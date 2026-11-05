import base64
import hashlib
import hmac
import json
import subprocess
import time
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from fastapi import Request
from pydantic import BaseModel


class AudioMetadata(BaseModel):
    duration_seconds: float
    sample_rate: int
    channels: int


class InvalidToken(Exception):
    pass


class ObjectStorage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    async def get(self, key: str) -> bytes: ...

    async def copy(self, src_key: str, dst_key: str) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def exists(self, key: str) -> bool: ...

    async def size(self, key: str) -> int: ...

    async def metadata(self, key: str) -> AudioMetadata | None: ...

    def signed_upload_url(self, key: str, ttl_seconds: int) -> str: ...

    def signed_download_url(self, key: str, filename: str, ttl_seconds: int) -> str: ...

    def verify_upload_token(self, token: str) -> str: ...

    def verify_download_token(self, token: str) -> tuple[str, str]: ...


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


class LocalObjectStorage:
    def __init__(self, root: Path, secret_key: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._secret = secret_key.encode()

    def _path(self, key: str) -> Path:
        path = Path(key)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("invalid storage key")
        return self.root / path

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    async def copy(self, src_key: str, dst_key: str) -> None:
        await self.put(dst_key, await self.get(src_key), "application/octet-stream")

    async def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    async def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    async def size(self, key: str) -> int:
        return self._path(key).stat().st_size

    async def metadata(self, key: str) -> AudioMetadata | None:
        path = self._path(key)
        if not path.is_file():
            return None
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return None
            payload = json.loads(result.stdout)
            audio = next(
                (s for s in payload.get("streams", []) if s.get("codec_type") == "audio"),
                None,
            )
            duration = payload.get("format", {}).get("duration")
            if audio is None or duration is None:
                return None
            return AudioMetadata(
                duration_seconds=float(duration),
                sample_rate=int(audio["sample_rate"]),
                channels=int(audio["channels"]),
            )
        except (OSError, ValueError, KeyError, subprocess.SubprocessError, json.JSONDecodeError):
            return None

    def _sign(self, payload: dict) -> str:
        body = _b64encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        )
        signature = _b64encode(
            hmac.new(self._secret, body.encode(), hashlib.sha256).digest()
        )
        return f"{body}.{signature}"

    def _verify(self, token: str, purpose: str) -> dict:
        try:
            body, signature = token.split(".")
        except ValueError as exc:
            raise InvalidToken("malformed token") from exc

        expected = _b64encode(
            hmac.new(self._secret, body.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            raise InvalidToken("bad signature")

        try:
            payload = json.loads(_b64decode(body))
        except (ValueError, json.JSONDecodeError) as exc:
            raise InvalidToken("bad payload") from exc

        if payload.get("p") != purpose:
            raise InvalidToken("wrong purpose")
        if int(payload.get("e", 0)) < int(time.time()):
            raise InvalidToken("expired")
        return payload

    def signed_upload_url(self, key: str, ttl_seconds: int) -> str:
        token = self._sign({"k": key, "e": int(time.time()) + ttl_seconds, "p": "put"})
        return f"/api/uploads/{token}"

    def signed_download_url(self, key: str, filename: str, ttl_seconds: int) -> str:
        token = self._sign(
            {
                "k": key,
                "e": int(time.time()) + ttl_seconds,
                "p": "get",
                "f": filename,
            }
        )
        return f"/api/uploads/download/{token}?filename={quote(filename)}"

    def verify_upload_token(self, token: str) -> str:
        payload = self._verify(token, "put")
        key = payload.get("k")
        if not isinstance(key, str):
            raise InvalidToken("missing key")
        return key

    def verify_download_token(self, token: str) -> tuple[str, str]:
        payload = self._verify(token, "get")
        key = payload.get("k")
        if not isinstance(key, str):
            raise InvalidToken("missing key")
        return key, str(payload.get("f") or "download")


def get_storage(request: Request) -> ObjectStorage:
    return request.app.state.storage
