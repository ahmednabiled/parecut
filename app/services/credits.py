import math
from decimal import Decimal

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
