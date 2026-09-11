# =============================================================================
# outputs.tf -- values printed after `terraform apply` and readable with
#               `terraform output`.
#
# Outputs serve two purposes:
#   1. Human convenience: the cluster name / endpoint appear in the terminal
#      so you can copy-paste them into kubectl or shell scripts.
#   2. Module chaining: if another Terraform module consumes this one, it can
#      reference these outputs with `module.eks_cluster.<output_name>`.
# =============================================================================

output "cluster_name" {
  description = "EKS cluster name. Use in: aws eks update-kubeconfig --name <value>"
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "API server endpoint URL. Your kubeconfig points kubectl here."
  value       = module.eks.cluster_endpoint
  # The endpoint itself is not secret, but treat it as sensitive so it doesn't
  # appear in CI logs by accident.
  sensitive   = false
}

output "cluster_certificate_authority_data" {
  description = "Base64-encoded CA certificate used by kubectl to verify the API server TLS cert."
  value       = module.eks.cluster_certificate_authority_data
  sensitive   = true
}

output "cluster_oidc_issuer_url" {
  description = <<-EOT
    OIDC issuer URL for this cluster. Used when creating IAM roles that trust
    K8s service accounts (IRSA). Format:
      https://oidc.eks.<region>.amazonaws.com/id/<hex-id>
  EOT
  value       = module.eks.cluster_oidc_issuer_url
}

output "oidc_provider_arn" {
  description = <<-EOT
    ARN of the IAM OIDC Identity Provider. Paste this into the trust policy of
    any IAM role you want a Kubernetes ServiceAccount to assume.
  EOT
  value       = module.eks.oidc_provider_arn
}

output "node_group_role_arn" {
  description = "IAM role ARN used by worker nodes. Needed for the aws-auth ConfigMap."
  value       = module.eks.eks_managed_node_groups["general"].iam_role_arn
}

output "vpc_id" {
  description = "ID of the VPC created for the cluster."
  value       = module.vpc.vpc_id
}

output "private_subnet_ids" {
  description = "Private subnet IDs. Worker nodes and pods live here."
  value       = module.vpc.private_subnets
}

output "public_subnet_ids" {
  description = <<-EOT
    Public subnet IDs. The AWS Load Balancer Controller places ALB nodes here
    (internet-facing ALBs must have at least two public subnets).
    Tag: kubernetes.io/role/elb=1 is set automatically by the VPC module.
  EOT
  value       = module.vpc.public_subnets
}

output "ecr_repository_url" {
  description = <<-EOT
    ECR repository URL for the guestbook image. Push with:
      docker tag guestbook:1.0.0 <value>:1.0.0
      docker push <value>:1.0.0
    Then update the image in the Kustomize overlay.
  EOT
  value       = aws_ecr_repository.guestbook.repository_url
}

output "kubeconfig_command" {
  description = "Run this command to configure kubectl after `terraform apply`."
  value       = "aws eks update-kubeconfig --region ${var.aws_region} --name ${module.eks.cluster_name}"
}

output "irsa_guestbook_app_role_arn" {
  description = <<-EOT
    IAM role ARN for the guestbook-app IRSA ServiceAccount. Paste this as the
    `eks.amazonaws.com/role-arn` annotation value in manifests/serviceaccount-patch.yaml.
  EOT
  value       = aws_iam_role.guestbook_app_irsa.arn
}

output "irsa_alb_controller_role_arn" {
  description = <<-EOT
    IAM role ARN for the AWS Load Balancer Controller IRSA. Paste this into the
    Helm values (serviceAccount.annotations) when installing the chart.
  EOT
  value       = aws_iam_role.alb_controller_irsa.arn
}
