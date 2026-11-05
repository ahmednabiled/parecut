import mimetypes
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.config import Settings
from app.deps import get_current_user, get_settings_dep
from app.models import User
from app.storage import InvalidToken, ObjectStorage, get_storage

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

ALLOWED_EXTENSIONS = {
    "wav",
    "flac",
    "mp3",
    "m4a",
    "aac",
    "ogg",
    "mp4",
    "mov",
    "mkv",
    "webm",
}


class PresignRequest(BaseModel):
    filename: str
    size_bytes: int
    content_type: str = "application/octet-stream"


class PresignResponse(BaseModel):
    upload_url: str
    upload_key: str
    expires_at: datetime


def _safe_name(filename: str) -> str:
    name = Path(filename).name
    return re.sub(r"[^A-Za-z0-9._-]", "_", name) or "upload"


@router.post("", response_model=PresignResponse, status_code=status.HTTP_201_CREATED)
async def presign_upload(
    payload: PresignRequest,
    user: User = Depends(get_current_user),
    storage: ObjectStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings_dep),
) -> PresignResponse:
    extension = Path(payload.filename).suffix.lower().lstrip(".")
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unsupported file type: {extension or 'none'}",
        )
    if payload.size_bytes > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="File exceeds the maximum upload size",
        )

    upload_key = f"uploads/{uuid4().hex}/{_safe_name(payload.filename)}"
    upload_url = storage.signed_upload_url(upload_key, settings.upload_url_ttl_seconds)
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=settings.upload_url_ttl_seconds
    )
    return PresignResponse(
        upload_url=upload_url, upload_key=upload_key, expires_at=expires_at
    )


@router.put("/{token}", status_code=status.HTTP_204_NO_CONTENT)
async def receive_upload(
    token: str,
    request: Request,
    storage: ObjectStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings_dep),
) -> None:
    try:
        key = storage.verify_upload_token(token)
    except InvalidToken as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid upload token"
        ) from exc

    body = await request.body()
    if len(body) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="File exceeds the maximum upload size",
        )
    await storage.put(key, body, request.headers.get("content-type", "application/octet-stream"))


@router.get("/download/{token}")
async def download_signed(
    token: str,
    storage: ObjectStorage = Depends(get_storage),
) -> Response:
    try:
        key, filename = storage.verify_download_token(token)
    except InvalidToken as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid download token"
        ) from exc

    if not await storage.exists(key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    data = await storage.get(key)
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    safe_filename = filename.replace('"', "")
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'},
    )
