import asyncio
import base64
import hashlib
import hmac
import json
import os
import subprocess
import tempfile
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi import Request
from pydantic import BaseModel


class AudioMetadata(BaseModel):
    duration_seconds: float
    sample_rate: int
    channels: int


class InvalidToken(Exception):
    pass


class UploadTooLarge(Exception):
    pass


class ObjectStorage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    async def put_stream(
        self,
        key: str,
        chunks: AsyncIterator[bytes],
        content_type: str,
        max_bytes: int,
    ) -> int: ...

    async def get(self, key: str) -> bytes: ...

    async def get_range(self, key: str, start: int, end: int) -> bytes: ...

    def iter_range(self, key: str, start: int, end: int) -> Iterator[bytes]: ...

    async def copy(self, src_key: str, dst_key: str) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def list_objects(self, prefix: str) -> list[tuple[str, float]]: ...

    async def exists(self, key: str) -> bool: ...

    async def size(self, key: str) -> int: ...

    async def metadata(self, key: str) -> AudioMetadata | None: ...

    def signed_upload_url(self, key: str, ttl_seconds: int) -> str: ...

    def signed_direct_upload_url(self, key: str, ttl_seconds: int) -> str: ...

    def signed_download_url(self, key: str, filename: str, ttl_seconds: int) -> str: ...

    def verify_upload_token(self, token: str) -> str: ...

    def verify_download_token(self, token: str) -> tuple[str, str]: ...


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


class _SignedTokens:
    def __init__(self, secret_key: str) -> None:
        self._secret = secret_key.encode()

    def sign(self, payload: dict) -> str:
        body = _b64encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        )
        signature = _b64encode(
            hmac.new(self._secret, body.encode(), hashlib.sha256).digest()
        )
        return f"{body}.{signature}"

    def verify(self, token: str, purpose: str) -> dict:
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


def _ffprobe_metadata(source: str) -> AudioMetadata | None:
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
                source,
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


