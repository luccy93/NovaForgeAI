# NovaForge AI — Terraform Configuration
# Provisions cloud infrastructure for production deployment

terraform {
  required_version = ">= 1.8"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.0"
    }
  }

  backend "gcs" {
    bucket = "novaforge-terraform-state"
    prefix = "prod"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ─── VPC ──────────────────────────────────────────────────────────

resource "google_compute_network" "vpc" {
  name                    = "novaforge-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  name          = "novaforge-subnet"
  network       = google_compute_network.vpc.id
  region        = var.region
  ip_cidr_range = "10.0.0.0/16"
  private_ip_google_access = true
}

# ─── GKE Cluster ──────────────────────────────────────────────────

resource "google_container_cluster" "cluster" {
  name     = "novaforge-cluster"
  location = var.region

  network    = google_compute_network.vpc.id
  subnetwork = google_compute_subnetwork.subnet.id

  remove_default_node_pool = true
  initial_node_count       = 1

  master_auth {
    client_certificate_config {
      issue_client_certificate = false
    }
  }

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = "10.1.0.0/28"
  }

  ip_allocation_policy {
    cluster_ipv4_cidr_block  = "10.2.0.0/16"
    services_ipv4_cidr_block = "10.3.0.0/16"
  }

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }
}

resource "google_container_node_pool" "general" {
  name       = "general-pool"
  location   = var.region
  cluster    = google_container_cluster.cluster.name
  node_count = var.node_count

  node_config {
    machine_type = var.machine_type
    disk_size_gb = 100
    disk_type    = "pd-standard"
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]
    workload_metadata_config {
      mode = "GKE_METADATA"
    }
    labels = {
      role = "general"
    }
    tags = ["novaforge"]
  }
}

resource "google_container_node_pool" "gpu" {
  count      = var.enable_gpu ? 1 : 0
  name       = "gpu-pool"
  location   = var.region
  cluster    = google_container_cluster.cluster.name
  node_count = 0

  autoscaling {
    min_node_count = 0
    max_node_count = 5
  }

  node_config {
    machine_type = "n1-standard-8"
    disk_size_gb = 200
    oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    guest_accelerator {
      type  = "nvidia-tesla-t4"
      count = 1
    }
    labels = {
      role = "gpu"
    }
    tags = ["novaforge", "gpu"]
  }
}

# ─── Cloud SQL (PostgreSQL) ───────────────────────────────────────

resource "google_sql_database_instance" "postgres" {
  name             = "novaforge-postgres"
  database_version = "POSTGRES_16"
  region           = var.region

  settings {
    tier              = var.postgres_tier
    disk_size         = 100
    disk_autoresize   = true
    disk_type         = "PD_SSD"
    availability_type = "ZONAL"

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "03:00"
      transaction_log_retention_days = 7
    }

    ip_configuration {
      private_network = google_compute_network.vpc.id
      ipv4_enabled    = false
    }
  }
}

resource "google_sql_database" "database" {
  name     = "novaforge"
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "app_user" {
  name     = "novaforge"
  instance = google_sql_database_instance.postgres.name
  password = var.postgres_password
}

# ─── Memorystore (Redis) ───────────────────────────────────────────

resource "google_redis_instance" "redis" {
  name           = "novaforge-redis"
  tier           = "STANDARD_HA"
  memory_size_gb = var.redis_memory_gb
  region         = var.region
  connect_mode   = "PRIVATE_SERVICE_ACCESS"
  authorized_network = google_compute_network.vpc.id
}

# ─── Outputs ──────────────────────────────────────────────────────

output "cluster_endpoint" {
  value = google_container_cluster.cluster.endpoint
}

output "postgres_connection" {
  value = google_sql_database_instance.postgres.private_ip_address
}

output "redis_host" {
  value = google_redis_instance.redis.host
}
