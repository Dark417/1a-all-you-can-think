# =============================================================================
# versions.tf — Pin Terraform core and provider versions.
#
# WHY pin?  Floating versions ("~> 5") can silently pull in breaking changes
# across teams or CI runs. These pins are current as of mid-2025; bump them
# deliberately after reading the provider/module changelogs.
# =============================================================================

terraform {
  required_version = ">= 1.7.0"

  required_providers {
    google = {
      # hashicorp/google covers the core GCP resources (GKE, networking, IAM).
      source  = "hashicorp/google"
      version = "~> 5.30"
    }
    google-beta = {
      # Some GKE features (Gateway API, Dataplane V2 tuning) land in beta first.
      source  = "hashicorp/google-beta"
      version = "~> 5.30"
    }
  }

  # ---------------------------------------------------------------------------
  # Remote state (recommended for team usage).
  # Uncomment and fill in your GCS bucket to store state remotely so multiple
  # engineers can share and lock it.  Without this, state is local only.
  # ---------------------------------------------------------------------------
  # backend "gcs" {
  #   bucket = "YOUR_TF_STATE_BUCKET"   # must already exist
  #   prefix = "gke/guestbook"
  # }
}

# Configure the default google provider with project and region so individual
# resources don't have to repeat them.
provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}
