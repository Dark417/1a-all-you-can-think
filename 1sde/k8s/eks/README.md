# EKS Deployment — Kubernetes + MongoDB Guestbook

This directory deploys the same guestbook application from `k8s/raw/` onto AWS
Elastic Kubernetes Service (EKS). The application and its Kubernetes objects are
**unchanged** — this overlay only adds AWS-specific glue: an ALB Ingress, a gp3
StorageClass, an ECR image reference, and IRSA credentials for the app pod.

---

## Table of contents

1. [What EKS gives you that raw didn't](#what-eks-gives-you-that-raw-didnt)
2. [Prerequisites](#prerequisites)
3. [Cost warning](#cost-warning)
4. [Architecture overview](#architecture-overview)
5. [Happy path — eksctl](#happy-path--eksctl)
6. [Happy path — Terraform](#happy-path--terraform)
7. [Build and push the app image to ECR](#build-and-push-the-app-image-to-ecr)
8. [Install the AWS Load Balancer Controller](#install-the-aws-load-balancer-controller)
9. [Install the EBS CSI driver add-on](#install-the-ebs-csi-driver-add-on)
10. [Set up IRSA (IAM Roles for Service Accounts)](#set-up-irsa-iam-roles-for-service-accounts)
11. [Deploy the application](#deploy-the-application)
12. [Verify and test](#verify-and-test)
13. [Teardown](#teardown)
14. [Troubleshooting](#troubleshooting)

---

## What EKS gives you that raw didn't

| Feature | Local kind cluster | AWS EKS |
|---|---|---|
| **Managed control plane** | You run `kind create cluster` and own everything | AWS runs etcd + API server across 3 AZs; you never SSH into masters |
| **IAM integration (IRSA)** | No IAM; pods share the host's identity | Each ServiceAccount can assume a scoped IAM role via OIDC tokens — no static credentials anywhere |
| **Application Load Balancer** | nginx Ingress on localhost | AWS ALB Controller creates a real L7 load balancer from an Ingress object; TLS termination, WAF, access logs all available |
| **EBS / EFS CSI** | hostPath or kind volumes (lost on cluster delete) | Persistent EBS gp3 volumes that survive node replacement; online resize; multi-AZ EFS if needed |
| **VPC CNI** | kindnet (overlay, no VPC visibility) | Every pod gets a real VPC IP; security groups, VPC flow logs, and direct routing work without an overlay |
| **Cluster Autoscaler / Karpenter** | Fixed node count | Karpenter (or Cluster Autoscaler) provisions and terminates EC2 instances in response to pending pods; right-size nodes automatically |
| **Managed Node Groups** | N/A | AWS patches node AMIs, drains and replaces unhealthy nodes automatically |
| **ECR image registry** | Local Docker daemon | Private registry co-located with the cluster; pulls are free, rate-limit-free, and scanned for CVEs |

---

## Prerequisites

Install all tools before proceeding. Versions listed are minimum tested; newer
minor versions are generally fine.

### AWS account and IAM

- An AWS account with billing enabled.
- An IAM user or role with sufficient permissions. A quick way for testing:
  attach `AdministratorAccess`. For production, scope permissions to the
  services used (EKS, EC2, VPC, IAM, ECR, ELB, CloudFormation).
- Access key configured:
  ```bash
  aws configure
  # or
  export AWS_ACCESS_KEY_ID=...
  export AWS_SECRET_ACCESS_KEY=...
  export AWS_DEFAULT_REGION=us-east-1
  ```
- Verify identity:
  ```bash
  aws sts get-caller-identity
  ```

### CLI tools

| Tool | Install | Version check |
|---|---|---|
| `aws` CLI v2 | https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html | `aws --version` |
| `eksctl` | https://eksctl.io/installation/ | `eksctl version` (need >= 0.175) |
| `kubectl` | https://kubernetes.io/docs/tasks/tools/ | `kubectl version --client` |
| `helm` v3 | https://helm.sh/docs/intro/install/ | `helm version` |
| Docker | https://docs.docker.com/get-docker/ | `docker version` |
| `terraform` (optional, Terraform path only) | https://developer.hashicorp.com/terraform/install | `terraform version` (need >= 1.7) |

Quick install (macOS with Homebrew):
```bash
brew install awscli eksctl kubectl helm docker terraform
```

Quick install (Linux):
```bash
# aws CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
unzip awscliv2.zip && sudo ./aws/install

# eksctl
ARCH=amd64
PLATFORM=$(uname -s)_$ARCH
curl -sLO "https://github.com/eksctl-io/eksctl/releases/latest/download/eksctl_${PLATFORM}.tar.gz"
tar -xzf eksctl_${PLATFORM}.tar.gz -C /tmp
sudo mv /tmp/eksctl /usr/local/bin

# kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

---

## Cost warning

> **This demo is NOT free.** Running it for a day costs approximately **$8–15 USD**
> depending on region and instance type. Running it for a month without teardown
> will cost approximately **$250–400 USD**. Always run `eksctl delete cluster`
> or `terraform destroy` when you are done.

Approximate per-hour costs (us-east-1, on-demand, mid-2025):

| Resource | Count | $/hr each | $/hr total |
|---|---|---|---|
| EKS control plane | 1 | $0.10 | $0.10 |
| m5.large worker nodes | 2 | $0.096 | $0.192 |
| NAT Gateway | 1 | $0.045 | $0.045 |
| ALB | 1 | ~$0.025 | ~$0.025 |
| EBS gp3 (1 Gi) | 1 | ~$0.0001 | ~$0.0001 |
| **Total** | | | **~$0.36/hr ≈ $8.70/day** |

---

## Architecture overview

```
Internet
    │
    ▼
┌───────────────────────────────────────────┐
│  Application Load Balancer (public subnet) │  ← created by ALB Controller from Ingress
│  port 80 → target-type: ip               │
└──────────────┬────────────────────────────┘
               │  Pod IPs (VPC CNI)
               ▼
┌───────────────────────────────────────────┐
│  EKS Worker Nodes (private subnet)         │
│  ┌─────────────────┐  ┌────────────────┐  │
│  │ guestbook pod   │  │ guestbook pod  │  │  ← Deployment, 2 replicas
│  │ (IRSA → SSM)    │  │                │  │
│  └────────┬────────┘  └───────┬────────┘  │
│           │                   │            │
│           └─────────┬─────────┘            │
│                     ▼                      │
│            ┌────────────────┐              │
│            │  mongo-0 pod   │              │  ← StatefulSet, PVC → EBS gp3
│            │  /data/db      │              │
│            └────────────────┘              │
└───────────────────────────────────────────┘
               │  via NAT Gateway
               ▼
          AWS Services
      (ECR, SSM, STS/OIDC)
```

---

## Happy path — eksctl

Use this path if you prefer a single YAML file and a single command. eksctl
wraps CloudFormation internally.

### Step 1: Edit the cluster config

Open `k8s/eks/eksctl-cluster.yaml` and replace every `TODO` placeholder:

```bash
# Required substitutions:
# - TODO_ACCOUNT_ID  → your 12-digit AWS account ID
# - TODO_REGION      → the same region you set in aws configure

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=$(aws configure get region)
echo "Account: $AWS_ACCOUNT_ID   Region: $AWS_REGION"
```

You can do a quick find-and-replace:
```bash
sed -i "s/TODO_ACCOUNT_ID/${AWS_ACCOUNT_ID}/g; s/us-east-1/${AWS_REGION}/g" \
  k8s/eks/eksctl-cluster.yaml
```

### Step 2: Create the ALB Controller IAM policy

The AWS Load Balancer Controller needs a large IAM policy. Create it once:

```bash
# Download the policy JSON published by the controller project.
curl -O https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/v2.8.1/docs/install/iam_policy.json

# Create the policy in IAM.
aws iam create-policy \
  --policy-name AWSLoadBalancerControllerIAMPolicy \
  --policy-document file://iam_policy.json

# Note the ARN printed (arn:aws:iam::ACCOUNT:policy/AWSLoadBalancerControllerIAMPolicy)
# and paste it into eksctl-cluster.yaml where indicated.
```

### Step 3: Create the cluster (takes ~15 minutes)

```bash
eksctl create cluster -f k8s/eks/eksctl-cluster.yaml
```

This single command:
- Creates a VPC with public + private subnets across 3 AZs.
- Provisions the EKS control plane.
- Launches a managed node group with 2 × m5.large workers.
- Installs the 4 managed add-ons (vpc-cni, coredns, kube-proxy, ebs-csi-driver).
- Creates the IAM OIDC Identity Provider.
- Creates IRSA roles for the guestbook-app and ALB Controller ServiceAccounts.
- Configures your kubeconfig automatically.

### Step 4: Verify the cluster

```bash
# Should print the cluster details.
eksctl get cluster --name guestbook-eks

# Should show 2 worker nodes in Ready state.
kubectl get nodes -o wide

# Should show kube-system pods running.
kubectl get pods -n kube-system
```

Skip ahead to [Build and push the app image to ECR](#build-and-push-the-app-image-to-ecr).

---

## Happy path — Terraform

Use this path if you want Terraform to manage both the infrastructure and the
Helm chart for the ALB Controller in one plan.

### Step 1: Initialize

```bash
cd k8s/eks/terraform

# Download modules and providers (~1-2 minutes).
terraform init
```

### Step 2: Review the plan

```bash
# Optionally override defaults:
# terraform plan -var="aws_region=us-east-1" -var="cluster_name=guestbook-eks"

terraform plan -out=tfplan
```

Read the plan output carefully. You will see ~80 resources to create. Verify that
no existing resources are unexpectedly modified or destroyed.

### Step 3: Apply (takes ~15–20 minutes)

```bash
terraform apply tfplan
```

Terraform creates all infrastructure in the correct dependency order. The cluster
comes up first, then the node group, then the IRSA roles, then the Helm release.

### Step 4: Configure kubectl

```bash
# Terraform prints this command as an output. Copy and run it:
terraform output -raw kubeconfig_command | bash

# Or manually:
aws eks update-kubeconfig --region us-east-1 --name guestbook-eks
```

### Step 5: Note the IRSA role ARN

```bash
terraform output irsa_guestbook_app_role_arn
# Example: arn:aws:iam::123456789012:role/guestbook-eks-guestbook-app-irsa
```

Copy this ARN — you will paste it into the manifest patch in a later step.

---

## Build and push the app image to ECR

The base manifests reference `guestbook:1.0.0` (a locally built image). On EKS
the nodes can't reach your laptop's Docker daemon, so the image must live in a
registry the nodes can pull from. ECR is the natural choice: it's co-located with
the cluster, pulls are free and fast, and nodes use the node IAM role to authenticate.

### Step 1: Authenticate Docker to ECR

ECR uses short-lived passwords (12-hour tokens). This command pipes the token
directly into `docker login`:

```bash
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=$(aws configure get region)

aws ecr get-login-password --region ${AWS_REGION} | \
  docker login --username AWS --password-stdin \
  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com
```

### Step 2: Create the ECR repository (eksctl path only; Terraform creates it automatically)

```bash
aws ecr create-repository \
  --repository-name guestbook \
  --image-scanning-configuration scanOnPush=true \
  --region ${AWS_REGION}
```

### Step 3: Build, tag, and push

```bash
ECR_REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/guestbook"

# Build the image (run from the repo root so the Dockerfile context is correct).
docker build -t guestbook:1.0.0 k8s/app/

# Tag with the ECR URI.
docker tag guestbook:1.0.0 ${ECR_REPO}:1.0.0

# Push to ECR (~1-2 minutes depending on layer cache).
docker push ${ECR_REPO}:1.0.0

echo "Image pushed: ${ECR_REPO}:1.0.0"
```

### Step 4: Update the Kustomize overlay

Edit `k8s/eks/manifests/kustomization.yaml` and replace `TODO_ACCOUNT_ID` and
`TODO_REGION` in the `images:` section:

```bash
sed -i \
  "s/TODO_ACCOUNT_ID/${AWS_ACCOUNT_ID}/g; \
   s/TODO_REGION/${AWS_REGION}/g" \
  k8s/eks/manifests/kustomization.yaml
```

Verify:
```bash
grep "newName:" k8s/eks/manifests/kustomization.yaml
# Should print: newName: 123456789012.dkr.ecr.us-east-1.amazonaws.com/guestbook
```

---

## Install the AWS Load Balancer Controller

The AWS Load Balancer Controller is a Kubernetes controller that watches Ingress
and Service objects and creates/updates AWS Application Load Balancers. It is
NOT installed by default — you must install it as a Helm chart.

**If you used Terraform**, this step is done automatically. Skip to
[Set up IRSA](#set-up-irsa-iam-roles-for-service-accounts).

**If you used eksctl**, follow these steps:

### Step 1: Add the eks-charts Helm repository

```bash
helm repo add eks https://aws.github.io/eks-charts
helm repo update
```

### Step 2: Get the IRSA role ARN for the ALB Controller

eksctl created this role during cluster creation:

```bash
eksctl get iamserviceaccount \
  --cluster guestbook-eks \
  --namespace kube-system \
  --name aws-load-balancer-controller \
  --output json | jq -r '.[0].status.roleARN'
```

### Step 3: Install the chart

```bash
ALB_ROLE_ARN=$(eksctl get iamserviceaccount \
  --cluster guestbook-eks \
  --namespace kube-system \
  --name aws-load-balancer-controller \
  --output json | jq -r '.[0].status.roleARN')

helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
  --namespace kube-system \
  --set clusterName=guestbook-eks \
  --set serviceAccount.create=true \
  --set serviceAccount.name=aws-load-balancer-controller \
  --set "serviceAccount.annotations.eks\.amazonaws\.com/role-arn=${ALB_ROLE_ARN}" \
  --set replicaCount=2 \
  --version 1.8.1
```

### Step 4: Verify the controller is running

```bash
kubectl get deployment -n kube-system aws-load-balancer-controller
# READY should be 2/2

kubectl logs -n kube-system \
  -l app.kubernetes.io/name=aws-load-balancer-controller \
  --tail=20
```

---

## Install the EBS CSI driver add-on

The EBS CSI driver allows Kubernetes PersistentVolumeClaims to dynamically
provision EBS volumes. It is installed as an EKS **managed add-on**, which means
AWS handles patching and compatibility.

**If you used eksctl or Terraform**, the add-on is installed automatically as
part of cluster creation. Verify it is running:

```bash
kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-ebs-csi-driver
# You should see: ebs-csi-controller (2 pods) and ebs-csi-node (1 per node DaemonSet)
```

**To install it manually** (e.g. on an existing cluster):

```bash
# Create the IRSA role first (if not already created):
eksctl create iamserviceaccount \
  --name ebs-csi-controller-sa \
  --namespace kube-system \
  --cluster guestbook-eks \
  --attach-policy-arn arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy \
  --approve \
  --role-only \
  --role-name AmazonEKS_EBS_CSI_DriverRole

# Install the add-on:
aws eks create-addon \
  --cluster-name guestbook-eks \
  --addon-name aws-ebs-csi-driver \
  --service-account-role-arn \
    arn:aws:iam::${AWS_ACCOUNT_ID}:role/AmazonEKS_EBS_CSI_DriverRole
```

---

## Set up IRSA (IAM Roles for Service Accounts)

IRSA lets pods assume IAM roles without static credentials. The mechanism uses
the cluster's OIDC provider (created automatically by eksctl and Terraform) to
validate a short-lived token projected into each pod.

**If you used eksctl**, the IRSA roles were created by the `iam.serviceAccounts`
section in `eksctl-cluster.yaml`. Get the guestbook-app role ARN:

```bash
eksctl get iamserviceaccount \
  --cluster guestbook-eks \
  --namespace guestbook \
  --name guestbook-app \
  --output json | jq -r '.[0].status.roleARN'
```

**If you used Terraform**:

```bash
cd k8s/eks/terraform
terraform output irsa_guestbook_app_role_arn
```

### Patch the ServiceAccount manifest

Once you have the ARN, update the placeholder in the patch file:

```bash
IRSA_ROLE_ARN=arn:aws:iam::${AWS_ACCOUNT_ID}:role/guestbook-eks-guestbook-app-irsa

sed -i \
  "s|arn:aws:iam::TODO_ACCOUNT_ID:role/guestbook-eks-guestbook-app-irsa|${IRSA_ROLE_ARN}|g" \
  k8s/eks/manifests/serviceaccount-patch.yaml
```

---

## Deploy the application

With the cluster running, ECR image pushed, ALB Controller installed, and IRSA
role ARN filled in, deploy everything with a single kubectl command:

```bash
# Preview what will be created/changed:
kubectl diff -k k8s/eks/manifests

# Apply the overlay (Kustomize builds it in memory, pipes to kubectl apply):
kubectl apply -k k8s/eks/manifests
```

Watch the rollout:

```bash
# Watch pods come up:
kubectl get pods -n guestbook -w

# Check the StatefulSet (MongoDB):
kubectl rollout status statefulset/mongo -n guestbook

# Check the Deployment (app):
kubectl rollout status deployment/guestbook -n guestbook
```

The Job `seed-guestbook` runs once to insert a welcome message. It should
complete within 30 seconds of MongoDB becoming ready.

---

## Verify and test

### Step 1: Get the ALB DNS name

The ALB Controller provisions the load balancer asynchronously. It takes
1–3 minutes for the ALB to become active.

```bash
# Wait for the ADDRESS field to be populated:
kubectl get ingress -n guestbook guestbook -w

# Once it shows an address, export it:
ALB_DNS=$(kubectl get ingress -n guestbook guestbook \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
echo "ALB DNS: ${ALB_DNS}"
```

### Step 2: Test the endpoints

```bash
# Liveness probe (no external dependencies):
curl http://${ALB_DNS}/healthz
# Expected: {"status":"alive","pod":"guestbook-XXXXXXX","version":"1.0.0"}

# Readiness probe (checks MongoDB):
curl http://${ALB_DNS}/readyz
# Expected: {"status":"ready","pod":"guestbook-XXXXXXX","mongo":"up"}

# List guestbook messages (seeded by the Job):
curl http://${ALB_DNS}/api/messages | python3 -m json.tool

# Add a message:
curl -X POST http://${ALB_DNS}/api/messages \
  -H 'Content-Type: application/json' \
  -d '{"author":"student","text":"Hello from EKS!"}'

# Which pod served the request?
curl http://${ALB_DNS}/api/info

# Open the Swagger UI in a browser:
echo "Open: http://${ALB_DNS}/docs"
```

### Step 3: Verify IRSA is working

```bash
# Exec into an app pod and check the AWS token is projected:
APP_POD=$(kubectl get pod -n guestbook -l app.kubernetes.io/name=guestbook \
  -o jsonpath='{.items[0].metadata.name}')

kubectl exec -n guestbook ${APP_POD} -- \
  ls /var/run/secrets/eks.amazonaws.com/serviceaccount/
# Should list: token

# Test the AWS identity (requires AWS CLI in the container -- for debug only):
# kubectl exec -n guestbook ${APP_POD} -- aws sts get-caller-identity
```

### Step 4: Test autoscaling

```bash
# Generate load (requires `hey` or `ab`):
hey -n 10000 -c 50 http://${ALB_DNS}/healthz

# Watch the HPA scale up:
kubectl get hpa -n guestbook -w

# Watch new pods appear:
kubectl get pods -n guestbook -w
```

---

## Teardown

> **Run this when you are done.** EKS, EC2, NAT gateways, and ALBs all accrue
> charges every hour they exist.

### eksctl teardown

```bash
# Delete the cluster and ALL associated resources (VPC, node group, IAM roles,
# CloudFormation stacks). This takes ~10 minutes.
eksctl delete cluster -f k8s/eks/eksctl-cluster.yaml

# Delete the ECR repository (and all images inside it):
aws ecr delete-repository --repository-name guestbook --force --region ${AWS_REGION}

# Delete the ALB Controller IAM policy:
aws iam delete-policy \
  --policy-arn arn:aws:iam::${AWS_ACCOUNT_ID}:policy/AWSLoadBalancerControllerIAMPolicy
```

### Terraform teardown

```bash
cd k8s/eks/terraform

# Destroy all resources in reverse dependency order (~10-15 minutes):
terraform destroy

# You will be prompted to confirm. Review the list and type `yes`.
```

### Verify teardown

After teardown, verify no resources are left running:

```bash
# No EKS clusters:
aws eks list-clusters

# No load balancers (the ALB should have been deleted with the cluster):
aws elbv2 describe-load-balancers --query 'LoadBalancers[?Tags[?Key==`project` && Value==`guestbook`]]'

# No lingering EBS volumes (PVCs should have been deleted with the cluster):
aws ec2 describe-volumes --filters Name=tag:project,Values=guestbook
```

---

## Troubleshooting

### Pods stuck in `Pending`

```bash
kubectl describe pod -n guestbook <pod-name>
# Look for: "0/2 nodes are available" -- means node group isn't ready yet, wait.
# Look for: "failed to create volume" -- EBS CSI IRSA issue; check the role ARN.
```

### ALB not created / Ingress ADDRESS is empty

```bash
# Check the ALB Controller logs:
kubectl logs -n kube-system \
  -l app.kubernetes.io/name=aws-load-balancer-controller \
  --tail=50

# Common causes:
# 1. Subnets not tagged with kubernetes.io/role/elb=1 (eksctl + Terraform handle this)
# 2. ALB Controller ServiceAccount missing the IRSA annotation
# 3. Security group not allowing inbound traffic on port 80
```

### `ImagePullBackOff`

```bash
kubectl describe pod -n guestbook <pod-name>
# Check the image URI in the error -- should be the ECR URI, not guestbook:1.0.0
# Check that the node IAM role has ecr:GetAuthorizationToken + ecr:BatchGetImage
# The managed node group gets these policies via the managed node group role automatically.
```

### IRSA / AWS API calls failing inside the pod

```bash
# Check the annotation is present on the ServiceAccount:
kubectl get sa -n guestbook guestbook-app -o yaml | grep role-arn

# Check the role ARN is correct (account ID, region, role name):
aws iam get-role --role-name guestbook-eks-guestbook-app-irsa

# Check the trust policy references the correct cluster OIDC issuer:
aws iam get-role --role-name guestbook-eks-guestbook-app-irsa \
  --query 'Role.AssumeRolePolicyDocument'
```

### MongoDB PVC stuck in `Pending`

```bash
kubectl describe pvc -n guestbook data-mongo-0
# "no persistent volumes available" -- EBS CSI not installed or gp3 SC not default
# Check: kubectl get storageclass
# Check: kubectl get pods -n kube-system -l app=ebs-csi-controller
```

### Cluster creation fails with CloudFormation timeout

eksctl operations are implemented as CloudFormation stacks. If a stack times out:

```bash
# List CloudFormation stacks:
aws cloudformation list-stacks --stack-status-filter CREATE_FAILED ROLLBACK_IN_PROGRESS

# View events for the failed stack:
aws cloudformation describe-stack-events \
  --stack-name eksctl-guestbook-eks-cluster \
  --query 'StackEvents[?ResourceStatus==`CREATE_FAILED`]'
```

---

## Placeholders to fill in before use

The following values are set to `TODO_*` placeholders in the manifests and must
be replaced with real values:

| File | Placeholder | How to get the value |
|---|---|---|
| `eksctl-cluster.yaml` | `TODO_ACCOUNT_ID` | `aws sts get-caller-identity --query Account --output text` |
| `eksctl-cluster.yaml` | `TODO_ACCOUNT_ID` (SSM resource ARN) | same |
| `manifests/kustomization.yaml` | `TODO_ACCOUNT_ID` | same |
| `manifests/kustomization.yaml` | `TODO_REGION` | `aws configure get region` |
| `manifests/serviceaccount-patch.yaml` | `TODO_ACCOUNT_ID` | same |
| `manifests/serviceaccount-patch.yaml` | `guestbook-eks-guestbook-app-irsa` (role name) | eksctl: `eksctl get iamserviceaccount`; TF: `terraform output irsa_guestbook_app_role_arn` |
