# =============================================================================
# main.tf — GKE Standard cluster with Workload Identity, Dataplane V2,
#           VPC-native networking, and a Google Service Account for the app.
#
# Architecture overview
# ─────────────────────
#   VPC  ──►  Subnet (primary: nodes, secondary: pods + services)
#               └─► GKE Standard cluster
#                     ├─ Workload Identity enabled cluster-wide
#                     ├─ Dataplane V2 (eBPF CNI with NetworkPolicy enforcement)
#                     ├─ Autopilot (commented block at the bottom)
#                     └─ Default node pool
#
# Resources created
# ─────────────────
#   1. Required GCP APIs
#   2. VPC + subnet (with secondary ranges for VPC-native GKE)
#   3. GKE Standard cluster (regional, private-nodes optional)
#   4. Default node pool
#   5. Google Service Account for Workload Identity (app identity)
#   6. Workload Identity IAM binding (GSA → KSA annotation)
#   7. Artifact Registry repo (to store the guestbook container image)
# =============================================================================


# ─────────────────────────────────────────────────────────────────────────────
# 1. Enable Required APIs
# GCP APIs must be explicitly enabled before you can use them.  Terraform can
# do this; the services may take ~1–2 min to activate on first apply.
# ─────────────────────────────────────────────────────────────────────────────
resource "google_project_service" "container" {
  # The Container (GKE) API — prerequisite for any GKE cluster.
  service                    = "container.googleapis.com"
  disable_on_destroy         = false   # don't disable when `terraform destroy` runs
  disable_dependent_services = false
}

resource "google_project_service" "artifactregistry" {
  # Artifact Registry replaces Container Registry as the managed image store.
  service                    = "artifactregistry.googleapis.com"
  disable_on_destroy         = false
  disable_dependent_services = false
}

resource "google_project_service" "compute" {
  # Compute Engine API is needed for the VPC, subnets, and node VMs.
  service                    = "compute.googleapis.com"
  disable_on_destroy         = false
  disable_dependent_services = false
}

resource "google_project_service" "iam" {
  # IAM API is needed to manage Service Accounts and Workload Identity bindings.
  service                    = "iam.googleapis.com"
  disable_on_destroy         = false
  disable_dependent_services = false
}


# ─────────────────────────────────────────────────────────────────────────────
# 2. VPC and Subnet
#
# GKE VPC-native clusters require a subnet with two *secondary IP ranges*:
#   • pods range    — each Pod gets a real VPC IP (alias IPs), not NAT'd
#   • services range — ClusterIP addresses come from here
# VPC-native mode is required for Workload Identity and Dataplane V2.
# ─────────────────────────────────────────────────────────────────────────────
resource "google_compute_network" "vpc" {
  name                    = var.network_name
  auto_create_subnetworks = false   # we define subnets explicitly

  depends_on = [google_project_service.compute]
}

resource "google_compute_subnetwork" "subnet" {
  name          = var.subnet_name
  network       = google_compute_network.vpc.id
  region        = var.region
  ip_cidr_range = var.subnet_ip_cidr_range

  # Secondary ranges are named so GKE can reference them by name below.
  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = var.pods_ip_cidr_range
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = var.services_ip_cidr_range
  }

  # Enable Google private access so Pods can reach Google APIs (like Secret
  # Manager, Artifact Registry) without a public IP.
  private_ip_google_access = true

  log_config {
    aggregation_interval = "INTERVAL_10_MIN"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }
}

# Cloud NAT is only needed when nodes have no public IPs (private nodes).
# Uncomment if you set enable_private_nodes = true.
# resource "google_compute_router" "router" {
#   name    = "${var.cluster_name}-router"
#   region  = var.region
#   network = google_compute_network.vpc.id
# }
# resource "google_compute_router_nat" "nat" {
#   name                               = "${var.cluster_name}-nat"
#   router                             = google_compute_router.router.name
#   region                             = var.region
#   nat_ip_allocate_option             = "AUTO_ONLY"
#   source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
# }


