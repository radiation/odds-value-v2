variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-east1"
}

variable "artifact_repo_id" {
  type    = string
  default = "sports-ev"
}

variable "db_instance_name" {
  type    = string
  default = "odds-value-pg"
}

variable "db_name" {
  type    = string
  default = "odds_value"
}

variable "db_user" {
  type    = string
  default = "odds_value_app"
}

variable "db_password" {
  type        = string
  description = "Optional: set to the existing DB user's password to avoid rotation when importing. If omitted, Terraform will generate one."
  sensitive   = true
  default     = null
}
