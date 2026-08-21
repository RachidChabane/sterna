# Shared Secrets Outputs

output "secret_ids" {
  description = "Shared secret IDs"
  value = {
    llm_secrets      = scaleway_secret.llm_secrets.id
    oauth_secrets    = scaleway_secret.oauth_secrets.id
    external_secrets = scaleway_secret.external_secrets.id
    voice_secrets    = scaleway_secret.voice_secrets.id
  }
}

output "secret_names" {
  description = "Shared secret names"
  value = {
    llm_secrets      = scaleway_secret.llm_secrets.name
    oauth_secrets    = scaleway_secret.oauth_secrets.name
    external_secrets = scaleway_secret.external_secrets.name
    voice_secrets    = scaleway_secret.voice_secrets.name
  }
}

output "credentials" {
  description = "Credentials for External Secrets Operator to access shared secrets"
  value = {
    access_key = scaleway_iam_api_key.shared_secrets.access_key
    secret_key = scaleway_iam_api_key.shared_secrets.secret_key
  }
  sensitive = true
}
