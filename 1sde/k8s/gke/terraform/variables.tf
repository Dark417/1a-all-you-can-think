# =============================================================================
# variables.tf — All tuneable inputs for the GKE cluster.
#
# Pass values on the CLI (`-var project_id=my-proj`) or in a tfvars file
# (copy this block to `terraform.tfvars` and fill it in — never commit that
# file to source control if it contains secrets or billing-sensitive IDs).
# =============================================================================

variable "project_id" {
  description = "GCP project ID where all resources will be created."
  type        = string
  # No default — Terraform will prompt if not provided, ensuring you don't
  # accidentally deploy into the wrong project.
}

variable "region" {
  description = "GCP region for the cluster and node pool (e.g. us-central1)."
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = <<-EOT
    Primary zone within `region` for a zonal Standard cluster
    (e.g. us-central1-a).  Ignored when `autopilot` is true because Autopilot
    clusters are always regional (multi-zone).
  EOT
  type        = string
  default     = "us-central1-a"
}

variable "cluster_name" {
  description = "Name given to the GKE cluster."
  type        = string
  default     = "guestbook"
}

variable "kubernetes_version" {
  description = <<-EOT
    Kubernetes minor version channel to use, e.g. \"1.29\", \"1.30\".
    Pass \"latest\" to always use the newest available version —
    fine for demos, but pin this for production so upgrades are intentional.
  EOT
  type        = string
  default     = "1.30"
}

variable "node_pool_machine_type" {
  description = <<-EOT
    Compute Engine machine type for the default node pool.
    e2-standard-2 (2 vCPU / 8 GB) is a balanced choice for this demo.
    For a cost-minimal test: e2-small (2 vCPU / 2 GB) works but is tight.
  EOT
  type        = string
  default     = "e2-standard-2"
}

variable "node_pool_initial_count" {
  description = "Nodes to create per zone at cluster creation time."
  type        = number
  default     = 1
}

variable "node_pool_min_count" {
  description = "Minimum nodes per zone for cluster autoscaler."
  type        = number
  default     = 1
}

variable "node_pool_max_count" {
  description = "Maximum nodes per zone for cluster autoscaler."
  type        = number
  default     = 3
}

variable "node_pool_disk_size_gb" {
  description = "Boot-disk size in GiB per node."
  type        = number
  default     = 50
}

variable "node_pool_disk_type" {
  description = "Boot-disk type: pd-standard, pd-balanced, or pd-ssd."
  type        = string
  default     = "pd-balanced"
}

variable "network_name" {
  description = "Name of the VPC network to create for the cluster."
  type        = string
  default     = "guestbook-vpc"
}

variable "subnet_name" {
  description = "Name of the subnet to create inside the VPC."
  type        = string
  default     = "guestbook-subnet"
}

variable "subnet_ip_cidr_range" {
  description = "Primary CIDR for nodes in the subnet."
  type        = string
  default     = "10.0.0.0/20"
}

variable "pods_ip_cidr_range" {
  description = <<-EOT
    Secondary CIDR for Pods (alias IP range).
    GKE uses VPC-native networking; each Pod gets a real VPC IP from this range.
    /16 supports ~65 k Pods — overkill here but leaves room to grow.
  EOT
  type        = string
  default     = "10.4.0.0/16"
}

variable "services_ip_cidr_range" {
  description = "Secondary CIDR for Services (ClusterIP)."
  type        = string
  default     = "10.8.0.0/20"
}

variable "master_ipv4_cidr_block" {
  description = <<-EOT
    /28 CIDR for the GKE control-plane peering network.
    Must not overlap any existing ranges in your VPC.
    Used when `enable_private_nodes` is true.
  EOT
  type        = string
  default     = "172.16.0.32/28"
}

variable "enable_private_nodes" {
  description = <<-EOT
    When true, node VMs get only private IPs.  The control plane is still
    reachable via the private endpoint.  Recommended for production.
    Requires a Cloud NAT gateway for nodes to pull images; one is created
    automatically when this is true (see main.tf).
  EOT
  type        = bool
  default     = false   # false keeps the demo simpler (no NAT setup needed)
}

variable "master_authorized_networks" {
  description = <<-EOT
    List of CIDR blocks allowed to reach the public Kubernetes API endpoint.
    Lock this down to your office/VPN range in production.
    \"0.0.0.0/0\" (default) is convenient for demos but exposes the API server.
  EOT
  type = list(object({
    cidr_block   = string
    display_name = string
  }))
  default = [
    {
      cidr_block   = "0.0.0.0/0"
      display_name = "all (demo only — restrict in production)"
    }
  ]
}

variable "gsa_name" {
  description = <<-EOT
    Name of the Google Service Account to create for Workload Identity.
    This GSA is what the guestbook-app Kubernetes ServiceAccount will
    impersonate via Workload Identity.
  EOT
  type        = string
  default     = "guestbook-app"
}

variable "artifact_registry_region" {
  description = "Region for the Artifact Registry repository."
  type        = string
  default     = "us-central1"
}

variable "artifact_registry_repo" {
  description = "Name of the Artifact Registry Docker repository."
  type        = string
  default     = "guestbook"
}
