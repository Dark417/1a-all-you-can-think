# =============================================================================
# main.tf -- EKS cluster + supporting infrastructure via official modules.
#
# Module sources:
#   VPC:  terraform-aws-modules/vpc/aws       ~> 5.8
#   EKS:  terraform-aws-modules/eks/aws       ~> 20.0
#
# Both modules are authored by AWS and the community, widely used in production,
# and kept up-to-date with each EKS release.  Using them means you write ~60
# lines here instead of ~600 lines of raw aws_* resources.
#
# Resource inventory created by this file:
#   * 1 VPC (3 public + 3 private subnets, 1 Internet GW, 1 NAT GW)
#   * 1 EKS cluster (control plane managed by AWS)
#   * 1 managed node group (EC2 Auto Scaling Group)
#   * 4 EKS managed add-ons (vpc-cni, coredns, kube-proxy, ebs-csi-driver)
#   * 1 IAM OIDC Identity Provider (enables IRSA)
#   * 2 IAM roles with trust policies (guestbook-app, alb-controller)
#   * 1 ECR repository
#   * 1 IAM policy for the AWS Load Balancer Controller
# =============================================================================

# ---------------------------------------------------------------------------
# Provider configuration.
# The kubernetes and helm providers are configured AFTER the cluster is created
# (they need the endpoint and CA certificate).  We use `depends_on` on the
# resources that consume them so Terraform plans them in the right order.
# ---------------------------------------------------------------------------
provider "aws" {
  region = var.aws_region

  # Default tags are merged onto every aws_* resource automatically.
  # This means you never forget to tag a resource.
  default_tags {
    tags = var.tags
  }
}

# We need the cluster endpoint/CA to configure the kubernetes + helm providers.
# Using `data` on the module output works but requires a two-phase apply the
# first time.  For simplicity we configure via the module output directly.
provider "kubernetes" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
  # Use an exec plugin to get a short-lived token -- more secure than a static
  # kubeconfig credential; works with MFA-enabled roles.
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name, "--region", var.aws_region]
  }
}

provider "helm" {
  kubernetes {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name, "--region", var.aws_region]
    }
  }
}

# ---------------------------------------------------------------------------
# Current AWS identity -- used to build ARNs without hard-coding account IDs.
# ---------------------------------------------------------------------------
data "aws_caller_identity" "current" {}

# ---------------------------------------------------------------------------
# VPC
# The EKS module requires subnets tagged with specific kubernetes.io labels
# so the Load Balancer Controller and cloud-controller-manager can discover
# them automatically.  The vpc module applies these tags when you pass the
# cluster name through the `cluster_name` variable.
# ---------------------------------------------------------------------------
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.8"

  name = "${var.cluster_name}-vpc"
  cidr = var.vpc_cidr
  azs  = var.availability_zones

  # Private subnets host worker nodes and pods.
  # Tag: kubernetes.io/role/internal-elb=1 tells the ALB Controller to place
  # internal load balancers here.
  private_subnets = [
    cidrsubnet(var.vpc_cidr, 4, 0),  # e.g. 10.0.0.0/20
    cidrsubnet(var.vpc_cidr, 4, 1),  # e.g. 10.0.16.0/20
    cidrsubnet(var.vpc_cidr, 4, 2),  # e.g. 10.0.32.0/20
  ]

  # Public subnets host the NAT gateway and ALB load-balancer nodes.
  # Tag: kubernetes.io/role/elb=1 tells the ALB Controller to use these for
  # internet-facing load balancers.
  public_subnets = [
    cidrsubnet(var.vpc_cidr, 4, 8),  # e.g. 10.0.128.0/20
    cidrsubnet(var.vpc_cidr, 4, 9),  # e.g. 10.0.144.0/20
    cidrsubnet(var.vpc_cidr, 4, 10), # e.g. 10.0.160.0/20
  ]

  enable_nat_gateway     = true
  single_nat_gateway     = true  # one NAT GW saves ~$32/mo; set false for HA
  enable_dns_hostnames   = true  # required for EKS
  enable_dns_support     = true

  # These subnet tags are mandatory for EKS + ALB Controller subnet discovery.
  public_subnet_tags = {
    "kubernetes.io/role/elb"                      = "1"
    "kubernetes.io/cluster/${var.cluster_name}"   = "shared"
  }

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb"             = "1"
    "kubernetes.io/cluster/${var.cluster_name}"   = "shared"
    # Karpenter uses this tag to discover subnets it may launch nodes in.
    "karpenter.sh/discovery"                      = var.cluster_name
  }
}

