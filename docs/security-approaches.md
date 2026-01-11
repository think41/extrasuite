# Fabric EA: Security Approaches for Service Account Credentials

## Problem Statement

Fabric provisions service accounts (SAs) for employees to interact with Google Docs/Sheets via CLI tools. Currently, each employee downloads a long-lived SA private key. Security team's concerns:

1. Private keys never expire
2. If key is stolen, all documents shared with that SA are compromised
3. Revocation requires manual intervention in GCP
4. Limited audit trail (SA usage doesn't tie back to human identity)

**Constraint**: Each employee must have their own SA (1:1 mapping) to prevent cross-employee document access.

---

## Approach Comparison Summary

| Approach | Credential Stored Locally | Lifetime | Blast Radius | Revocation Speed | CLI UX |
|----------|---------------------------|----------|--------------|------------------|--------|
| A. SA Private Key | Private key | Forever | EA docs | Manual (hours) | Seamless |
| B. Local OAuth + Impersonation | OAuth refresh token | Until revoked | EA docs + **all GCP** | Fast (minutes) | Seamless |
| **C. Fabric Token Exchange** | **SA token only** | **1 hour** | EA docs only | Instant | Hourly browser flash |
| D. SA Key with Rotation | Private key (rotated) | 30 days | EA docs | Manual (hours) | Seamless |

**Approach C stores OAuth credentials server-side in Fabric, not on the user's laptop.**

---

## Approach A: Long-Lived SA Private Key (Current)

### How It Works
1. Employee visits Fabric portal, authenticates via Google
2. Fabric creates SA, generates private key
3. Employee downloads key to `~/.config/gspread/service_account.json`
4. CLI tools use key directly for API calls

### Credential Details
```
Stored: ~/.config/gspread/service_account.json
Contains: SA private key (RSA)
Lifetime: Permanent (never expires)
Scope: Whatever APIs the SA is used for
```

### Security Properties
| Property | Assessment |
|----------|------------|
| Exposure if stolen | Permanent access until key manually deleted |
| Revocation | Must identify specific key in GCP Console, delete it |
| Audit trail | "SA X accessed Sheet Y" - no human identity |
| Blast radius | Only documents shared with this SA |
| GCP project access | None (SA has no GCP IAM roles) |

### Employee Experience
- **Setup**: One-time portal visit + curl command
- **Daily use**: Fully seamless, no re-authentication
- **Offline**: Works completely offline
- **Friction**: Zero after initial setup

### CLI Ergonomics
```python
# Simple - just load the key file
gc = gspread.service_account(filename=CREDS_FILE)
sheet = gc.open_by_url(url)
```

### Pros
- Simplest implementation
- Zero ongoing friction for employees
- Works offline
- No server dependency after setup

### Cons
- Keys never expire
- Revocation is manual and slow
- No tie to human identity in audit logs
- If laptop is stolen, attacker has permanent access

---

## Approach B: Local OAuth + SA Impersonation

### How It Works
1. CLI runs local OAuth flow (opens browser, local callback server)
2. Employee authenticates with their @company.com Google account
3. OAuth refresh token stored locally
4. CLI uses OAuth token to impersonate employee's mapped SA
5. Impersonation generates short-lived SA access tokens (1 hour)

### Prerequisite Setup (Admin)
```bash
# Create SA for each employee
gcloud iam service-accounts create ea-alice

# Grant employee permission to impersonate their SA only
gcloud iam service-accounts add-iam-policy-binding \
  ea-alice@project.iam.gserviceaccount.com \
  --member="user:alice@company.com" \
  --role="roles/iam.serviceAccountTokenCreator"
```

### Credential Details
```
Stored: ~/.config/fabric/credentials.json
Contains: OAuth refresh token + client ID/secret
Lifetime: Until explicitly revoked (or 6 months unused)
Scope: cloud-platform (required for impersonation)
```

### Security Properties
| Property | Assessment |
|----------|------------|
| Exposure if stolen | Access until refresh token revoked |
| Revocation | Google Workspace admin can revoke instantly |
| Audit trail | "User X impersonated SA Y" - human identity preserved |
| Blast radius | **EA docs + ALL GCP projects user has access to** |
| GCP project access | **Yes - full cloud-platform scope** |

### Employee Experience
- **Setup**: Run `gsheet auth`, browser opens, approve once
- **Daily use**: Seamless (refresh token auto-renews)
- **Offline**: Works (cached access tokens valid for 1 hour)
- **Friction**: Zero after initial setup

### CLI Ergonomics
```python
# More complex - OAuth flow + impersonation
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth import impersonated_credentials

def auth():
    flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, SCOPES)
    creds = flow.run_local_server(port=8085)
    # Save refresh token...

def get_client():
    source_creds = Credentials(refresh_token=saved_token, ...)
    target_creds = impersonated_credentials.Credentials(
        source_credentials=source_creds,
        target_principal="ea-alice@project.iam.gserviceaccount.com",
        target_scopes=["spreadsheets", "drive.readonly"]
    )
    return gspread.authorize(target_creds)
```

### Pros
- Short-lived SA tokens (1 hour)
- Centralized revocation via Google Workspace
- Human identity in audit logs
- Leverages existing Google auth (2FA, session policies)
- No Fabric server dependency

### Cons
- **Critical**: Stolen OAuth token grants access to ALL GCP projects the employee can access
- OAuth refresh tokens are still long-lived
- Requires cloud-platform scope (very broad)
- Employees with production GCP access have elevated risk

### When to Use
Only if employees have minimal/no GCP access beyond the EA project.

---

## Approach C: Fabric Token Exchange Service (Recommended)

### How It Works

**First-Time Flow:**
1. CLI starts localhost webserver on random port
2. CLI prints/opens URL: `https://fabric.think41.com/api/auth?redirect=http://localhost:<port>/on-authentication`
3. User authenticates to Fabric via Google OAuth in browser
4. User grants Fabric `cloud-platform` scope
5. Fabric saves OAuth credentials in server-side database
6. Fabric searches GCP for user's SA (by metadata in SA description)
7. If SA not found:
   - Create SA: `ea-<username>@project.iam.gserviceaccount.com`
   - Store metadata: `Owner: alice@company.com | Created: <timestamp>`
   - Grant user `serviceAccountTokenCreator` on their SA only
8. Fabric impersonates SA using stored OAuth credentials
9. Browser redirects to `http://localhost:<port>/on-authentication?token=<sa_token>`
10. Localhost server receives token, saves to file, terminates
11. CLI continues with SA token

**Subsequent Flow:**
1. CLI checks if cached SA token is valid (not expired)
2. If valid → use directly, call Google APIs
3. If expired → repeat auth flow (steps 1-11)
4. User likely has active Fabric session → redirect happens quickly
5. Brief browser open/close (acceptable UX tradeoff)

### Credential Storage

```
┌─────────────────────────────────────────────────────────────────┐
│ FABRIC SERVER (Database)                                        │
├─────────────────────────────────────────────────────────────────┤
│ User OAuth Credentials:                                         │
│   alice@company.com → {                                         │
│     refresh_token: "1//0eXXX...",                              │
│     access_token: "ya29.XXX...",                               │
│     scopes: ["cloud-platform"],                                │
│     created_at: "2024-01-15T10:00:00Z"                         │
│   }                                                             │
│                                                                 │
│ SA Mapping (derived from GCP metadata search):                  │
│   alice@company.com → ea-alice@project.iam.gserviceaccount.com │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ USER'S LAPTOP                                                   │
├─────────────────────────────────────────────────────────────────┤
│ ~/.config/fabric/token.json                                     │
│   {                                                             │
│     "access_token": "ya29.SA_TOKEN...",                        │
│     "expires_at": 1699876543,                                  │
│     "service_account": "ea-alice@project.iam.gserviceaccount"  │
│   }                                                             │
│                                                                 │
│ NO OAuth credentials                                            │
│ NO Fabric session token                                         │
│ NO long-lived secrets                                           │
└─────────────────────────────────────────────────────────────────┘
```

### Credential Details
```
Stored locally: SA access token ONLY
SA token lifetime: 1 hour (fixed by Google)
SA token scope: spreadsheets + drive.readonly (no cloud-platform)
OAuth credentials: Stored server-side in Fabric DB
```

### Security Properties
| Property | Assessment |
|----------|------------|
| Exposure if stolen | **1 hour max** (only SA token on laptop) |
| Revocation | Delete OAuth from Fabric DB → no new tokens issued |
| Audit trail | Fabric logs all token requests + Google logs SA usage |
| Blast radius | EA docs only (SA token has no cloud-platform scope) |
| GCP project access | None (SA tokens scoped to sheets/drive only) |
| OAuth exposure | **None on laptop** (stored server-side only) |

### Attack Window Analysis
```
Scenario: SA token file stolen at T=0

├─ 0h ────────────────────────── 1h ─┤
│  Attacker can access EA docs        │ Token expires
│                                     │ Attack ends automatically
│  No way to get new tokens           │
│  (OAuth is on server, not laptop)   │

Scenario: Fabric server DB compromised
├─ OAuth credentials exposed
├─ Admin must rotate all OAuth tokens
├─ Users re-authenticate via browser
└─ More serious, but centralized response
```

### Employee Experience
- **First-time setup**: Browser opens, Google OAuth, ~30 seconds
- **Daily use**: Every hour, brief browser open/close for token refresh
- **Offline**: Works for up to 1 hour (cached SA token)
- **Friction**: Moderate (hourly browser flash, but auto-completes if session active)

### CLI Ergonomics
```python
import http.server
import threading
import webbrowser
import urllib.parse
import secrets
from pathlib import Path

TOKEN_FILE = Path.home() / ".config" / "fabric" / "token.json"
FABRIC_AUTH_URL = "https://fabric.think41.com/api/auth"

def get_token():
    """Get valid SA token, refreshing via browser if needed."""
    # Check cached token
    if TOKEN_FILE.exists():
        token_data = json.loads(TOKEN_FILE.read_text())
        if token_data["expires_at"] > time.time() + 60:  # 1 min buffer
            return token_data["access_token"]

    # Need new token - start localhost server and open browser
    return browser_auth_flow()

def browser_auth_flow():
    """Open browser for auth, receive token via localhost callback."""
    port = find_free_port()  # Random available port
    token_holder = {}

    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)

            if "token" in params:
                token_holder["token"] = params["token"][0]
                token_holder["expires_in"] = int(params.get("expires_in", [3600])[0])
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Authentication successful! You can close this tab.")
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Authentication failed.")

    # Start server in background
    server = http.server.HTTPServer(("localhost", port), CallbackHandler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()

    # Open browser
    redirect_url = f"http://localhost:{port}/on-authentication"
    auth_url = f"{FABRIC_AUTH_URL}?redirect={urllib.parse.quote(redirect_url)}"

    print(f"Opening browser for authentication...")
    print(f"If browser doesn't open, visit: {auth_url}")
    webbrowser.open(auth_url)

    # Wait for callback
    thread.join(timeout=120)
    server.server_close()

    if "token" not in token_holder:
        raise Exception("Authentication timed out or failed")

    # Save token
    token_data = {
        "access_token": token_holder["token"],
        "expires_at": time.time() + token_holder["expires_in"],
    }
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(token_data))

    return token_holder["token"]

def get_client():
    """Get authenticated gspread client."""
    token = get_token()
    creds = Credentials(token=token)
    return gspread.authorize(creds)
```

### Security Advantages Over Other Approaches

| Aspect | Approach C (Token Exchange) | Why It's Better |
|--------|----------------------------|-----------------|
| Local credential lifetime | 1 hour | vs. permanent (SA key) or long-lived (OAuth) |
| OAuth on laptop | None | vs. refresh token with cloud-platform scope |
| Blast radius | EA docs only | vs. all GCP projects (local OAuth) |
| Self-service provisioning | Yes | No admin setup per employee |
| Revocation | Delete from Fabric DB | Centralized, instant |

### Pros
- **Shortest exposure window**: 1 hour max (only SA token on laptop)
- **Zero OAuth on laptop**: All OAuth credentials stored server-side
- **Instant centralized revocation**: Delete from Fabric DB
- **Self-service provisioning**: SA auto-created on first auth
- **No GCP blast radius**: SA tokens only have sheets/drive scope
- **Full audit trail**: Fabric logs + Google logs

### Cons
- Requires Fabric server to be available for token refresh
- Hourly browser open/close for token refresh (auto-completes if session active)
- More complex implementation (server-side OAuth storage, SA auto-provisioning)
- Network dependency for token refresh
- If Fabric DB is compromised, all OAuth tokens are exposed (but centralized response)

---

## Approach D: SA Keys with Lifecycle Management

### How It Works
1. Same as Approach A, but with automated rotation
2. CLI checks key age, warns/refuses if too old
3. Background job deletes keys older than threshold
4. Employees re-provision periodically

### Credential Details
```
Stored: ~/.config/gspread/service_account.json
Contains: SA private key (RSA)
Lifetime: 30 days (policy-enforced, not cryptographic)
Rotation: Employee must re-download monthly
```

### Security Properties
| Property | Assessment |
|----------|------------|
| Exposure if stolen | 30 days max (until rotation) |
| Revocation | Manual, but old keys auto-deleted |
| Audit trail | Still weak (SA usage, no human identity) |
| Blast radius | EA docs only |
| GCP project access | None |

### Employee Experience
- **Setup**: Portal visit + curl command
- **Daily use**: Seamless until key expires
- **Monthly**: Must re-visit portal, re-run curl
- **Friction**: Low (one interruption per month)

### CLI Ergonomics
```python
def check_key_age():
    key_data = json.load(CREDS_FILE)
    created = datetime.fromisoformat(key_data.get("created_at"))
    age = datetime.now() - created
    if age > timedelta(days=30):
        raise Error("Key expired. Run 'gsheet auth' to refresh.")
    if age > timedelta(days=25):
        print("Warning: Key expires in", 30 - age.days, "days")
```

### Pros
- Limits exposure window to rotation period
- Simple implementation
- Works offline
- No server dependency after provisioning

### Cons
- Still stores private keys locally
- Rotation is policy-enforced, not cryptographic
- Weak audit trail (no human identity)
- Monthly friction for employees

---

## Recommendation Matrix

### By Security Priority

| If security team prioritizes... | Recommended Approach |
|--------------------------------|---------------------|
| Minimal blast radius | C (Fabric Token Exchange) |
| Fastest revocation | C (Fabric Token Exchange) |
| Best audit trail | B or C (both tie to human identity) |
| No long-lived secrets | C (Fabric Token Exchange) |
| Defense in depth | C (Fabric Token Exchange) |

### By Employee Experience Priority

| If employee experience prioritizes... | Recommended Approach |
|--------------------------------------|---------------------|
| Zero daily friction | A (SA Key) or D (SA Key + Rotation) |
| Offline capability | A or D |
| No browser popups | A or D |
| Familiar Google auth flow | B (Local OAuth) |

### By Implementation Complexity

| Approach | Complexity | Server Changes | CLI Changes |
|----------|------------|----------------|-------------|
| A. SA Key (current) | Low | None | None |
| B. Local OAuth | Medium | IAM setup only | OAuth flow |
| C. Fabric Token Exchange | Medium-High | New /api/token endpoint | Session + token management |
| D. SA Key + Rotation | Low-Medium | Rotation job | Age check |

---

## Final Recommendation

**Approach C (Fabric Token Exchange)** provides the best security properties:

1. **1-hour exposure window** - Only SA token on laptop, expires automatically
2. **Zero OAuth on laptop** - All OAuth credentials stored server-side in Fabric
3. **No GCP blast radius** - SA tokens scoped to sheets/drive only
4. **Instant revocation** - Delete OAuth from Fabric DB
5. **Self-service provisioning** - SA auto-created on first auth
6. **Full audit trail** - Fabric logs all token requests

### Implementation Components

**Fabric Server:**
1. `/api/auth` endpoint - Handle Google OAuth, store credentials in DB
2. SA lookup/creation - Search GCP for user's SA by metadata, create if missing
3. SA impersonation - Use stored OAuth to generate short-lived SA tokens
4. Redirect with token - Return SA token via localhost callback URL
5. OAuth storage - Database table for user → OAuth credentials mapping

**CLI (gsheet-skill):**
1. Token cache check - Use cached token if valid
2. Localhost callback server - Receive token from browser redirect
3. Browser launch - Open Fabric auth URL with redirect parameter
4. Token storage - Save SA token to `~/.config/fabric/token.json`

**GCP Setup:**
1. Fabric admin SA needs `serviceAccountAdmin` + `serviceAccountTokenCreator` at project level
2. Each user SA is created with metadata: `Owner: user@company.com`
3. Each user gets `serviceAccountTokenCreator` on their own SA only

### Sequence Diagram

```
┌─────┐          ┌─────────┐          ┌────────┐          ┌─────┐
│ CLI │          │ Browser │          │ Fabric │          │ GCP │
└──┬──┘          └────┬────┘          └───┬────┘          └──┬──┘
   │                  │                   │                  │
   │ Start localhost  │                   │                  │
   │ server :8085     │                   │                  │
   │──────────────────│                   │                  │
   │                  │                   │                  │
   │ Open browser     │                   │                  │
   │─────────────────>│                   │                  │
   │                  │                   │                  │
   │                  │ GET /api/auth     │                  │
   │                  │ ?redirect=...     │                  │
   │                  │──────────────────>│                  │
   │                  │                   │                  │
   │                  │ Google OAuth      │                  │
   │                  │<─────────────────>│                  │
   │                  │                   │                  │
   │                  │                   │ Store OAuth      │
   │                  │                   │ in DB            │
   │                  │                   │                  │
   │                  │                   │ Search SA        │
   │                  │                   │────────────────>│
   │                  │                   │                  │
   │                  │                   │ (Create if      │
   │                  │                   │  not found)     │
   │                  │                   │────────────────>│
   │                  │                   │                  │
   │                  │                   │ Impersonate SA  │
   │                  │                   │────────────────>│
   │                  │                   │                  │
   │                  │                   │<────────────────│
   │                  │                   │ SA token (1h)   │
   │                  │                   │                  │
   │                  │ Redirect to       │                  │
   │                  │ localhost:8085    │                  │
   │                  │ ?token=xxx        │                  │
   │                  │<──────────────────│                  │
   │                  │                   │                  │
   │ Receive token    │                   │                  │
   │<─────────────────│                   │                  │
   │                  │                   │                  │
   │ Save token       │                   │                  │
   │ Call Sheets API  │                   │                  │
   │─────────────────────────────────────────────────────────>│
   │                  │                   │                  │
```

### Migration Path

1. Deploy Fabric Token Exchange alongside current SA key flow
2. Update gsheet-skill CLI to use new auth flow
3. New employees use token exchange by default
4. Existing employees: CLI detects old credentials, prompts migration
5. Deprecate SA key download after migration complete
6. (Optional) Bulk-delete orphaned SA keys after grace period
