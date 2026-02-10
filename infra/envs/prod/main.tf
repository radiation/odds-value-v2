locals {
  required_services = [
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "secretmanager.googleapis.com",
    "sqladmin.googleapis.com",
    "iam.googleapis.com",
    "cloudscheduler.googleapis.com",
  ]
}

resource "google_project_service" "services" {
  for_each = toset(local.required_services)

  service            = each.value
  disable_on_destroy = false
}

# -----------------------------
# Artifact Registry (Docker)
# -----------------------------
resource "google_artifact_registry_repository" "docker" {
  location      = var.region
  repository_id = var.artifact_repo_id
  description   = "Odds Value container images"
  format        = "DOCKER"

  depends_on = [google_project_service.services]
}

# -----------------------------
# Service account for Cloud Run Jobs
# -----------------------------
resource "google_service_account" "run_jobs" {
  account_id   = "run-jobs"
  display_name = "Cloud Run Jobs service account"
}

resource "google_project_iam_member" "run_jobs_logwriter" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.run_jobs.email}"
}

# Allow jobs SA to read secrets
resource "google_project_iam_member" "run_jobs_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.run_jobs.email}"
}

# -----------------------------
# Cloud SQL (Postgres)
# NOTE: public IP enabled by default here for fastest bootstrap.
# We'll tighten to private IP + VPC connector next if you want.
# -----------------------------
resource "google_sql_database_instance" "postgres" {
  name             = var.db_instance_name
  region           = var.region
  database_version = "POSTGRES_16"

  settings {
    edition = "ENTERPRISE"
    tier    = "db-g1-small"

    backup_configuration {
      enabled = true
    }

    ip_configuration {
      ipv4_enabled = true
    }
  }

  deletion_protection = true

  depends_on = [google_project_service.services]
}


resource "google_sql_database" "app_db" {
  name     = var.db_name
  instance = google_sql_database_instance.postgres.name
}

resource "random_password" "db_password" {
  count   = var.db_password == null ? 1 : 0
  length  = 24
  special = true
}

locals {
  effective_db_password = var.db_password != null ? var.db_password : random_password.db_password[0].result
}

resource "google_sql_user" "app_user" {
  name     = var.db_user
  instance = google_sql_database_instance.postgres.name
  password = local.effective_db_password
}

# -----------------------------
# Secrets
# -----------------------------
resource "google_secret_manager_secret" "db_password" {
  secret_id = "DB_PASSWORD"
  replication {
    auto {}
  }

  depends_on = [google_project_service.services]
}

resource "google_secret_manager_secret_version" "db_password_v1" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = local.effective_db_password
}

resource "google_secret_manager_secret" "database_url" {
  secret_id = "DATABASE_URL"
  replication {
    auto {}
  }

  depends_on = [google_project_service.services]
}

resource "google_secret_manager_secret_version" "database_url_v1" {
  secret = google_secret_manager_secret.database_url.id
  secret_data = format(
    "postgresql+psycopg://%s:%s@localhost:5432/%s",
    var.db_user,
    urlencode(local.effective_db_password),
    var.db_name
  )
}