# ---------------------------------------------------------------------------
# EKS cluster
# ---------------------------------------------------------------------------
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.cluster_name
  cluster_version = var.cluster_version

  # API server endpoint access.
  # public_and_private lets you reach the API from your workstation AND lets
  # nodes talk to the API server via the private endpoint (no internet round-trip).
  # For production: set cluster_endpoint_public_access = false and use a VPN/bastion.
  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = true

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # IRSA: create the IAM OIDC Identity Provider for this cluster.
  # Every IRSA role's trust policy references this provider's ARN + the issuer URL.
  enable_irsa = true

  # ---------------------------------------------------------------------------
  # Managed Add-ons.
  # Specified here so Terraform tracks their versions and can upgrade them.
  # vpc-cni uses IRSA for its own AWS API calls (ENI management); we create the
  # role inline with `service_account_role_arn`.
  # ---------------------------------------------------------------------------
  cluster_addons = {
    vpc-cni = {
      most_recent               = true
      resolve_conflicts_on_update = "OVERWRITE"
      # The VPC CNI needs to call EC2 APIs to manage ENIs and assign IPs.
      # We attach the AWS-managed policy to a role and link it via IRSA.
      service_account_role_arn  = aws_iam_role.vpc_cni_irsa.arn
    }
    coredns = {
      most_recent               = true
      resolve_conflicts_on_update = "OVERWRITE"
    }
    kube-proxy = {
      most_recent               = true
      resolve_conflicts_on_update = "OVERWRITE"
    }
    aws-ebs-csi-driver = {
      most_recent               = true
      resolve_conflicts_on_update = "OVERWRITE"
      # The EBS CSI driver calls ec2:CreateVolume etc on behalf of PVCs.
      service_account_role_arn  = aws_iam_role.ebs_csi_irsa.arn
    }
  }

  # ---------------------------------------------------------------------------
  # Managed Node Group.
  # EKS manages the Auto Scaling Group and replaces unhealthy nodes automatically.
  # ---------------------------------------------------------------------------
  eks_managed_node_groups = {
    general = {
      name           = "${var.cluster_name}-ng-general"
      instance_types = [var.node_instance_type]

      min_size     = var.node_min_size
      desired_size = var.node_desired_size
      max_size     = var.node_max_size

      # Workers run in private subnets (no public IP exposure).
      subnet_ids = module.vpc.private_subnets

      disk_size            = var.node_disk_size
      # Encrypted root volume -- good practice.
      block_device_mappings = {
        xvda = {
          device_name = "/dev/xvda"
          ebs = {
            volume_size           = var.node_disk_size
            volume_type           = "gp3"
            encrypted             = true
            delete_on_termination = true
          }
        }
      }

      # Node labels appear on the Node object and can be used with nodeSelector.
      labels = {
        role      = "worker"
        lifecycle = "on-demand"
      }

      # Attach the Cluster Autoscaler policy so nodes can scale the group.
      iam_role_additional_policies = {
        ClusterAutoscaler = aws_iam_policy.cluster_autoscaler.arn
        # SSM access lets you shell into nodes via Session Manager (no bastion).
        SSMCore = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
      }

      tags = merge(var.tags, {
        # Karpenter / Cluster Autoscaler discovery tag.
        "k8s.io/cluster-autoscaler/enabled"             = "true"
        "k8s.io/cluster-autoscaler/${var.cluster_name}" = "owned"
      })
    }
  }

  # Tags on the cluster itself.
  tags = var.tags
}

