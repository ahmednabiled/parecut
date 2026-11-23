import mimetypes
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import Settings
from app.deps import get_current_user, get_settings_dep
from app.models import User
from app.ratelimit import rate_limit
from app.storage import InvalidToken, ObjectStorage, UploadTooLarge, get_storage

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
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0)
    content_type: str = "application/octet-stream"


class PresignResponse(BaseModel):
    upload_url: str
    upload_key: str
    expires_at: datetime


def _safe_name(filename: str) -> str:
    name = Path(filename).name
    return re.sub(r"[^A-Za-z0-9._-]", "_", name) or "upload"


@router.post(
    "",
    response_model=PresignResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("upload"))],
)
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

    upload_key = f"uploads/{user.id}/{uuid4().hex}/{_safe_name(payload.filename)}"
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

    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > settings.max_upload_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="File exceeds the maximum upload size",
                )
        except ValueError:
            pass

    content_type = request.headers.get("content-type", "application/octet-stream")
    try:
        await storage.put_stream(
            key, request.stream(), content_type, settings.max_upload_bytes
        )
    except UploadTooLarge as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="File exceeds the maximum upload size",
        ) from exc


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

    total = await storage.size(key)
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    safe_filename = filename.replace('"', "").replace("\r", "").replace("\n", "")
    headers = {"Content-Disposition": f'attachment; filename="{safe_filename}"'}
    if total <= 0:
        return Response(content=b"", media_type=media_type, headers=headers)
    headers["Content-Length"] = str(total)
    return StreamingResponse(
        storage.iter_range(key, 0, total - 1),
        media_type=media_type,
        headers=headers,
    )