# ─────────────────────────────────────────────────────────────────────────────
# 3. GKE Standard Cluster
#
# Key decisions explained:
#   • regional cluster (var.region) — control plane spans 3 zones, zero
#     downtime during control-plane upgrades (vs. a zonal cluster).
#   • remove_default_node_pool = true — we define a separate node pool below
#     so we can configure it fully; the default pool created with the cluster
#     is unusable anyway (can't be modified after creation in some settings).
#   • workload_identity_config — maps KSA → GSA via OIDC token federation,
#     eliminating the need for static key files in Pods.
#   • datapath_provider = "ADVANCED_DATAPATH" — enables Dataplane V2 (GKE's
#     eBPF CNI based on Cilium). Enforces NetworkPolicy without an extra
#     operator and provides L4 observability.
#   • enable_shielded_nodes — Shielded VMs provide verified boot and integrity
#     monitoring, defending against rootkits and boot-level malware.
# ─────────────────────────────────────────────────────────────────────────────
resource "google_container_cluster" "primary" {
  provider = google-beta   # some beta features (gateway API) require beta

  name     = var.cluster_name
  location = var.region    # regional = HA control plane across 3 zones

  # Kubernetes minor version.  "latest" always gives the newest available
  # channel version; pin to e.g. "1.30" for predictable upgrades.
  min_master_version = var.kubernetes_version

  # We create and manage our own node pool below, so delete the default one
  # that GKE forces upon creation.
  remove_default_node_pool = true
  initial_node_count       = 1   # required dummy value when removing default pool

  # ── Networking ─────────────────────────────────────────────────────────────
  network    = google_compute_network.vpc.id
  subnetwork = google_compute_subnetwork.subnet.id

  # VPC-native (alias IPs) — mandatory for Workload Identity + Dataplane V2.
  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  # Dataplane V2: eBPF-based data plane that enforces NetworkPolicy natively.
  # IMPORTANT: cannot be changed after cluster creation.
  datapath_provider = "ADVANCED_DATAPATH"

  # ── Control-plane access ───────────────────────────────────────────────────
  private_cluster_config {
    enable_private_nodes    = var.enable_private_nodes
    enable_private_endpoint = false   # keep public endpoint for kubectl access
    master_ipv4_cidr_block  = var.master_ipv4_cidr_block
  }

  master_authorized_networks_config {
    dynamic "cidr_blocks" {
      for_each = var.master_authorized_networks
      content {
        cidr_block   = cidr_blocks.value.cidr_block
        display_name = cidr_blocks.value.display_name
      }
    }
  }

  # ── Workload Identity ──────────────────────────────────────────────────────
  # Enables the cluster-level OIDC issuer that pods use to exchange their
  # Kubernetes service account token for a short-lived Google OAuth token.
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # ── Add-ons ────────────────────────────────────────────────────────────────
  addons_config {
    # HTTP load balancing creates GCE L7 LBs from Ingress objects — required
    # for the GKE Ingress controller to work.
    http_load_balancing {
      disabled = false
    }
    # Horizontal Pod Autoscaling add-on installs the metrics-server adapter
    # so the HPA defined in the base manifest can scale on CPU.
    horizontal_pod_autoscaling {
      disabled = false
    }
    # GKE Managed Prometheus (also known as Google Cloud Managed Service for
    # Prometheus) — scrapes Pod metrics automatically.  Optional; disable to
    # save ~$0.10/GiB ingested during demo.
    gke_backup_agent_config {
      enabled = false
    }
  }

  # ── Gateway API ────────────────────────────────────────────────────────────
  # Uncomment to enable the Gateway API CRDs managed by GKE.  Required if
  # you want to use the Gateway/HTTPRoute alternative shown in ingress.yaml.
  # gateway_api_config {
  #   channel = "CHANNEL_STANDARD"
  # }

  # ── Security ───────────────────────────────────────────────────────────────
  enable_shielded_nodes = true

  # Binary Authorization can enforce that only signed images run in the cluster.
  # binary_authorization { evaluation_mode = "PROJECT_SINGLETON_POLICY_ENFORCE" }

  # Release channel governs automatic upgrades.  REGULAR is the sweet spot:
  # ~2–3 months behind bleeding edge, well-tested, still current.
  release_channel {
    channel = "REGULAR"
  }

  # Maintenance window: upgrade nodes during low-traffic hours.
  maintenance_policy {
    recurring_window {
      start_time = "2024-01-01T03:00:00Z"
      end_time   = "2024-01-01T07:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SA,SU"
    }
  }

  # Logging and monitoring: send to Cloud Logging and Cloud Monitoring.
  logging_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS"]
  }
  monitoring_config {
    enable_components = ["SYSTEM_COMPONENTS"]
    managed_prometheus {
      enabled = true
    }
  }

  depends_on = [
    google_project_service.container,
    google_compute_subnetwork.subnet,
  ]
}