class LocalObjectStorage:
    def __init__(self, root: Path, secret_key: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._tokens = _SignedTokens(secret_key)

    def _path(self, key: str) -> Path:
        path = Path(key)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("invalid storage key")
        return self.root / path

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def put_stream(
        self,
        key: str,
        chunks: AsyncIterator[bytes],
        content_type: str,
        max_bytes: int,
    ) -> int:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_name(f".{path.name}.part")
        total = 0
        try:
            with part.open("wb") as handle:
                async for chunk in chunks:
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        raise UploadTooLarge("File exceeds the maximum upload size")
                    await asyncio.to_thread(handle.write, chunk)
            await asyncio.to_thread(os.replace, part, path)
        except Exception:
            part.unlink(missing_ok=True)
            raise
        return total

    async def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    async def get_range(self, key: str, start: int, end: int) -> bytes:
        def read() -> bytes:
            with self._path(key).open("rb") as handle:
                handle.seek(start)
                return handle.read(end - start + 1)

        return await asyncio.to_thread(read)

    def iter_range(self, key: str, start: int, end: int) -> Iterator[bytes]:
        path = self._path(key)
        remaining = end - start + 1
        with path.open("rb") as handle:
            handle.seek(start)
            while remaining > 0:
                chunk = handle.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    async def copy(self, src_key: str, dst_key: str) -> None:
        await self.put(dst_key, await self.get(src_key), "application/octet-stream")

    async def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    async def list_objects(self, prefix: str) -> list[tuple[str, float]]:
        def _scan() -> list[tuple[str, float]]:
            base = self._path(prefix) if prefix else self.root
            if not base.exists():
                return []
            results: list[tuple[str, float]] = []
            for path in base.rglob("*"):
                if not path.is_file() or path.name.endswith(".part"):
                    continue
                rel = path.relative_to(self.root).as_posix()
                results.append((rel, path.stat().st_mtime))
            return results

        return await asyncio.to_thread(_scan)

    async def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    async def size(self, key: str) -> int:
        return self._path(key).stat().st_size

    async def metadata(self, key: str) -> AudioMetadata | None:
        path = self._path(key)
        if not path.is_file():
            return None
        return await asyncio.to_thread(_ffprobe_metadata, str(path))

    def signed_upload_url(self, key: str, ttl_seconds: int) -> str:
        token = self._tokens.sign(
            {"k": key, "e": int(time.time()) + ttl_seconds, "p": "put"}
        )
        return f"/api/uploads/{token}"

    def signed_direct_upload_url(self, key: str, ttl_seconds: int) -> str:
        return self.signed_upload_url(key, ttl_seconds)

    def signed_download_url(self, key: str, filename: str, ttl_seconds: int) -> str:
        token = self._tokens.sign(
            {
                "k": key,
                "e": int(time.time()) + ttl_seconds,
                "p": "get",
                "f": filename,
            }
        )
        return f"/api/uploads/download/{token}?filename={quote(filename)}"

    def verify_upload_token(self, token: str) -> str:
        payload = self._tokens.verify(token, "put")
        key = payload.get("k")
        if not isinstance(key, str):
            raise InvalidToken("missing key")
        return key

    def verify_download_token(self, token: str) -> tuple[str, str]:
        payload = self._tokens.verify(token, "get")
        key = payload.get("k")
        if not isinstance(key, str):
            raise InvalidToken("missing key")
        return key, str(payload.get("f") or "download")


class R2ObjectStorage:
    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        secret_key: str,
        region: str = "auto",
        client: Any | None = None,
    ) -> None:
        if not bucket or not endpoint_url or not access_key_id or not secret_access_key:
            raise ValueError("R2 storage requires bucket, endpoint, and credentials")
        self.bucket = bucket
        self._tokens = _SignedTokens(secret_key)
        self._client = client or boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
            config=Config(signature_version="s3v4"),
        )

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    async def put_stream(
        self,
        key: str,
        chunks: AsyncIterator[bytes],
        content_type: str,
        max_bytes: int,
    ) -> int:
        total = 0
        with tempfile.SpooledTemporaryFile(max_size=16 * 1024 * 1024) as spool:
            async for chunk in chunks:
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise UploadTooLarge("File exceeds the maximum upload size")
                await asyncio.to_thread(spool.write, chunk)
            spool.seek(0)
            if hasattr(self._client, "upload_fileobj"):
                await asyncio.to_thread(
                    self._client.upload_fileobj,
                    spool,
                    self.bucket,
                    key,
                    ExtraArgs={"ContentType": content_type},
                )
            else:
                data = await asyncio.to_thread(spool.read)
                await self.put(key, data, content_type)
        return total

    async def get(self, key: str) -> bytes:
        response = await asyncio.to_thread(
            self._client.get_object, Bucket=self.bucket, Key=key
        )
        return await asyncio.to_thread(response["Body"].read)

    async def get_range(self, key: str, start: int, end: int) -> bytes:
        response = await asyncio.to_thread(
            self._client.get_object,
            Bucket=self.bucket,
            Key=key,
            Range=f"bytes={start}-{end}",
        )
        return await asyncio.to_thread(response["Body"].read)

    def iter_range(self, key: str, start: int, end: int) -> Iterator[bytes]:
        response = self._client.get_object(
            Bucket=self.bucket,
            Key=key,
            Range=f"bytes={start}-{end}",
        )
        body = response["Body"]
        try:
            while True:
                chunk = body.read(256 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            body.close()

    async def copy(self, src_key: str, dst_key: str) -> None:
        await asyncio.to_thread(
            self._client.copy_object,
            Bucket=self.bucket,
            CopySource={"Bucket": self.bucket, "Key": src_key},
            Key=dst_key,
        )

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(
            self._client.delete_object, Bucket=self.bucket, Key=key
        )

    async def list_objects(self, prefix: str) -> list[tuple[str, float]]:
        def _list() -> list[tuple[str, float]]:
            results: list[tuple[str, float]] = []
            token: str | None = None
            while True:
                kwargs: dict[str, Any] = {"Bucket": self.bucket, "Prefix": prefix}
                if token:
                    kwargs["ContinuationToken"] = token
                response = self._client.list_objects_v2(**kwargs)
                for item in response.get("Contents", []):
                    key = item.get("Key")
                    modified = item.get("LastModified")
                    if isinstance(key, str) and modified is not None:
                        ts = (
                            modified.timestamp()
                            if hasattr(modified, "timestamp")
                            else float(modified)
                        )
                        results.append((key, ts))
                if not response.get("IsTruncated"):
                    break
                token = response.get("NextContinuationToken")
                if not token:
                    break
            return results

        return await asyncio.to_thread(_list)

    async def exists(self, key: str) -> bool:
        try:
            await asyncio.to_thread(
                self._client.head_object, Bucket=self.bucket, Key=key
            )
            return True
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    async def size(self, key: str) -> int:
        response = await asyncio.to_thread(
            self._client.head_object, Bucket=self.bucket, Key=key
        )
        return int(response["ContentLength"])

    async def metadata(self, key: str) -> AudioMetadata | None:
        url = self.signed_download_url(key, Path(key).name, 300)
        return await asyncio.to_thread(_ffprobe_metadata, url)

    def signed_upload_url(self, key: str, ttl_seconds: int) -> str:
        token = self._tokens.sign(
            {"k": key, "e": int(time.time()) + ttl_seconds, "p": "put"}
        )
        return f"/api/uploads/{token}"

    def signed_direct_upload_url(self, key: str, ttl_seconds: int) -> str:
        return self._client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=ttl_seconds,
        )

    def signed_download_url(self, key: str, filename: str, ttl_seconds: int) -> str:
        safe_filename = filename.replace('"', "").replace("\r", "").replace("\n", "")
        return self._client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ResponseContentDisposition": f'attachment; filename="{safe_filename}"',
            },
            ExpiresIn=ttl_seconds,
        )

    def verify_upload_token(self, token: str) -> str:
        payload = self._tokens.verify(token, "put")
        key = payload.get("k")
        if not isinstance(key, str):
            raise InvalidToken("missing key")
        return key

    def verify_download_token(self, token: str) -> tuple[str, str]:
        raise InvalidToken("R2 storage uses direct downloads")


def get_storage(request: Request) -> ObjectStorage:
    return request.app.state.storage
