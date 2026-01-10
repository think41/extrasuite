"""Service account creation API endpoints."""

import json
import re
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import BaseModel

from fabric.auth.api import SessionData, get_current_user
from fabric.config import Settings, get_settings

router = APIRouter(prefix="/service-account", tags=["service-account"])


class MagicToken(BaseModel):
    """Magic token for service account download."""

    token: str
    expires_at: str
    command_macos: str
    command_linux: str
    command_windows: str


class ServiceAccountStatus(BaseModel):
    """Service account status for a user."""

    exists: bool
    email: str | None = None
    display_name: str | None = None
    description: str | None = None  # Contains owner email and creation date for traceability


class ServiceAccountDownload(BaseModel):
    """Service account JSON credentials."""

    credentials: dict
    email: str
    save_path: str


# In-memory token storage (use Redis in production for distributed environments)
# Format: {token: {"email": user_email, "expires_at": datetime, "used": bool}}
_magic_tokens: dict[str, dict] = {}


def get_iam_service(settings: Settings):
    """Get Google IAM service client using application default credentials."""
    if not settings.google_cloud_project:
        raise HTTPException(
            status_code=500,
            detail="Google Cloud project not configured. Set GOOGLE_CLOUD_PROJECT.",
        )

    # Use application default credentials or service account from env
    try:
        # This will use GOOGLE_APPLICATION_CREDENTIALS environment variable
        credentials = service_account.Credentials.from_service_account_file(
            "credentials/admin-service-account.json",
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        return build("iam", "v1", credentials=credentials)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize IAM service: {e}",
        ) from None


def sanitize_email_for_account_id(email: str) -> str:
    """Convert email to valid service account ID.

    Service account IDs must:
    - Be 6-30 characters
    - Start with a letter
    - Contain only lowercase letters, numbers, and hyphens
    """
    # Take part before @
    local_part = email.split("@")[0].lower()

    # Replace invalid characters with hyphens
    account_id = re.sub(r"[^a-z0-9]", "-", local_part)

    # Remove consecutive hyphens
    account_id = re.sub(r"-+", "-", account_id)

    # Remove leading/trailing hyphens
    account_id = account_id.strip("-")

    # Ensure it starts with a letter
    if account_id and not account_id[0].isalpha():
        account_id = "ea-" + account_id

    # Prefix with ea- (executive assistant) for clarity
    if not account_id.startswith("ea-"):
        account_id = "ea-" + account_id

    # Truncate to 30 characters max
    account_id = account_id[:30].rstrip("-")

    # Ensure minimum length of 6
    if len(account_id) < 6:
        account_id = account_id + "-user"

    return account_id


def get_download_command(base_url: str, token: str, os_type: str) -> str:
    """Generate OS-specific download command."""
    download_url = f"{base_url}/api/service-account/download/{token}"

    if os_type == "macos" or os_type == "linux":
        return f"""curl -s "{download_url}" | python3 -c "
import json, sys, os, pathlib
data = json.load(sys.stdin)
if 'error' in data: print(f'Error: {{data[\"error\"]}}'); sys.exit(1)
path = pathlib.Path.home() / '.fabric' / 'credentials.json'
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data['credentials'], indent=2))
print(f'Credentials saved to {{path}}')
print(f'Your AI EA email: {{data[\"email\"]}}')"
"""
    else:  # windows
        return f"""powershell -Command "
$response = Invoke-RestMethod -Uri '{download_url}'
if ($response.error) {{ Write-Error $response.error; exit 1 }}
$path = Join-Path $env:USERPROFILE '.fabric\\credentials.json'
$parent = Split-Path $path -Parent
if (!(Test-Path $parent)) {{ New-Item -ItemType Directory -Path $parent -Force }}
$response.credentials | ConvertTo-Json -Depth 10 | Set-Content $path
Write-Host 'Credentials saved to' $path
Write-Host 'Your AI EA email:' $response.email"
"""


@router.post("/init", response_model=MagicToken)
async def init_service_account(
    user: SessionData = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> MagicToken:
    """Initialize service account creation and return magic token with download commands.

    This endpoint generates an ephemeral token that can be used once to download
    the service account credentials. The token expires after 5 minutes.
    """
    # Generate ephemeral token
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.magic_token_expiry)

    # Store token
    _magic_tokens[token] = {
        "email": user.email,
        "name": user.name,
        "expires_at": expires_at,
        "used": False,
    }

    # Clean up expired tokens
    now = datetime.now(UTC)
    for old_token in list(_magic_tokens.keys()):
        if _magic_tokens[old_token]["expires_at"] < now:
            del _magic_tokens[old_token]

    # Generate download commands for each OS
    # In production, this would be the actual server URL
    base_url = (
        f"http://localhost:{settings.port}"
        if not settings.is_production
        else "https://fabric.think41.com"
    )

    return MagicToken(
        token=token,
        expires_at=expires_at.isoformat(),
        command_macos=get_download_command(base_url, token, "macos"),
        command_linux=get_download_command(base_url, token, "linux"),
        command_windows=get_download_command(base_url, token, "windows"),
    )


