from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.db import get_session
from app.deps import get_current_user, get_settings_dep
from app.models import User
from app.schemas import JobCreate, JobRead, to_job_read
from app.services.jobs import InsufficientCredits, UploadNotFound, create_job
from app.services.pipeline import PipelineRunner, get_runner
from app.storage import ObjectStorage, get_storage

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", response_model=JobRead, status_code=status.HTTP_201_CREATED)
async def create(
    payload: JobCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    storage: ObjectStorage = Depends(get_storage),
    runner: PipelineRunner = Depends(get_runner),
    settings: Settings = Depends(get_settings_dep),
):
    try:
        job = await create_job(session, user, storage, runner, settings, payload)
    except UploadNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found"
        ) from exc
    except InsufficientCredits as exc:
        return JSONResponse(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            content={
                "detail": "Insufficient credits",
                "required_minutes": float(exc.required),
                "available_minutes": float(exc.available),
            },
        )
    return to_job_read(job)
