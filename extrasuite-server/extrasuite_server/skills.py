"""Skills download API.

Provides endpoints to download skill packages for Claude Code/Codex.
Protected by short-lived signed tokens.

Skills distribution:
- Enterprise (bundled): /app/skills.zip is served via authenticated download
- Public (default): Install script downloads directly from GitHub releases
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from loguru import logger

from extrasuite_server.config import Settings, get_settings

router = APIRouter()

# Token expiry in seconds (5 minutes)
DOWNLOAD_TOKEN_TTL = 300

# Bundled skills zip path (only exists in enterprise Docker images)
_DOCKER_SKILLS_ZIP = Path("/app/skills.zip")


def _get_serializer(settings: Settings) -> URLSafeTimedSerializer:
    """Get a serializer for signing download tokens."""
    return URLSafeTimedSerializer(settings.secret_key, salt="skills-download")


@router.post("/download-token")
async def generate_download_token(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Generate a short-lived token for downloading skills.

    Requires authentication - user must be logged in.
    Returns a signed token that can be used to download the skills zip.
    """
    email = request.session.get("email")
    if not email:
        raise HTTPException(status_code=403, detail="Authentication required")

    serializer = _get_serializer(settings)
    token = serializer.dumps({"email": email, "purpose": "skills-download"})

    logger.info("Skills download token generated", extra={"email": email})

    return {"token": token, "expires_in": DOWNLOAD_TOKEN_TTL}


@router.get("/download")
async def download_skills(
    token: str = Query(..., description="Download token from /api/skills/download-token"),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    """Download the skills package as a zip file.

    Only available when bundled skills.zip exists (enterprise deployment).
    Requires a valid download token (no session/cookie needed).
    """
    serializer = _get_serializer(settings)

    try:
        data = serializer.loads(token, max_age=DOWNLOAD_TOKEN_TTL)
    except SignatureExpired:
        logger.warning("Skills download token expired")
        raise HTTPException(status_code=401, detail="Download token expired") from None
    except BadSignature:
        logger.warning("Invalid skills download token")
        raise HTTPException(status_code=401, detail="Invalid download token") from None

    if data.get("purpose") != "skills-download":
        raise HTTPException(status_code=401, detail="Invalid token purpose")

    email = data.get("email", "unknown")

    # Only serve bundled skills.zip (enterprise deployment)
    if not _DOCKER_SKILLS_ZIP.exists():
        logger.warning(
            "Skills download requested but no bundled skills.zip", extra={"email": email}
        )
        raise HTTPException(status_code=404, detail="Skills package not available")

    logger.info("Skills download started", extra={"email": email})

    return FileResponse(
        _DOCKER_SKILLS_ZIP,
        media_type="application/zip",
        filename="extrasuite-skills.zip",
    )


@router.get("/install/{token}")
async def get_install_script(
    token: str,
    ps: bool = Query(False, description="Return PowerShell script instead of bash"),
    settings: Settings = Depends(get_settings),
) -> PlainTextResponse:
    """Get a personalized install script with download URL embedded.

    The token is validated and used to generate a download URL.
    Returns a bash script by default, or PowerShell if ps=true.

    If bundled skills.zip exists (enterprise): downloads from server.
    Otherwise: downloads directly from GitHub releases.
    """
    serializer = _get_serializer(settings)

    try:
        data = serializer.loads(token, max_age=DOWNLOAD_TOKEN_TTL)
    except SignatureExpired:
        logger.warning("Install script token expired")
        if ps:
            script = 'Write-Error "Install link expired. Please get a new one from the website."'
        else:
            script = '#!/bin/bash\necho "Error: Install link expired. Please get a new one from the website."\nexit 1'
        return PlainTextResponse(script, media_type="text/plain")
    except BadSignature:
        logger.warning("Invalid install script token")
        if ps:
            script = 'Write-Error "Invalid install link."'
        else:
            script = '#!/bin/bash\necho "Error: Invalid install link."\nexit 1'
        return PlainTextResponse(script, media_type="text/plain")

    if data.get("purpose") != "skills-download":
        if ps:
            script = 'Write-Error "Invalid token."'
        else:
            script = '#!/bin/bash\necho "Error: Invalid token."\nexit 1'
        return PlainTextResponse(script, media_type="text/plain")

    email = data.get("email", "unknown")
    logger.info("Install script requested", extra={"email": email, "powershell": ps})

    # Determine download URL based on whether bundled skills.zip exists
    base_url = settings.server_url.rstrip("/")
    if _DOCKER_SKILLS_ZIP.exists():
        # Enterprise: download from server with auth token
        download_url = f"{base_url}/api/skills/download?token={token}"
    else:
        # Public: download directly from GitHub
        download_url = settings.default_skills_url

    # Read the appropriate template and substitute placeholders
    script_file = "install.ps1" if ps else "install.sh"
    script_template = Path(__file__).parent / "static" / script_file
    script = script_template.read_text()
    script = script.replace("__DOWNLOAD_URL__", download_url)
    script = script.replace("__SERVER_URL__", base_url)

    return PlainTextResponse(script, media_type="text/plain")