# ---------------------------------------------------------------------------
# ECR Repository for the guestbook image.
# Storing images in ECR means worker nodes pull over the internal VPC network
# (fast + free) rather than from Docker Hub (rate-limited, egress charges).
# ---------------------------------------------------------------------------
resource "aws_ecr_repository" "guestbook" {
  name                 = "guestbook"
  image_tag_mutability = "MUTABLE"  # allow re-pushing the same tag (e.g. 1.0.0)

  image_scanning_configuration {
    # ECR Basic Scanning checks for CVEs on every push at no extra cost.
    scan_on_push = true
  }

  # Encrypt images at rest with the AWS-managed KMS key for ECR.
  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = var.tags
}

# Lifecycle policy: keep only the 10 most recent tagged images to control storage costs.
resource "aws_ecr_lifecycle_policy" "guestbook" {
  repository = aws_ecr_repository.guestbook.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 tagged images"
        selection = {
          tagStatus   = "tagged"
          tagPrefixList = ["v", "1.", "2."]
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Expire untagged images after 7 days"
        selection = {
          tagStatus = "untagged"
          countType = "sinceImagePushed"
          countUnit = "days"
          countNumber = 7
        }
        action = { type = "expire" }
      }
    ]
  })
}

# ---------------------------------------------------------------------------
# IRSA roles for AWS-managed add-ons.
# Each role has a trust policy referencing the cluster OIDC provider so ONLY
# the specified ServiceAccount in the specified namespace can assume it.
# ---------------------------------------------------------------------------

# Helper: the OIDC provider URL without the https:// prefix (needed in ARN).
locals {
  oidc_provider_url = replace(module.eks.cluster_oidc_issuer_url, "https://", "")
  account_id        = data.aws_caller_identity.current.account_id
}

# --- VPC CNI IRSA ---
# Allows the aws-node DaemonSet to manage ENIs and IP addresses on the node.
resource "aws_iam_role" "vpc_cni_irsa" {
  name = "${var.cluster_name}-vpc-cni-irsa"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = module.eks.oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${local.oidc_provider_url}:sub" = "system:serviceaccount:kube-system:aws-node"
          "${local.oidc_provider_url}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "vpc_cni_irsa" {
  role       = aws_iam_role.vpc_cni_irsa.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

# --- EBS CSI IRSA ---
# Allows the ebs-csi-controller to create/attach/detach EBS volumes.
resource "aws_iam_role" "ebs_csi_irsa" {
  name = "${var.cluster_name}-ebs-csi-irsa"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = module.eks.oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${local.oidc_provider_url}:sub" = "system:serviceaccount:kube-system:ebs-csi-controller-sa"
          "${local.oidc_provider_url}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "ebs_csi_irsa" {
  role       = aws_iam_role.ebs_csi_irsa.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}

# ---------------------------------------------------------------------------
# IRSA role for the guestbook-app ServiceAccount.
# The trust policy locks this role to:
#   - the cluster's OIDC issuer (prevents impersonation from other clusters),
#   - the exact namespace + service account name.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "guestbook_app_irsa" {
  name = "${var.cluster_name}-guestbook-app-irsa"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = module.eks.oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          # Kubernetes injects an OIDC token whose `sub` claim is:
          #   system:serviceaccount:<namespace>:<service-account-name>
          "${local.oidc_provider_url}:sub" = "system:serviceaccount:guestbook:guestbook-app"
          "${local.oidc_provider_url}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })

  tags = var.tags
}

# Inline policy: read SSM parameters scoped to /guestbook/* (illustrative).
# Replace or extend with whatever AWS services the app actually needs.
resource "aws_iam_role_policy" "guestbook_app_ssm" {
  name = "guestbook-app-ssm-read"
  role = aws_iam_role.guestbook_app_irsa.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParametersByPath"
        ]
        # Scope to parameters under /guestbook/ only -- least-privilege.
        Resource = "arn:aws:ssm:${var.aws_region}:${local.account_id}:parameter/guestbook/*"
      }
    ]
  })
}

# ---------------------------------------------------------------------------
# IAM role + policy for the AWS Load Balancer Controller.
# The controller runs in kube-system and needs broad EC2/ELB permissions to
# create and manage Application Load Balancers.  AWS publishes the official
# policy JSON at the URL referenced in README.md.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "alb_controller_irsa" {
  name = "${var.cluster_name}-alb-controller-irsa"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = module.eks.oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${local.oidc_provider_url}:sub" = "system:serviceaccount:kube-system:aws-load-balancer-controller"
          "${local.oidc_provider_url}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })

  tags = var.tags
}