@router.get("/download/{token}")
async def download_service_account(
    token: str,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Download service account credentials using magic token.

    This is a one-time use endpoint. The token is invalidated after use.
    The credentials are created on-demand when this endpoint is called.
    """
    # Validate token
    if token not in _magic_tokens:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid or expired token"},
        )

    token_data = _magic_tokens[token]

    # Check expiry
    if datetime.now(UTC) > token_data["expires_at"]:
        del _magic_tokens[token]
        return JSONResponse(
            status_code=400,
            content={"error": "Token expired"},
        )

    # Check if already used
    if token_data["used"]:
        return JSONResponse(
            status_code=400,
            content={"error": "Token already used"},
        )

    # Mark as used immediately to prevent race conditions
    _magic_tokens[token]["used"] = True

    user_email = token_data["email"]
    user_name = token_data["name"]

    try:
        # Create service account
        iam_service = get_iam_service(settings)
        project_id = settings.google_cloud_project
        account_id = sanitize_email_for_account_id(user_email)

        # Check if service account already exists
        service_account_email = f"{account_id}@{project_id}.iam.gserviceaccount.com"

        try:
            existing = (
                iam_service.projects()
                .serviceAccounts()
                .get(name=f"projects/{project_id}/serviceAccounts/{service_account_email}")
                .execute()
            )
            # Service account exists, create new key
            sa_email = existing["email"]
        except HttpError as e:
            if e.resp.status == 404:
                # Create new service account with traceability metadata
                # displayName: Short name visible in GCP Console (max 100 chars)
                # description: Detailed info for audit (max 256 chars)
                created_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
                service_account_body = {
                    "accountId": account_id,
                    "serviceAccount": {
                        "displayName": f"AI EA for {user_name}"[:100],
                        "description": f"Owner: {user_email} | Created: {created_at} | Via: Fabric Portal"[
                            :256
                        ],
                    },
                }

                created = (
                    iam_service.projects()
                    .serviceAccounts()
                    .create(name=f"projects/{project_id}", body=service_account_body)
                    .execute()
                )
                sa_email = created["email"]
            else:
                raise

        # Create a new key for the service account
        key = (
            iam_service.projects()
            .serviceAccounts()
            .keys()
            .create(
                name=f"projects/{project_id}/serviceAccounts/{sa_email}",
                body={"keyAlgorithm": "KEY_ALG_RSA_2048"},
            )
            .execute()
        )

        # Decode the private key data (base64 encoded JSON)
        import base64

        credentials_json = json.loads(base64.b64decode(key["privateKeyData"]).decode("utf-8"))

        # Clean up token
        del _magic_tokens[token]

        return JSONResponse(
            content={
                "credentials": credentials_json,
                "email": sa_email,
                "save_path": "~/.fabric/credentials.json",
            }
        )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Clean up on error, allow retry
        if token in _magic_tokens:
            _magic_tokens[token]["used"] = False
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to create service account: {str(e)}"},
        )


@router.get("/status", response_model=ServiceAccountStatus)
async def get_status(
    user: SessionData = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> ServiceAccountStatus:
    """Check if user has a service account created.

    This checks if a service account exists for the user in the Google Cloud project.
    """
    try:
        iam_service = get_iam_service(settings)
        project_id = settings.google_cloud_project
        account_id = sanitize_email_for_account_id(user.email)
        service_account_email = f"{account_id}@{project_id}.iam.gserviceaccount.com"

        try:
            sa = (
                iam_service.projects()
                .serviceAccounts()
                .get(name=f"projects/{project_id}/serviceAccounts/{service_account_email}")
                .execute()
            )
            return ServiceAccountStatus(
                exists=True,
                email=sa["email"],
                display_name=sa.get("displayName"),
                description=sa.get("description"),  # Contains owner info for traceability
            )
        except HttpError as e:
            if e.resp.status == 404:
                return ServiceAccountStatus(exists=False)
            raise

    except HTTPException:
        raise
    except Exception:
        # If we can't check, assume doesn't exist
        return ServiceAccountStatus(exists=False)
