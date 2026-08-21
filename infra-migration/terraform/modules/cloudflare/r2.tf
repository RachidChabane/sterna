# R2 bucket for user-generated content
resource "cloudflare_r2_bucket" "main" {
  count = var.r2_bucket_name != "" ? 1 : 0

  account_id = var.cloudflare_account_id
  name       = var.r2_bucket_name
  location   = "WEUR" # Western Europe
}

# R2 bucket for Terraform state (only create if explicitly enabled)
resource "cloudflare_r2_bucket" "tfstate" {
  count = var.create_tfstate_bucket ? 1 : 0

  account_id = var.cloudflare_account_id
  name       = "sternaway-tfstate"
  location   = "WEUR"
}

# -----------------------------------------------------------------------------
# R2 Bucket for Database Backups
# -----------------------------------------------------------------------------
# Stores daily PostgreSQL backups with 30-day retention

resource "cloudflare_r2_bucket" "backups" {
  count = var.create_backup_bucket ? 1 : 0

  account_id = var.cloudflare_account_id
  name       = "sternaway-backups-${var.environment}"
  location   = "WEUR" # Western Europe
}

# Lifecycle rule for 30-day retention
# Note: Cloudflare R2 lifecycle rules are managed via API/dashboard
# This is documented here for reference, to be applied manually or via API:
#
# Lifecycle rule configuration:
# - Rule ID: delete-old-backups
# - Prefix: (empty, applies to all objects)
# - Action: Delete objects after 30 days
#
# Apply via Cloudflare API:
# PUT /accounts/{account_id}/r2/buckets/{bucket_name}/lifecycle
# {
#   "rules": [{
#     "id": "delete-old-backups",
#     "enabled": true,
#     "conditions": { "maxAgeDays": 30 },
#     "actions": { "type": "Delete" }
#   }]
# }
