output "artifact_registry_repo" {
  value = google_artifact_registry_repository.docker.name
}

output "cloud_sql_instance_connection_name" {
  value = google_sql_database_instance.postgres.connection_name
}

output "run_jobs_service_account" {
  value = google_service_account.run_jobs.email
}
