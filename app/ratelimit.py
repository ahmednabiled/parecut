import math
import time
from collections import deque
from typing import Literal

from fastapi import Depends, HTTPException, Request, status

from app.config import Settings
from app.deps import get_settings_dep

RateLimitBucket = Literal["auth", "upload", "job"]


class RateLimiter:
    """Lightweight sliding-window in-memory rate limiter with bounded memory."""

    def __init__(self, *, window_seconds: float = 60.0, max_keys: int = 10_000) -> None:
        self._window = window_seconds
        self._max_keys = max_keys
        self._hits: dict[tuple[str, str], deque[float]] = {}

    def check(
        self,
        bucket: str,
        key: str,
        *,
        limit: int,
        now: float | None = None,
    ) -> tuple[bool, int]:
        if limit <= 0:
            return True, 0
        current = time.monotonic() if now is None else now
        cutoff = current - self._window
        compound = (bucket, key)
        timestamps = self._hits.get(compound)
        if timestamps is None:
            if len(self._hits) >= self._max_keys:
                self._evict(cutoff)
            timestamps = deque()
            self._hits[compound] = timestamps

        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()

        if len(timestamps) >= limit:
            retry_after = max(1, math.ceil(timestamps[0] + self._window - current))
            return False, retry_after

        timestamps.append(current)
        return True, 0

    def _evict(self, cutoff: float) -> None:
        stale = [
            key
            for key, timestamps in self._hits.items()
            if not timestamps or timestamps[-1] <= cutoff
        ]
        for key in stale:
            self._hits.pop(key, None)
        if len(self._hits) >= self._max_keys:
            self._hits.pop(next(iter(self._hits)), None)


def client_ip(request: Request, settings: Settings) -> str:
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            first = forwarded.split(",", 1)[0].strip()
            if first:
                return first
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _bucket_limit(settings: Settings, bucket: RateLimitBucket) -> int:
    if bucket == "auth":
        return settings.rate_limit_auth_per_minute
    if bucket == "upload":
        return settings.rate_limit_upload_per_minute
    return settings.rate_limit_job_per_minute


def rate_limit(bucket: RateLimitBucket):
    async def _dependency(
        request: Request,
        settings: Settings = Depends(get_settings_dep),
    ) -> None:
        if not settings.is_rate_limit_enabled():
            return
        limiter: RateLimiter | None = getattr(request.app.state, "rate_limiter", None)
        if limiter is None:
            return
        allowed, retry_after = limiter.check(
            bucket,
            client_ip(request, settings),
            limit=_bucket_limit(settings, bucket),
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )

    return _dependency
