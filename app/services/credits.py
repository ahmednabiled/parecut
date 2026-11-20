import math
from decimal import Decimal

from sqlalchemy import update
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import CreditLedger, UserProfile, utcnow


def reserve_minutes(duration_seconds: float | None) -> Decimal:
    if duration_seconds is None:
        return Decimal("1")
    return Decimal(max(1, math.ceil(duration_seconds / 60)))


async def add_ledger_entry(
    session: AsyncSession,
    profile: UserProfile,
    *,
    delta: Decimal,
    reason: str,
    job_id: str | None = None,
) -> CreditLedger:
    entry = CreditLedger(
        user_id=profile.user_id,
        job_id=job_id,
        delta_minutes=delta,
        reason=reason,
    )
    profile.credit_balance_minutes = (
        Decimal(profile.credit_balance_minutes or 0) + delta
    )
    profile.updated_at = utcnow()
    session.add(entry)
    session.add(profile)
    await session.flush()
    return entry


async def reserve_credits(
    session: AsyncSession,
    user_id: str,
    *,
    minutes: Decimal,
    job_id: str,
) -> tuple[bool, Decimal | None]:
    """Atomically deduct `minutes` if the user has sufficient balance.

    Returns (True, None) on success, or (False, available_minutes) when
    insufficient (or (False, None) if the profile does not exist).
    """
    result = await session.exec(
        update(UserProfile)
        .where(
            UserProfile.user_id == user_id,
            UserProfile.credit_balance_minutes >= minutes,
        )
        .values(
            credit_balance_minutes=UserProfile.credit_balance_minutes - minutes,
            updated_at=utcnow(),
        )
    )
    if (result.rowcount or 0) == 1:
        session.add(
            CreditLedger(
                user_id=user_id,
                job_id=job_id,
                delta_minutes=-minutes,
                reason="job_reserve",
            )
        )
        await session.flush()
        return True, None

    profile = await session.get(UserProfile, user_id)
    if profile is None:
        return False, None
    return False, Decimal(profile.credit_balance_minutes or 0)
