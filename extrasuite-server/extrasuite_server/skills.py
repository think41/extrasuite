"""Skills download API.

Provides endpoints to download skill packages for Claude Code/Codex.
Protected by short-lived signed tokens.
"""

import io
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from loguru import logger

from extrasuite_server.config import Settings, get_settings

router = APIRouter()

# Token expiry in seconds (5 minutes)
DOWNLOAD_TOKEN_TTL = 300

# Skills directory paths
# In Docker (production): /app/skills (copied during build)
# In development: repo_root/skills
_DOCKER_SKILLS_DIR = Path("/app/skills")
_DEV_SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"

# Use Docker path if it exists, otherwise fall back to dev path
SKILLS_DIR = _DOCKER_SKILLS_DIR if _DOCKER_SKILLS_DIR.exists() else _DEV_SKILLS_DIR

# Files/directories to exclude from the zip
EXCLUDED_PATTERNS = {
    "venv",
    "__pycache__",
    ".git",
    ".DS_Store",
    "*.pyc",
    ".gitignore",
}


def _should_exclude(path: Path) -> bool:
    """Check if a path should be excluded from the zip."""
    for pattern in EXCLUDED_PATTERNS:
        if pattern.startswith("*"):
            # Glob pattern for extension
            if path.name.endswith(pattern[1:]):
                return True
        elif path.name == pattern:
            return True
        # Check if any parent matches
        for parent in path.parents:
            if parent.name == pattern:
                return True
    return False


def _get_serializer(settings: Settings) -> URLSafeTimedSerializer:
    """Get a serializer for signing download tokens."""
    return URLSafeTimedSerializer(settings.secret_key, salt="skills-download")


@router.post("/download-token")
async def generate_download_token(
    request: Request,
    settings: Settings = None,
) -> dict:
    """Generate a short-lived token for downloading skills.

    Requires authentication - user must be logged in.
    Returns a signed token that can be used to download the skills zip.
    """
    if settings is None:
        settings = get_settings()

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
    settings: Settings = None,
) -> StreamingResponse:
    """Download the skills package as a zip file.

    Requires a valid download token (no session/cookie needed).
    This allows curl-based downloads without browser authentication.
    """
    if settings is None:
        settings = get_settings()

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
    logger.info("Skills download started", extra={"email": email})

    # Find the gsheets skill directory
    gsheets_dir = SKILLS_DIR / "gsheets"
    if not gsheets_dir.exists():
        logger.error("Skills directory not found", extra={"path": str(gsheets_dir)})
        raise HTTPException(status_code=500, detail="Skills package not available")

    # Create zip in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in gsheets_dir.rglob("*"):
            if file_path.is_file() and not _should_exclude(file_path):
                # Archive name is relative to gsheets_dir, but we put files in gsheets/
                arcname = "gsheets/" + str(file_path.relative_to(gsheets_dir))
                zf.write(file_path, arcname)

    zip_buffer.seek(0)

    logger.info("Skills download completed", extra={"email": email})

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=extrasuite-skills.zip"},
    )
