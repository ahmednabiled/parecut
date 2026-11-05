from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db import get_session
from app.deps import get_current_user
from app.models import CreditLedger, Job, JobArtifact, User, UserProfile
from app.schemas import (
    LedgerRead,
    ProfileResponse,
    ProfileUpdate,
    to_job_read,
    to_profile_read,
    to_user_read,
)

router = APIRouter(prefix="/api/profile", tags=["profile"])


async def _build_response(
    session: AsyncSession, user: User, profile: UserProfile
) -> ProfileResponse:
    jobs = (
        await session.exec(
            select(Job).where(Job.user_id == user.id).order_by(Job.created_at.desc()).limit(10)
        )
    ).all()
    ledger = (
        await session.exec(
            select(CreditLedger)
            .where(CreditLedger.user_id == user.id)
            .order_by(CreditLedger.created_at.desc())
            .limit(20)
        )
    ).all()

    artifacts = (
        await session.exec(
            select(JobArtifact)
            .where(JobArtifact.job_id.in_([job.id for job in jobs]))
            .order_by(JobArtifact.created_at)
        )
    ).all()
    grouped: dict[str, list[JobArtifact]] = defaultdict(list)
    for artifact in artifacts:
        grouped[artifact.job_id].append(artifact)

    return ProfileResponse(
        user=to_user_read(user),
        profile=to_profile_read(profile),
        jobs=[to_job_read(job, grouped[job.id]) for job in jobs],
        ledger=[
            LedgerRead(
                id=entry.id,
                job_id=entry.job_id,
                delta_minutes=float(entry.delta_minutes),
                reason=entry.reason,
                created_at=entry.created_at,
            )
            for entry in ledger
        ],
    )


@router.get("", response_model=ProfileResponse)
async def get_profile(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ProfileResponse:
    profile = await session.get(UserProfile, user.id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return await _build_response(session, user, profile)


@router.patch("", response_model=ProfileResponse)
async def update_profile(
    payload: ProfileUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ProfileResponse:
    profile = await session.get(UserProfile, user.id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    changes = payload.model_dump(exclude_unset=True)
    if "full_name" in changes:
        user.full_name = changes["full_name"].strip()
        session.add(user)
    for field in ("default_fps", "default_enhance_mix", "default_silence_pad_ms"):
        if field in changes:
            setattr(profile, field, changes[field])
    session.add(profile)
    await session.commit()

    return await _build_response(session, user, profile)