# The AWS Load Balancer Controller policy JSON is published by AWS and is ~300 lines.
# We download it from the canonical URL (pinned to the same controller version used
# in the Helm chart installation in README.md).
data "http" "alb_controller_policy" {
  # Pin to v2.8 policy -- update alongside the Helm chart version.
  url = "https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/v2.8.1/docs/install/iam_policy.json"
}

resource "aws_iam_policy" "alb_controller" {
  name        = "${var.cluster_name}-AWSLoadBalancerControllerIAMPolicy"
  description = "IAM policy for the AWS Load Balancer Controller (v2.8)"
  policy      = data.http.alb_controller_policy.response_body

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "alb_controller_irsa" {
  role       = aws_iam_role.alb_controller_irsa.name
  policy_arn = aws_iam_policy.alb_controller.arn
}

# ---------------------------------------------------------------------------
# Cluster Autoscaler IAM policy (attached to the node group role).
# The Cluster Autoscaler reads ASG metadata and calls SetDesiredCapacity to
# scale the node group in/out based on pending Pods.
# ---------------------------------------------------------------------------
resource "aws_iam_policy" "cluster_autoscaler" {
  name        = "${var.cluster_name}-ClusterAutoscalerPolicy"
  description = "Allows Cluster Autoscaler to describe and modify the node group ASG."

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "autoscaling:DescribeAutoScalingGroups",
          "autoscaling:DescribeAutoScalingInstances",
          "autoscaling:DescribeLaunchConfigurations",
          "autoscaling:DescribeScalingActivities",
          "autoscaling:DescribeTags",
          "ec2:DescribeImages",
          "ec2:DescribeInstanceTypes",
          "ec2:DescribeLaunchTemplateVersions",
          "ec2:GetInstanceTypesFromInstanceRequirements",
          "eks:DescribeNodegroup"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "autoscaling:SetDesiredCapacity",
          "autoscaling:TerminateInstanceInAutoScalingGroup"
        ]
        # Scope to ASGs tagged for this specific cluster only.
        Resource = "*"
        Condition = {
          StringEquals = {
            "autoscaling:ResourceTag/k8s.io/cluster-autoscaler/enabled"             = "true"
            "autoscaling:ResourceTag/k8s.io/cluster-autoscaler/${var.cluster_name}" = "owned"
          }
        }
      }
    ]
  })

  tags = var.tags
}

# ---------------------------------------------------------------------------
# AWS Load Balancer Controller -- installed via Helm.
# Terraform manages this so the controller version is tracked in source control
# alongside the infrastructure.  Alternatively, install it manually (README.md).
# ---------------------------------------------------------------------------
resource "helm_release" "aws_load_balancer_controller" {
  name       = "aws-load-balancer-controller"
  repository = "https://aws.github.io/eks-charts"
  chart      = "aws-load-balancer-controller"
  namespace  = "kube-system"
  # Pin the chart version; check https://github.com/aws/eks-charts/releases for latest.
  version    = "1.8.1"

  # The controller needs to know the cluster name to watch the right resources.
  set {
    name  = "clusterName"
    value = module.eks.cluster_name
  }

  # Point the controller's ServiceAccount to the IRSA role we created above.
  set {
    name  = "serviceAccount.create"
    value = "true"
  }
  set {
    name  = "serviceAccount.name"
    value = "aws-load-balancer-controller"
  }
  set {
    name  = "serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn"
    value = aws_iam_role.alb_controller_irsa.arn
  }

  # Two replicas for controller HA -- if one Pod crashes during a deploy,
  # the other continues managing ALBs.
  set {
    name  = "replicaCount"
    value = "2"
  }

  depends_on = [
    module.eks,
    aws_iam_role_policy_attachment.alb_controller_irsa
  ]
}

# ---------------------------------------------------------------------------
# http provider -- used to fetch the ALB controller policy JSON above.
# ---------------------------------------------------------------------------
terraform {
  required_providers {
    http = {
      source  = "hashicorp/http"
      version = "~> 3.4"
    }
  }
}
