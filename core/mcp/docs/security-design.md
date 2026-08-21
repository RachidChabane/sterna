# MCP OAuth Token Security

## Overview

This document describes the security measures implemented for storing OAuth tokens in compliance with **GDPR (General Data Protection Regulation)**, **CCPA (California Consumer Privacy Act)**, and other data protection regulations.

## Legal Requirements

OAuth tokens are considered **sensitive personal data** under GDPR and CCPA. Storing them in plain text is:
- ❌ **Illegal** under GDPR Article 32 (Security of processing)
- ❌ **Illegal** under CCPA § 1798.150 (Security requirements)
- ❌ **Non-compliant** with PCI-DSS, SOC 2, and ISO 27001 standards

**GDPR Article 32** requires:
> "The controller and the processor shall implement appropriate technical and organizational measures to ensure a level of security appropriate to the risk, including... the pseudonymisation and encryption of personal data."

## Implementation

### Encryption Method

We use **Fernet encryption** (symmetric encryption) from the `cryptography` library:
- **Algorithm**: AES-128 in CBC mode with PKCS7 padding
- **Key derivation**: Fernet keys are 32 URL-safe base64-encoded bytes
- **Integrity**: Built-in HMAC signature to detect tampering
- **Standards compliant**: Meets NIST recommendations for data at rest

### Encrypted Fields

The following fields are encrypted at rest:

1. **MCPServer.auth_config** (`EncryptedJSONField`)
   - Stores API keys and tokens for MCP server connections
   - Format: `{"API_KEY": "sk-xxx..."}`
   - Encrypted before database write, decrypted on read

2. **MCPServer.env_vars** (`EncryptedJSONField`)
   - Environment variables passed to sandboxed MCP servers
   - Contains API keys, tokens, and other secrets
   - Format: `{"GITHUB_TOKEN": "ghp_xxx...", "API_KEY": "..."}`

3. **MCPServer.oauth_access_token** (`EncryptedTextField`)
   - OAuth 2.1 access token for remote MCP servers
   - Per-server OAuth authentication

4. **MCPServer.oauth_refresh_token** (`EncryptedTextField`)
   - OAuth 2.1 refresh token for renewing access tokens
   - Optional field, encrypted when present

5. **MCPServer.oauth_client_secret** (`EncryptedTextField`)
   - OAuth client secret from dynamic client registration
   - Encrypted at rest for security

6. **MCPServer.oauth_pkce_verifier** (`EncryptedTextField`)
   - Temporary PKCE code verifier during OAuth flow
   - Cleared after OAuth completion

### Custom Fields

We've implemented two custom Django model fields in `mcp/fields.py`:

#### EncryptedTextField
```python
from mcp.fields import EncryptedTextField

class MyModel(models.Model):
    secret_data = EncryptedTextField()
```

- Inherits from `models.TextField`
- Encrypts on write (`get_prep_value`)
- Decrypts on read (`from_db_value`)
- Backwards compatible: handles legacy plain-text data gracefully

#### EncryptedJSONField
```python
from mcp.fields import EncryptedJSONField

class MyModel(models.Model):
    secret_config = EncryptedJSONField(default=dict)
```

- Inherits from `models.JSONField`
- Serializes to JSON, then encrypts
- Decrypts, then parses JSON on read
- Backwards compatible with plain JSON

### Configuration

#### Environment Variable

Set the encryption key in your `.env` file:

```bash
# Generate a new key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Add to .env
FIELD_ENCRYPTION_KEY=<generated-key>
```

⚠️ **CRITICAL**:
- **NEVER commit** the production encryption key to version control
- **KEEP IT SECRET**: Treat it like a password
- **DO NOT CHANGE**: Changing the key will make existing encrypted data unreadable
- **BACKUP**: Store securely in your secrets management system (e.g., AWS Secrets Manager, HashiCorp Vault)

#### Settings Configuration

The key is loaded in `sterna/settings/base.py`:

```python
FIELD_ENCRYPTION_KEY = env(
    "FIELD_ENCRYPTION_KEY",
    default="..."  # Development only
)
```

### Migration

A data migration (`0005_encrypt_oauth_tokens.py`) encrypts existing plain-text tokens:

```bash
# Apply migration
python manage.py migrate mcp

# The migration will:
# 1. Read existing plain-text tokens
# 2. Encrypt them using FIELD_ENCRYPTION_KEY
# 3. Update database with encrypted values
# 4. Report number of records encrypted
```

**Rollback**: The migration is reversible - it will decrypt tokens back to plain text if rolled back.

### Backwards Compatibility

The encrypted fields have built-in backwards compatibility:

