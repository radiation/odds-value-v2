terraform {
  backend "gcs" {
    bucket = "odds-value-tfstate"
    prefix = "envs/prod"
  }
}