# ─────────────────────────────────────────────────────────────────────────────
# 4. Default Node Pool
#
# Separating the node pool from the cluster resource makes it possible to
# resize, upgrade, or replace nodes without recreating the whole cluster.
#
# Workload Identity on nodes: the `workload_metadata_config` block sets the
# node metadata to GKE_METADATA, which:
#   • prevents Pods from reaching the instance metadata endpoint directly
#   • routes workload-identity token requests through the GKE metadata server
# ─────────────────────────────────────────────────────────────────────────────
resource "google_container_node_pool" "default" {
  name       = "default-pool"
  cluster    = google_container_cluster.primary.id
  location   = var.region   # regional pool spans all zones in the region

  initial_node_count = var.node_pool_initial_count

  # Cluster autoscaler: adds/removes nodes based on pending Pods and idle nodes.
  autoscaling {
    min_node_count = var.node_pool_min_count
    max_node_count = var.node_pool_max_count
  }

  # Automatic node upgrades keep nodes patched; auto-repair replaces unhealthy
  # nodes without manual intervention.
  management {
    auto_upgrade = true
    auto_repair  = true
  }

  # Upgrade strategy: surge upgrades replace nodes one-by-one (max-surge=1,
  # max-unavailable=0) for zero-downtime rolling node upgrades.
  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
  }

  node_config {
    machine_type = var.node_pool_machine_type
    disk_size_gb = var.node_pool_disk_size_gb
    disk_type    = var.node_pool_disk_type

    # OAuth scopes grant the node's default GSA permission to call GCP APIs.
    # cloud-platform is broad; production should use fine-grained scopes.
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]

    # Shielded instance settings complement enable_shielded_nodes at cluster
    # level: secure boot prevents loading unsigned kernel modules.
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    # THIS IS THE KEY NODE-LEVEL WORKLOAD IDENTITY SETTING.
    # GKE_METADATA blocks direct access to the Compute metadata server and
    # routes Pod token requests through the GKE metadata server, which
    # exchanges the Kubernetes SA token for a Google OAuth token.
    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    # Labels stamped on all nodes — useful for nodeSelector or affinity rules.
    labels = {
      "app.kubernetes.io/part-of" = "guestbook"
      "managed-by"                = "terraform"
    }
  }
}


# ─────────────────────────────────────────────────────────────────────────────
# 5. Google Service Account for Workload Identity
#
# The app doesn't call any GCP APIs today, but every non-trivial app eventually
# needs to (e.g., Secret Manager, Cloud Storage, Pub/Sub).  This GSA is the
# *cloud identity* the guestbook-app Pods will assume via Workload Identity.
# ─────────────────────────────────────────────────────────────────────────────
resource "google_service_account" "guestbook_app" {
  account_id   = var.gsa_name
  display_name = "Guestbook App — Workload Identity"
  description  = "Cloud identity for guestbook-app Pods via Workload Identity Federation"

  depends_on = [google_project_service.iam]
}

# (Optional) grant the GSA read access to Secret Manager secrets.
# Uncomment if the app should fetch secrets from Secret Manager.
# resource "google_project_iam_member" "secretmanager_accessor" {
#   project = var.project_id
#   role    = "roles/secretmanager.secretAccessor"
#   member  = "serviceAccount:${google_service_account.guestbook_app.email}"
# }


