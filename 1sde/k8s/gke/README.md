# GKE — Guestbook Demo

This directory deploys the same FastAPI + MongoDB guestbook app as `k8s/raw/`,
but on **Google Kubernetes Engine** with production-leaning GCP integrations.

---

## Table of Contents

1. [What GKE Gives You (vs. raw)](#what-gke-gives-you-vs-raw)
2. [Cost Warning](#cost-warning)
3. [Prerequisites](#prerequisites)
4. [Directory Layout](#directory-layout)
5. [Step-by-Step: Happy Path](#step-by-step-happy-path)
   - [Step 1 — Set Shell Variables](#step-1--set-shell-variables)
   - [Step 2 — Enable GCP APIs](#step-2--enable-gcp-apis)
   - [Step 3 — Create Artifact Registry and Push the Image](#step-3--create-artifact-registry-and-push-the-image)
   - [Step 4 — Create the Cluster](#step-4--create-the-cluster)
     - [Option A: GKE Autopilot (recommended)](#option-a-gke-autopilot-recommended)
     - [Option B: GKE Standard via gcloud](#option-b-gke-standard-via-gcloud)
     - [Option C: GKE Standard via Terraform](#option-c-gke-standard-via-terraform)
   - [Step 5 — Configure kubectl](#step-5--configure-kubectl)
   - [Step 6 — Set Up Workload Identity](#step-6--set-up-workload-identity)
   - [Step 7 — Update Overlay Placeholders](#step-7--update-overlay-placeholders)
   - [Step 8 — Deploy with Kustomize](#step-8--deploy-with-kustomize)
   - [Step 9 — Expose via GCE Load Balancer and Test](#step-9--expose-via-gce-load-balancer-and-test)
   - [Step 10 — (Optional) Enable Gateway API](#step-10--optional-enable-gateway-api)
6. [Teardown](#teardown)
7. [Troubleshooting](#troubleshooting)

---

## What GKE Gives You (vs. raw)

| Feature | k8s/raw (kind/bare cluster) | GKE |
|---|---|---|
| **Control plane** | You run it (kubeadm) or it's ephemeral (kind) | Google manages it: HA, auto-upgraded, SLA-backed |
| **Node management** | You provision VMs, patch OS, drain for upgrades | Auto-upgrade, auto-repair, Shielded VMs |
| **Autopilot mode** | Not available | Fully serverless nodes: pay per Pod, not per node |
| **Workload Identity** | Static key files or IRSA equivalent | Native OIDC federation: KSA → GSA, zero key files |
| **Cloud Load Balancer** | NodePort + local nginx controller | GCE L7 HTTPS LB provisioned from an Ingress object; or Gateway API |
| **Persistent disks** | hostPath / local PVs | PD CSI driver: pd-standard, pd-balanced, pd-ssd, regional PDs |
| **NetworkPolicy** | CNI-dependent (kindnet doesn't enforce) | Dataplane V2 (eBPF / Cilium): enforced everywhere, observable |
| **Node auto-provisioning** | Not available | NAP creates node pools on demand to fit pending Pods |
| **Managed Prometheus** | You install/manage Prometheus yourself | GKE Managed Prometheus: scrapes built-in, integrated with Cloud Monitoring |
| **Container image scanning** | Manual | Artifact Registry scans on push (with Container Analysis API) |
| **Cluster upgrades** | Manual | Release channels (RAPID/REGULAR/STABLE) with maintenance windows |

---

## Cost Warning

Running this demo creates **billable GCP resources**. Approximate US costs:

| Resource | Approximate cost |
|---|---|
| GKE Standard cluster (management fee) | ~$0.10/hour (~$73/month) |
| e2-standard-2 node (1 node, us-central1) | ~$0.067/hour |
| pd-balanced 1 GiB (MongoDB PVC) | ~$0.10/GiB/month |
| GCE HTTP(S) Load Balancer | ~$0.025/hour + $0.008/GB |
| Artifact Registry | $0.10/GB/month after free tier |
| **GKE Autopilot** (instead of Standard) | No cluster fee; pay per Pod resource |

**Always run the teardown steps** when you finish to avoid unexpected charges.
Estimate your costs at https://cloud.google.com/products/calculator.

---

## Prerequisites

Install and configure these tools before starting:

### Required

```
gcloud CLI (Google Cloud SDK)   https://cloud.google.com/sdk/docs/install
kubectl                         https://kubernetes.io/docs/tasks/tools/
gke-gcloud-auth-plugin          gcloud components install gke-gcloud-auth-plugin
Docker                          https://docs.docker.com/get-docker/
```

Verify versions:
```bash
gcloud version                  # >= 460.0.0
kubectl version --client        # >= 1.28
docker version                  # >= 24.0
```

### Optional (for Terraform path)

```
Terraform                       https://developer.hashicorp.com/terraform/install
# >= 1.7.0 required
```

### GCP Account Requirements

- A GCP **project** with **billing enabled**. Create one at https://console.cloud.google.com/projectcreate.
- Your account needs the following IAM roles (or Owner):
  - `roles/container.admin`
  - `roles/iam.serviceAccountAdmin`
  - `roles/iam.workloadIdentityPoolAdmin`
  - `roles/artifactregistry.admin`
  - `roles/compute.networkAdmin`

Authenticate the gcloud CLI:
```bash
gcloud auth login
gcloud auth application-default login   # used by Terraform + GCP client libraries
```

---

## Directory Layout

```
k8s/gke/
├── README.md                   # this file
├── manifests/                  # Kustomize overlay (references k8s/raw as base)
│   ├── kustomization.yaml      # overlay entry point
│   ├── storageclass.yaml       # pd-balanced StorageClass + patch
│   ├── ingress.yaml            # BackendConfig + GCE Ingress + Gateway API alternative
│   └── serviceaccount-patch.yaml  # Workload Identity annotation on KSA
└── terraform/                  # Infrastructure-as-Code for the cluster
    ├── versions.tf             # Terraform + provider version pins
    ├── variables.tf            # all tuneable inputs
    ├── main.tf                 # VPC, GKE cluster, node pool, GSA, Artifact Registry
    └── outputs.tf              # kubeconfig command, image tag, GSA email, etc.
```

The Kustomize overlay is intentionally minimal: it only adds and patches the
things that differ on GKE. The full app definition lives in `k8s/raw/` (the
base) and is shared across all cloud overlays.

---

## Step-by-Step: Happy Path

### Step 1 — Set Shell Variables

Export these once; all subsequent commands reference them.

```bash
export PROJECT_ID="your-gcp-project-id"    # gcloud projects list
export REGION="us-central1"                 # or your nearest region
export CLUSTER_NAME="guestbook"
export AR_REPO="guestbook"                  # Artifact Registry repo name
export AR_HOST="${REGION}-docker.pkg.dev"
export IMAGE="${AR_HOST}/${PROJECT_ID}/${AR_REPO}/guestbook:1.0.0"
export GSA_NAME="guestbook-app"
export GSA_EMAIL="${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
```

Set your default project and region to avoid repeating `--project`/`--region`:
```bash
gcloud config set project "${PROJECT_ID}"
gcloud config set compute/region "${REGION}"
```

---

### Step 2 — Enable GCP APIs

Some APIs take 1–2 minutes to activate. Run these once per project:

```bash
gcloud services enable \
  container.googleapis.com \
  artifactregistry.googleapis.com \
  compute.googleapis.com \
  iam.googleapis.com
```

Verify:
```bash
gcloud services list --enabled --filter="name:(container OR artifactregistry OR compute OR iam)"
```

---

### Step 3 — Create Artifact Registry and Push the Image

#### 3a. Create the repository

```bash
gcloud artifacts repositories create "${AR_REPO}" \
  --repository-format=docker \
  --location="${REGION}" \
  --description="Guestbook demo images"
```

#### 3b. Configure Docker to authenticate to Artifact Registry

```bash
gcloud auth configure-docker "${AR_HOST}"
# This writes credentials to ~/.docker/config.json for the AR hostname.
```

#### 3c. Build and push the image

```bash
# From the repo root:
docker build -t "guestbook:1.0.0" k8s/app/

# Re-tag with the full Artifact Registry path:
docker tag "guestbook:1.0.0" "${IMAGE}"

# Push:
docker push "${IMAGE}"
```

Verify the image is in Artifact Registry:
```bash
gcloud artifacts docker images list "${AR_HOST}/${PROJECT_ID}/${AR_REPO}"
```

---

### Step 4 — Create the Cluster

Choose **one** of the three options below. Option A (Autopilot) is recommended
for demos and new GKE users. Option B or C (Standard) gives you more control
over node configuration.

---

#### Option A: GKE Autopilot (recommended)

Autopilot manages nodes entirely — no node pool configuration, no OS patching,
no capacity planning. You pay per Pod (vCPU + memory), not per node.

```bash
gcloud container clusters create-auto "${CLUSTER_NAME}" \
  --region="${REGION}" \
  --release-channel=regular
```

This single command creates a regional, VPC-native Autopilot cluster with
Workload Identity enabled by default. It takes about 5–10 minutes.

**Autopilot limitations to be aware of:**
- DaemonSets are restricted (GKE runs system DaemonSets; user DaemonSets are not allowed).
- Privileged containers are not allowed (our app is already non-privileged, so this is fine).
- Node SSH access is not available.
- Some resource requests/limits are mutated by Autopilot to fit their billing model.

---

#### Option B: GKE Standard via gcloud

A Standard cluster where you control the node pool:

```bash
# Create VPC and subnet first:
gcloud compute networks create guestbook-vpc --subnet-mode=custom

gcloud compute networks subnets create guestbook-subnet \
  --network=guestbook-vpc \
  --region="${REGION}" \
  --range=10.0.0.0/20 \
  --secondary-range pods=10.4.0.0/16,services=10.8.0.0/20

# Create the cluster:
gcloud container clusters create "${CLUSTER_NAME}" \
  --region="${REGION}" \
  --cluster-version="1.30" \
  --release-channel=regular \
  --network=guestbook-vpc \
  --subnetwork=guestbook-subnet \
  --cluster-secondary-range-name=pods \
  --services-secondary-range-name=services \
  --enable-ip-alias \
  --workload-pool="${PROJECT_ID}.svc.id.goog" \
  --datapath-provider=advanced \
  --enable-shielded-nodes \
  --num-nodes=1 \
  --machine-type=e2-standard-2 \
  --disk-type=pd-balanced \
  --disk-size=50 \
  --no-enable-basic-auth \
  --no-issue-client-certificate

# Takes about 8–12 minutes.
```

**Key flags explained:**
- `--enable-ip-alias` — VPC-native networking (required for Workload Identity and container-native NEGs)
- `--workload-pool` — enables Workload Identity federation cluster-wide
- `--datapath-provider=advanced` — enables Dataplane V2 (eBPF NetworkPolicy enforcement)
- `--enable-shielded-nodes` — Shielded VMs (Secure Boot, vTPM, integrity monitoring)

---

#### Option C: GKE Standard via Terraform

Use the provided Terraform code in `k8s/gke/terraform/`:

```bash
cd k8s/gke/terraform

# Initialize: downloads provider plugins and modules.
terraform init

# Preview the plan (nothing is created yet):
terraform plan -var="project_id=${PROJECT_ID}" -var="region=${REGION}"

# Apply (creates ~7 resources; takes 10–15 minutes):
terraform apply -var="project_id=${PROJECT_ID}" -var="region=${REGION}"

# After apply, retrieve useful values:
terraform output kubeconfig_command   # run this to configure kubectl
terraform output gsa_email            # paste into serviceaccount-patch.yaml
terraform output image_push_tag       # full image tag for the push above
```

To switch to Autopilot via Terraform, comment out the
`google_container_cluster.primary` and `google_container_node_pool.default`
blocks in `main.tf` and uncomment the `google_container_cluster.autopilot`
block at the bottom of that file.

---

### Step 5 — Configure kubectl

```bash
gcloud container clusters get-credentials "${CLUSTER_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}"

# Verify connectivity:
kubectl cluster-info
kubectl get nodes
```

The `gke-gcloud-auth-plugin` (installed in prerequisites) handles token
refresh automatically. You no longer need to run `gcloud container clusters
get-credentials` on every new shell — the entry is stored in `~/.kube/config`.

---

### Step 6 — Set Up Workload Identity

If you used Terraform (Option C), it already created the GSA and IAM binding.
Skip to Step 7.

For the Autopilot or gcloud paths:

#### 6a. Create the Google Service Account

```bash
gcloud iam service-accounts create "${GSA_NAME}" \
  --display-name="Guestbook App — Workload Identity" \
  --description="Cloud identity for guestbook-app Pods"
```

#### 6b. Bind the Kubernetes ServiceAccount to the GSA

This grants the K8s SA (in namespace `guestbook`, named `guestbook-app`)
permission to impersonate the GSA via Workload Identity:

```bash
gcloud iam service-accounts add-iam-policy-binding "${GSA_EMAIL}" \
  --role=roles/iam.workloadIdentityUser \
  --member="serviceAccount:${PROJECT_ID}.svc.id.goog[guestbook/guestbook-app]"
```

Why this works: When a Pod runs as KSA `guestbook-app`, GKE injects an OIDC
token identifying `PROJECT.svc.id.goog[guestbook/guestbook-app]`. That token
is exchanged for a Google OAuth token for the GSA — exactly the principal
you just granted `workloadIdentityUser` to.

#### 6c. (Optional) Grant the GSA access to GCP services

The guestbook app doesn't currently call GCP APIs, but here's the pattern if
you add Secret Manager or Cloud Storage later:

```bash
# Example: allow the app to read secrets from Secret Manager
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --role=roles/secretmanager.secretAccessor \
  --member="serviceAccount:${GSA_EMAIL}"
```

---

### Step 7 — Update Overlay Placeholders

Two files need your project-specific values before you apply:

#### 7a. `manifests/kustomization.yaml` — image name

Open `k8s/gke/manifests/kustomization.yaml` and update the `images:` section:

```yaml
images:
  - name: guestbook
    newName: us-central1-docker.pkg.dev/YOUR_PROJECT_ID/guestbook/guestbook
    newTag: "1.0.0"
```

Replace `YOUR_PROJECT_ID` with your actual project ID (and `us-central1` with
your region if different).

Using sed:
```bash
sed -i "s/YOUR_PROJECT_ID/${PROJECT_ID}/g" k8s/gke/manifests/kustomization.yaml
```

#### 7b. `manifests/serviceaccount-patch.yaml` — GSA email

Open `k8s/gke/manifests/serviceaccount-patch.yaml` and update the annotation:

```yaml
annotations:
  iam.gke.io/gcp-service-account: "guestbook-app@YOUR_PROJECT_ID.iam.gserviceaccount.com"
```

Using sed:
```bash
sed -i "s/YOUR_PROJECT_ID/${PROJECT_ID}/g" k8s/gke/manifests/serviceaccount-patch.yaml
```

#### 7c. `manifests/ingress.yaml` — hostname (optional)

The Ingress uses `guestbook.example.com` as a placeholder host. For testing
without a real domain, you can:

a. Use `nip.io`: after the LB IP is assigned (Step 9), update the host to
   `guestbook.LB_IP.nip.io` (e.g., `guestbook.34.120.1.2.nip.io`) and
   re-apply.

b. Leave the host as-is and curl the LB IP directly with a `Host` header
   (see Step 9 for the test command).

---

### Step 8 — Deploy with Kustomize

Kustomize is built into kubectl (no separate install needed):

```bash
# Dry-run: see what would be applied without actually applying
kubectl apply -k k8s/gke/manifests --dry-run=client

# Apply everything (Namespace, Secrets, ConfigMaps, StatefulSet, Deployment,
# Service, Ingress, BackendConfig, HPA, PDB, NetworkPolicies, Jobs, StorageClass):
kubectl apply -k k8s/gke/manifests

# Watch rollout:
kubectl rollout status deployment/guestbook -n guestbook
kubectl rollout status statefulset/mongo -n guestbook

# Check all resources:
kubectl get all -n guestbook
```

Expected output (healthy state):
```
NAME                             READY   STATUS    RESTARTS   AGE
pod/guestbook-XXXXX-YYYYY        1/1     Running   0          2m
pod/guestbook-XXXXX-ZZZZZ        1/1     Running   0          2m
pod/mongo-0                      1/1     Running   0          3m

NAME                TYPE        CLUSTER-IP    EXTERNAL-IP   PORT(S)    AGE
service/guestbook   ClusterIP   10.8.1.5      <none>        80/TCP     3m
service/mongo       ClusterIP   None          <none>        27017/TCP  3m

NAME                        READY   UP-TO-DATE   AVAILABLE   AGE
deployment.apps/guestbook   2/2     2            2           2m

NAME                     READY   AGE
statefulset.apps/mongo   1/1     3m
```

---

### Step 9 — Expose via GCE Load Balancer and Test

#### 9a. Wait for the load balancer IP

The GCE Ingress controller provisions a load balancer asynchronously. It
typically takes 2–5 minutes for the IP to appear and for the backend to become
healthy.

```bash
# Poll until EXTERNAL-IP is assigned:
kubectl get ingress guestbook -n guestbook --watch

# Or one-liner to wait and print:
until kubectl get ingress guestbook -n guestbook -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null | grep -qE '[0-9]'; do
  echo "Waiting for LB IP..."; sleep 10
done
LB_IP=$(kubectl get ingress guestbook -n guestbook -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "Load balancer IP: ${LB_IP}"
```

#### 9b. Check backend health

```bash
kubectl describe ingress guestbook -n guestbook
# Look for: Backends: guestbook:80 (HEALTHY)
# If UNHEALTHY, check: kubectl describe backendconfig guestbook-backend-config -n guestbook
```

#### 9c. Test the app

```bash
# Using the Host header (no DNS change needed):
curl -H "Host: guestbook.example.com" "http://${LB_IP}/"
curl -H "Host: guestbook.example.com" "http://${LB_IP}/healthz"
curl -H "Host: guestbook.example.com" "http://${LB_IP}/api/messages"

# POST a guestbook entry:
curl -X POST "http://${LB_IP}/api/messages" \
  -H "Host: guestbook.example.com" \
  -H "Content-Type: application/json" \
  -d '{"author": "demo", "text": "Hello from GKE!"}'

# Or with a real domain / nip.io:
curl "http://guestbook.${LB_IP}.nip.io/"
```

#### 9d. (Optional) Reserve a static IP for production

A reserved static IP survives cluster recreation and can be attached to a DNS
record:

```bash
gcloud compute addresses create guestbook-ip --global

# Note the IP:
gcloud compute addresses describe guestbook-ip --global --format='value(address)'

# Uncomment the kubernetes.io/ingress.global-static-ip-name annotation in
# manifests/ingress.yaml and re-apply:
kubectl apply -k k8s/gke/manifests
```

---

### Step 10 — (Optional) Enable Gateway API

The Gateway API is the next-generation successor to Ingress, providing a
richer, role-oriented routing model.

```bash
# Enable Gateway API on an existing cluster:
gcloud container clusters update "${CLUSTER_NAME}" \
  --region="${REGION}" \
  --gateway-api=standard

# Wait for GatewayClass to appear:
kubectl get gatewayclass

# Uncomment the Gateway + HTTPRoute block in manifests/ingress.yaml and apply.
```

The `gke-l7-global-external-managed` GatewayClass creates the same GCE L7 LB
but with HTTPRoute-based routing rules.

---

## Teardown

Run these commands in order to stop all billing:

```bash
# 1. Delete Kubernetes resources (releases the load balancer and any NEGs):
kubectl delete -k k8s/gke/manifests

# 2a. If using Terraform: destroy all infrastructure
cd k8s/gke/terraform
terraform destroy -var="project_id=${PROJECT_ID}" -var="region=${REGION}"

# 2b. If using gcloud (Standard cluster):
gcloud container clusters delete "${CLUSTER_NAME}" --region="${REGION}"
gcloud compute networks subnets delete guestbook-subnet --region="${REGION}"
gcloud compute networks delete guestbook-vpc

# 3. Delete Artifact Registry (and all images stored in it):
gcloud artifacts repositories delete "${AR_REPO}" --location="${REGION}"

# 4. Delete the GSA:
gcloud iam service-accounts delete "${GSA_EMAIL}"

# 5. (If reserved) Release the static IP:
gcloud compute addresses delete guestbook-ip --global

# 6. Verify no orphaned resources remain:
gcloud compute forwarding-rules list
gcloud compute target-https-proxies list
gcloud compute backend-services list
```

Persistent Disks created from PVCs are retained by default (reclaimPolicy:
Retain in storageclass.yaml). Delete them explicitly:

```bash
# List PDs created by GKE:
gcloud compute disks list --filter="labels.kubernetes_io_created-for-pv-namespace=guestbook"

# Delete each one:
gcloud compute disks delete DISK_NAME --zone=ZONE
```

---

## Troubleshooting

### Backend UNHEALTHY in Ingress describe

The GCE LB health check hits `/healthz` on port 8000 directly on the Pod IP
(container-native NEG). Common causes:
- Pod isn't ready yet: `kubectl get pods -n guestbook`
- Health check path wrong: verify `requestPath: /healthz` in BackendConfig matches the app's `/healthz` endpoint
- Firewall rule blocking the GFE health check probe: GKE creates `gke-CLUSTER-NAME-*-health` firewall rules automatically; if you have an overly restrictive firewall policy, it may block probes from `35.191.0.0/16` and `130.211.0.0/22`

Allow GCE LB health check sources (if blocked):
```bash
gcloud compute firewall-rules create allow-gce-health-checks \
  --network=guestbook-vpc \
  --action=allow \
  --direction=ingress \
  --source-ranges=35.191.0.0/16,130.211.0.0/22 \
  --target-tags=gke-guestbook \
  --rules=tcp:8000
```

### Pod stuck in Pending on Autopilot

Autopilot may take 60–90 seconds to provision a node for a new Pod. Just wait.
If it stays Pending > 5 minutes:
```bash
kubectl describe pod -n guestbook POD_NAME
# Check Events for resource requests that exceed Autopilot limits
```

### MongoDB PVC stuck in Pending

This is usually because `WaitForFirstConsumer` is working correctly — the PVC
doesn't bind until the Pod is scheduled. Once the mongo Pod is scheduled, the
PVC will bind and the PD will be created in the correct zone.

### Workload Identity token not working

```bash
# Verify annotation on the KSA:
kubectl get serviceaccount guestbook-app -n guestbook -o yaml | grep iam.gke.io

# Verify IAM binding on the GSA:
gcloud iam service-accounts get-iam-policy "${GSA_EMAIL}"
# Should show: role: roles/iam.workloadIdentityUser
#              member: serviceAccount:PROJECT.svc.id.goog[guestbook/guestbook-app]

# Test from inside a Pod:
kubectl run -it --rm wi-test \
  --image=google/cloud-sdk:slim \
  --namespace=guestbook \
  --overrides='{"spec":{"serviceAccountName":"guestbook-app"}}' \
  -- gcloud auth print-identity-token
```

### `gke-gcloud-auth-plugin` not found

```bash
gcloud components install gke-gcloud-auth-plugin
export USE_GKE_GCLOUD_AUTH_PLUGIN=True
```

Or install via package manager:
```bash
# Debian/Ubuntu:
sudo apt-get install google-cloud-cli-gke-gcloud-auth-plugin
```
