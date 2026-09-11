# =============================================================================
# outputs.tf — Values printed after `terraform apply` and queryable with
#              `terraform output`.
#
# These are the essential references you'll need to configure kubectl, build
# and push images, and annotate the Kubernetes ServiceAccount.
# =============================================================================

output "cluster_name" {
  description = "Name of the GKE cluster."
  value       = google_container_cluster.primary.name
}

output "cluster_location" {
  description = "GCP region (or zone) where the cluster is located."
  value       = google_container_cluster.primary.location
}

output "cluster_endpoint" {
  description = <<-EOT
    The HTTPS endpoint of the Kubernetes API server.
    Use with: gcloud container clusters get-credentials $(tf output -raw cluster_name) --region ...
  EOT
  value     = "https://${google_container_cluster.primary.endpoint}"
  sensitive = true   # contains an IP; mark sensitive to avoid accidental logging
}

output "kubeconfig_command" {
  description = "Run this command to configure kubectl for the new cluster."
  value = "gcloud container clusters get-credentials ${google_container_cluster.primary.name} --region ${google_container_cluster.primary.location} --project ${var.project_id}"
}

output "gsa_email" {
  description = <<-EOT
    Email of the Google Service Account created for Workload Identity.
    Paste this into manifests/serviceaccount-patch.yaml as the value of
    the iam.gke.io/gcp-service-account annotation.
  EOT
  value = google_service_account.guestbook_app.email
}

output "artifact_registry_hostname" {
  description = <<-EOT
    Hostname prefix for pushing images to Artifact Registry.
    Tag your image: REGION-docker.pkg.dev/PROJECT/REPO/guestbook:1.0.0
  EOT
  value = "${var.artifact_registry_region}-docker.pkg.dev"
}

output "image_push_tag" {
  description = "Full image tag to use when building and pushing the guestbook image."
  value       = "${var.artifact_registry_region}-docker.pkg.dev/${var.project_id}/${var.artifact_registry_repo}/guestbook:1.0.0"
}

output "vpc_network_name" {
  description = "Name of the VPC network created for the cluster."
  value       = google_compute_network.vpc.name
}

output "subnet_name" {
  description = "Name of the subnet created for cluster nodes."
  value       = google_compute_subnetwork.subnet.name
}