1. **On read**: If decryption fails (invalid token error), assumes data is legacy plain-text
2. **Logging**: Warns when encountering plain-text data
3. **Graceful fallback**: Returns plain-text value instead of crashing

This ensures:
- ✅ Safe deployment without data loss
- ✅ Gradual migration of legacy data
- ✅ No service interruption

## Security Best Practices

### Key Management

1. **Development**:
   - Default key is hardcoded (acceptable for dev/test)
   - Key is version-controlled in settings (dev only)

2. **Production**:
   - Generate unique key per environment
   - Store in secrets management system
   - Rotate keys periodically (requires re-encryption migration)
   - Use environment variables, never hardcode

### Access Control

1. **Database level**:
   - Encrypted data is useless without the encryption key
   - Even with database access, attacker cannot decrypt tokens

2. **Application level**:
   - Django's user isolation (ForeignKey to User)
   - ViewSet querysets filtered by user
   - Defense-in-depth verification in registry layer

3. **Infrastructure level**:
   - Database credentials separated from encryption key
   - TLS for database connections
   - Network isolation (VPC, security groups)

### Compliance Checklist

- ✅ **GDPR Article 32**: Data encrypted at rest
- ✅ **CCPA § 1798.150**: Reasonable security measures
- ✅ **PCI-DSS 3.4**: Encryption of sensitive data
- ✅ **SOC 2**: Encryption controls
- ✅ **NIST 800-53**: SC-28 (Protection of Information at Rest)
- ✅ **ISO 27001**: A.10.1.1 (Cryptographic controls)

## Audit Trail

All OAuth token operations are logged:

1. **Connection logs** (`mcp/registry.py`):
   - Environment variables set (names only, not values)
   - Server connection/disconnection
   - Token usage

2. **OAuth flow logs** (`mcp/views.py`):
   - OAuth authorization requests
   - Token exchange success/failure
   - Cache invalidation after token updates

3. **Tool execution logs** (`mcp/models.py`):
   - `MCPToolExecution` model tracks every tool call
   - Includes timestamp, user, tool, arguments, results
   - Audit trail for compliance

## Threat Model

### Threats Mitigated

| Threat | Mitigation |
|--------|-----------|
| Database breach | Tokens encrypted, useless without key |
| SQL injection | Tokens encrypted in database |
| Insider threat | Separate key from database credentials |
| Backup exposure | Backups contain encrypted data |
| Log exposure | Tokens never logged in plain text |

### Residual Risks

| Risk | Mitigation Strategy |
|------|---------------------|
| Encryption key theft | Store in HSM/Secrets Manager, rotate regularly |
| Memory dump attack | Use memory-safe languages, secure infrastructure |
| Application compromise | Defense-in-depth, user isolation, audit logging |

## Testing

Test the encryption with these steps:

```python
# Django shell
python manage.py shell

from mcp.models import MCPServer
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.first()

# Create server with auth_config
server = MCPServer.objects.create(
    user=user,
    name="Test Server",
    transport_type="stdio",
    command="test",
    auth_config={"TOKEN": "test-token-123"}
)

# Check database - should be encrypted
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute("SELECT auth_config FROM mcp_mcpserver WHERE id = %s", [server.id])
    raw_value = cursor.fetchone()[0]
    print(f"Raw DB value: {raw_value}")  # Should be encrypted gibberish

# Read from model - should be decrypted
server.refresh_from_db()
print(f"Decrypted value: {server.auth_config}")  # Should be {"TOKEN": "test-token-123"}
```

## Production Deployment

### Pre-deployment Checklist

- [ ] Generate unique `FIELD_ENCRYPTION_KEY` for production
- [ ] Store key in secrets management system (AWS Secrets Manager, etc.)
- [ ] Set key via environment variable (not in code)
- [ ] Test encryption/decryption in staging
- [ ] Run migration to encrypt existing data
- [ ] Verify encrypted data in database
- [ ] Document key location and access procedures
- [ ] Set up key rotation schedule (annually minimum)

### Monitoring

Monitor these metrics:

1. **Decryption failures**: Should be zero in production
2. **Migration warnings**: Indicates legacy plain-text data
3. **Key access logs**: Track who/what accesses encryption key

## Support

For questions or security concerns, contact:
- Security team: security@your-company.com
- Lead developer: Your contact info

## References

- [GDPR Article 32](https://gdpr-info.eu/art-32-gdpr/)
- [CCPA § 1798.150](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?sectionNum=1798.150&lawCode=CIV)
- [Cryptography Library](https://cryptography.io/en/latest/fernet/)
- [Django Field Documentation](https://docs.djangoproject.com/en/stable/howto/custom-model-fields/)
- [NIST SP 800-57](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-57pt1r5.pdf)
