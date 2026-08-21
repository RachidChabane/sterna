"""Add ``User.provider_api_keys`` for provider-scoped BYOK.

Encrypted JSON object mapping provider slug (see
``llm.provider_registry.BYOK_PROVIDERS``) to the user's own API key for
that provider. Chat requests to a matching first-party model are routed
directly to the provider's OpenAI-compatible endpoint with this key.
"""

import mcp.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0013_refreshtoken_hash_and_family"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="provider_api_keys",
            field=mcp.fields.EncryptedTextField(
                blank=True,
                help_text=(
                    "JSON object mapping provider slug to the user's API key "
                    "for that provider (encrypted at rest)"
                ),
                null=True,
            ),
        ),
    ]
