# =============================================================================
# variables.tf -- all tuneable parameters for this Terraform configuration.
#
# Design principle: keep variables to the things you actually expect to differ
# between deployments (region, name, size). Hard-code anything that is always
# the same so reviewers don't need to track down the value.
# =============================================================================

variable "aws_region" {
  description = "AWS region where the cluster and VPC will be created."
  type        = string
  default     = "us-east-1"
  # Override on the CLI: terraform apply -var="aws_region=eu-west-1"
  # Or via TF_VAR_aws_region environment variable.
}

variable "cluster_name" {
  description = "Name of the EKS cluster. Used as a prefix for all resources."
  type        = string
  default     = "guestbook-eks"
}

variable "cluster_version" {
  description = <<-EOT
    EKS Kubernetes version to deploy. AWS supports the three most recent minor
    versions; check https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html.
    Pinned here to avoid surprise upgrades when AWS adds a new default.
  EOT
  type        = string
  default     = "1.30"
}

# ---------------------------------------------------------------------------
# Networking
# ---------------------------------------------------------------------------
variable "vpc_cidr" {
  description = <<-EOT
    CIDR block for the new VPC. The VPC module sub-divides this into public
    and private subnets across the AZs in the selected region.
    /16 gives 65 535 IPs -- plenty for a demo; tune for production.
  EOT
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = <<-EOT
    List of AZs to use. Three AZs are recommended for production HA.
    Two AZs save ~$32/mo in NAT gateway costs (one fewer gateway).
    Must be within var.aws_region.
  EOT
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

# ---------------------------------------------------------------------------
# Node group
# ---------------------------------------------------------------------------
variable "node_instance_type" {
  description = <<-EOT
    EC2 instance type for worker nodes.
      m5.large  -- 2 vCPU / 8 GB  -- good all-round for demos
      t3.medium -- 2 vCPU / 4 GB  -- cheapest that runs this workload comfortably
    Avoid t3 for sustained CPU workloads; the burst model throttles the app.
  EOT
  type        = string
  default     = "m5.large"
}

variable "node_min_size" {
  description = "Minimum number of worker nodes in the managed node group."
  type        = number
  default     = 2
}

variable "node_desired_size" {
  description = "Initial (desired) number of worker nodes."
  type        = number
  default     = 2
}

variable "node_max_size" {
  description = "Maximum number of worker nodes (Cluster Autoscaler ceiling)."
  type        = number
  default     = 4
}

variable "node_disk_size" {
  description = "Root EBS volume size in GiB for each worker node."
  type        = number
  default     = 20
}

# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------
variable "tags" {
  description = "Tags applied to every resource created by this configuration."
  type        = map(string)
  default = {
    project    = "guestbook"
    env        = "demo"
    managed-by = "terraform"
  }
}
