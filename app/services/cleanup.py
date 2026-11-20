import asyncio
import logging
import time

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select

from app.models import Job
from app.storage import ObjectStorage

logger = logging.getLogger(__name__)


async def cleanup_abandoned_uploads(
    sessionmaker: async_sessionmaker,
    storage: ObjectStorage,
    *,
    max_age_seconds: int = 86_400,
    now: float | None = None,
) -> int:
    """Delete objects under `uploads/` older than `max_age_seconds` that are not
    referenced by any Job row. Returns the number of deleted objects."""
    cutoff = (now if now is not None else time.time()) - max_age_seconds
    candidates = [
        key
        for key, modified_at in await storage.list_objects("uploads")
        if modified_at <= cutoff
    ]
    if not candidates:
        return 0

    async with sessionmaker() as session:
        referenced = set(
            (
                await session.exec(
                    select(Job.source_r2_key).where(
                        Job.source_r2_key.in_(candidates)
                    )
                )
            ).all()
        )

    deleted = 0
    for key in candidates:
        if key in referenced:
            continue
        try:
            await storage.delete(key)
            deleted += 1
        except Exception:
            logger.exception("failed to delete abandoned upload %s", key)
    if deleted:
        logger.info("cleaned up %d abandoned upload(s)", deleted)
    return deleted


async def periodic_cleanup(
    sessionmaker: async_sessionmaker,
    storage: ObjectStorage,
    *,
    ttl_seconds: int,
    interval_seconds: int,
) -> None:
    while True:
        try:
            await cleanup_abandoned_uploads(
                sessionmaker, storage, max_age_seconds=ttl_seconds
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("abandoned upload cleanup pass failed")
        await asyncio.sleep(interval_seconds)
