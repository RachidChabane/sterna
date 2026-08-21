# Backend configuration for Terraform state
# Using Cloudflare R2 as S3-compatible backend

terraform {
  backend "s3" {
    bucket = "sternaway-tfstate"
    key    = "shared/terraform.tfstate"
    region = "us-east-1" # Ignored - R2 uses its own region

    # R2-compatible settings (Terraform 1.8+)
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_s3_checksum            = true
    use_path_style              = true

    endpoints = {
      s3 = "https://b80b576d7908f66d87478b739446ae55.r2.cloudflarestorage.com"
    }
  }
}
