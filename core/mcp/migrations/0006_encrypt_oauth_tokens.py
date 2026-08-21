"""Data migration to encrypt existing OAuth tokens.

This migration encrypts any existing plain-text OAuth tokens stored in:
- MCPServer.auth_config
- MCPConnection.access_token
- MCPConnection.refresh_token

The migration reads plain-text data, encrypts it with Fernet, and writes the encrypted data back.
"""

import json
from django.conf import settings
from django.db import migrations
from cryptography.fernet import Fernet


def encrypt_existing_tokens(apps, schema_editor):
    """Encrypt all existing OAuth tokens."""
    MCPServer = apps.get_model('mcp', 'MCPServer')
    MCPConnection = apps.get_model('mcp', 'MCPConnection')

    # Get encryption key
    key = getattr(settings, 'FIELD_ENCRYPTION_KEY', None)
    if not key:
        print("WARNING: FIELD_ENCRYPTION_KEY not set - skipping encryption")
        return

    if isinstance(key, str):
        key = key.encode()

    fernet = Fernet(key)

    # Encrypt MCPServer.auth_config
    servers_encrypted = 0
    for server in MCPServer.objects.all():
        if server.auth_config:
            try:
                # The value is now stored as TEXT (JSON string)
                if isinstance(server.auth_config, str):
                    # Parse JSON string
                    data = json.loads(server.auth_config)
                elif isinstance(server.auth_config, dict):
                    # Already a dict (shouldn't happen but handle it)
                    data = server.auth_config
                else:
                    print(f"WARNING: Unexpected auth_config type for server {server.id}: {type(server.auth_config)}")
                    continue

                # Encrypt the JSON
                json_str = json.dumps(data, ensure_ascii=False)
                encrypted = fernet.encrypt(json_str.encode())

                # Update using direct SQL to bypass field decryption
                schema_editor.execute(
                    "UPDATE mcp_mcpserver SET auth_config = %s WHERE id = %s",
                    [encrypted.decode(), server.id]
                )
                servers_encrypted += 1
            except Exception as e:
                print(f"WARNING: Could not encrypt auth_config for server {server.id}: {e}")

    print(f"✅ Encrypted auth_config for {servers_encrypted} MCP servers")

    # Encrypt MCPConnection tokens
    connections_encrypted = 0
    for connection in MCPConnection.objects.all():
        try:
            updates = []
            params = []

            # Encrypt access_token
            if connection.access_token and connection.access_token.strip():
                encrypted_access = fernet.encrypt(connection.access_token.encode())
                updates.append("access_token = %s")
                params.append(encrypted_access.decode())

            # Encrypt refresh_token
            if connection.refresh_token and connection.refresh_token.strip():
                encrypted_refresh = fernet.encrypt(connection.refresh_token.encode())
                updates.append("refresh_token = %s")
                params.append(encrypted_refresh.decode())

            if updates:
                params.append(connection.id)
                sql = f"UPDATE mcp_mcpconnection SET {', '.join(updates)} WHERE id = %s"
                schema_editor.execute(sql, params)
                connections_encrypted += 1

        except Exception as e:
            print(f"WARNING: Could not encrypt tokens for connection {connection.id}: {e}")

    print(f"✅ Encrypted tokens for {connections_encrypted} MCP connections")


def decrypt_existing_tokens(apps, schema_editor):
    """Reverse migration - decrypt all tokens back to plain text."""
    MCPServer = apps.get_model('mcp', 'MCPServer')
    MCPConnection = apps.get_model('mcp', 'MCPConnection')

    # Get encryption key
    key = getattr(settings, 'FIELD_ENCRYPTION_KEY', None)
    if not key:
        print("WARNING: FIELD_ENCRYPTION_KEY not set - cannot decrypt")
        return

    if isinstance(key, str):
        key = key.encode()

    fernet = Fernet(key)

    # Decrypt MCPServer.auth_config
    for server in MCPServer.objects.all():
        if server.auth_config:
            try:
                # Decrypt
                if isinstance(server.auth_config, str):
                    decrypted = fernet.decrypt(server.auth_config.encode())
                    decrypted_str = decrypted.decode()
                else:
                    decrypted_str = server.auth_config

                # Update using direct SQL
                schema_editor.execute(
                    "UPDATE mcp_mcpserver SET auth_config = %s WHERE id = %s",
                    [decrypted_str, server.id]
                )
            except Exception as e:
                print(f"WARNING: Could not decrypt auth_config for server {server.id}: {e}")

    # Decrypt MCPConnection tokens
    for connection in MCPConnection.objects.all():
        try:
            updates = []
            params = []

            if connection.access_token:
                decrypted_access = fernet.decrypt(connection.access_token.encode())
                updates.append("access_token = %s")
                params.append(decrypted_access.decode())

            if connection.refresh_token:
                decrypted_refresh = fernet.decrypt(connection.refresh_token.encode())
                updates.append("refresh_token = %s")
                params.append(decrypted_refresh.decode())

            if updates:
                params.append(connection.id)
                sql = f"UPDATE mcp_mcpconnection SET {', '.join(updates)} WHERE id = %s"
                schema_editor.execute(sql, params)

        except Exception as e:
            print(f"WARNING: Could not decrypt tokens for connection {connection.id}: {e}")


class Migration(migrations.Migration):
    """Encrypt existing OAuth tokens for GDPR/CCPA compliance."""

    dependencies = [
        ('mcp', '0005_alter_mcpconnection_access_token_and_more'),
    ]

    operations = [
        migrations.RunPython(
            encrypt_existing_tokens,
            decrypt_existing_tokens,
        ),
    ]