# ─────────────────────────────────────────────────────────────────────────────
# 6. Workload Identity IAM Binding
#
# This grants the *Kubernetes Service Account* (guestbook-app in namespace
# guestbook) permission to impersonate the Google Service Account created
# above.  The mechanism is Workload Identity Federation (WIF):
#
#   Pod requests token → GKE metadata server validates K8s SA token →
#   exchanges it for a short-lived Google OAuth token for the GSA.
#
# The other half of the binding is the annotation on the KSA:
#   iam.gke.io/gcp-service-account: guestbook-app@PROJECT.iam.gserviceaccount.com
# That annotation is applied in manifests/serviceaccount-patch.yaml.
# ─────────────────────────────────────────────────────────────────────────────
resource "google_service_account_iam_member" "workload_identity_binding" {
  service_account_id = google_service_account.guestbook_app.name

  # The role "roles/iam.workloadIdentityUser" allows a principal (here a
  # Kubernetes SA expressed as a service account identity) to impersonate a GSA.
  role = "roles/iam.workloadIdentityUser"

  # The principal is: the K8s namespace + service account, expressed in the
  # format GCP WIF expects: serviceAccount:PROJECT.svc.id.goog[NS/KSA]
  member = "serviceAccount:${var.project_id}.svc.id.goog[guestbook/guestbook-app]"

  depends_on = [google_container_cluster.primary]
}


# ─────────────────────────────────────────────────────────────────────────────
# 7. Artifact Registry Repository
#
# Artifact Registry is the successor to Container Registry (gcr.io).
# Images stored here are automatically scanned for vulnerabilities when
# Container Analysis API is enabled.
# ─────────────────────────────────────────────────────────────────────────────
resource "google_artifact_registry_repository" "guestbook" {
  location      = var.artifact_registry_region
  repository_id = var.artifact_registry_repo
  format        = "DOCKER"
  description   = "Docker images for the guestbook demo app"

  depends_on = [google_project_service.artifactregistry]
}

# Grant the nodes' default service account read access to the registry so
# the GKE nodes can pull images without configuring imagePullSecrets.
# (Nodes use their own GSA for this, not the app's Workload Identity GSA.)
data "google_compute_default_service_account" "default" {
  depends_on = [google_project_service.compute]
}

resource "google_artifact_registry_repository_iam_member" "node_reader" {
  location   = google_artifact_registry_repository.guestbook.location
  repository = google_artifact_registry_repository.guestbook.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${data.google_compute_default_service_account.default.email}"
}


# =============================================================================
# AUTOPILOT ALTERNATIVE
# =============================================================================
# Replace the google_container_cluster + google_container_node_pool blocks
# above with this single resource to use GKE Autopilot instead of Standard.
#
# Autopilot differences:
#   • No node pool management — Google provisions, scales, upgrades, and
#     patches nodes entirely on your behalf.
#   • Billing is per-Pod (vCPU + memory) rather than per-node.
#   • Stronger security defaults (read-only root FS, non-root containers,
#     Workload Identity enforced, etc.).
#   • You cannot SSH into nodes or use DaemonSets for custom node agents.
#
# resource "google_container_cluster" "autopilot" {
#   provider         = google-beta
#   name             = var.cluster_name
#   location         = var.region
#   enable_autopilot = true
#
#   network    = google_compute_network.vpc.id
#   subnetwork = google_compute_subnetwork.subnet.id
#
#   ip_allocation_policy {
#     cluster_secondary_range_name  = "pods"
#     services_secondary_range_name = "services"
#   }
#
#   workload_identity_config {
#     workload_pool = "${var.project_id}.svc.id.goog"
#   }
#
#   release_channel {
#     channel = "REGULAR"
#   }
#
#   depends_on = [
#     google_project_service.container,
#     google_compute_subnetwork.subnet,
#   ]
# }
# =============================================================================
