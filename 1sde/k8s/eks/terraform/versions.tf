# =============================================================================
# versions.tf -- provider and module version constraints.
#
# WHY pin versions?
#   Terraform and provider releases sometimes introduce breaking changes.
#   Explicit lower-bounds (>=) combined with an upper cap (~> or <) ensure
#   `terraform init` always fetches a tested, compatible combination regardless
#   of when someone clones this repo.
#
# Update strategy:
#   1. Bump the version constraint here.
#   2. Run `terraform init -upgrade`.
#   3. Run `terraform plan` and review the diff before applying.
# =============================================================================
terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      # 5.x is the current stable major. ~> 5.50 allows 5.50+ but not 6.x.
      version = "~> 5.50"
    }
    # The Kubernetes provider lets Terraform manage K8s resources directly
    # (e.g. the aws-auth ConfigMap, Namespace, ServiceAccount annotations).
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.30"
    }
    # helm provider -- used to install the AWS Load Balancer Controller chart.
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.13"
    }
    # TLS provider -- needed by the OIDC thumbprint data source.
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }

  # ---------------------------------------------------------------------------
  # Remote state (recommended for real use -- commented out for the demo).
  # Storing state in S3 + DynamoDB locking enables team collaboration and
  # prevents two people from running `terraform apply` simultaneously.
  # ---------------------------------------------------------------------------
  # backend "s3" {
  #   bucket         = "TODO-your-tfstate-bucket"
  #   key            = "guestbook/eks/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "terraform-locks"
  #   encrypt        = true
  # }
}
