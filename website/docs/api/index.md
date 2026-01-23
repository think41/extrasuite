# API Reference

ExtraSuite provides a simple API for AI agents to obtain short-lived Google Cloud service account tokens. This section documents the protocol specification and implementation details.

## For Implementers

If you want to build your own ExtraSuite-compatible server using your organization's authentication system:

<div class="grid cards" markdown>

-   **[Authentication API Specification](auth-spec.md)**

    ---

    Complete protocol specification for the authentication and token issuance flow. Implementation-agnostic — use your own auth system, access policies, and infrastructure.

</div>

## Why Implement Your Own?

The [reference implementation](../deployment/index.md) uses Google OAuth and Cloud Run. You might want your own implementation if:

| Requirement | Your Solution |
|-------------|---------------|
| "I want to use my own authentication" | Integrate with your existing SSO, SAML, or identity provider |
| "I want to control which employees can use this" | Apply your access policies, group memberships, or approval workflows |
| "I already have an employee portal" | Add the two required endpoints to your existing service |

## Core Concepts

### The Protocol in Brief

1. **CLI starts a local server** on a random port
2. **CLI opens browser** to your server with the port number
3. **Your server authenticates** the user (your auth, your policies)
4. **Your server redirects** to localhost with an authorization code
5. **CLI exchanges the code** for a token via API call
6. **Your server returns** a short-lived token + expiry + service account email

### What You Provide

| Component | Description |
|-----------|-------------|
| User Authentication | Your existing identity system (OAuth, SAML, LDAP, etc.) |
| Access Control | Your rules for who can obtain tokens |
| Service Accounts | Google Cloud service accounts for your users |
| Token Generation | Google Cloud IAM to create short-lived tokens |

### What You Get

| Benefit | Description |
|---------|-------------|
| Compatibility | Works with `extrasuite-client` and all ExtraSuite skills |
| Control | Full control over authentication and authorization |
| Integration | Fits into your existing infrastructure |
| Audit Trail | All actions attributed to user-specific service accounts |

## Reference Implementation

The open-source reference implementation is available at [github.com/think41/extrasuite](https://github.com/think41/extrasuite). It provides:

- Google OAuth authentication
- Firestore for state management
- Automatic service account provisioning
- Cloud Run deployment

See the [Deployment Guide](../deployment/index.md) to deploy the reference implementation.

## Client Library

The `extrasuite-client` library implements the client side of this protocol:

```python
from extrasuite_client import CredentialsManager

# Point to your server
creds = CredentialsManager(server_url="https://your-server.com")

# Get a token (handles auth flow automatically)
token_info = creds.get_credentials()

print(f"Token: {token_info['access_token']}")
print(f"Expires: {token_info['expires_at']}")
print(f"Service Account: {token_info['service_account_email']}")
```

The client library works with any server that implements the [Authentication API Specification](auth-spec.md).
