from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.db import get_session
from app.deps import get_current_user, get_settings_dep
from app.models import User, UserProfile
from app.schemas import (
    LoginRequest,
    RegisterRequest,
    SessionUser,
    to_profile_read,
    to_user_read,
)
from app.security import (
    clear_session_cookie,
    create_session_token,
    hash_password,
    set_session_cookie,
    verify_password,
)
from app.services.credits import add_ledger_entry

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=SessionUser, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> SessionUser:
    email = payload.email.strip().lower()
    existing = (await session.exec(select(User).where(User.email == email))).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name.strip(),
    )
    session.add(user)
    await session.flush()

    profile = UserProfile(user_id=user.id, credit_balance_minutes=Decimal("0"))
    session.add(profile)
    await session.flush()
    await add_ledger_entry(
        session,
        profile,
        delta=settings.signup_bonus_minutes,
        reason="signup_bonus",
    )
    await session.commit()

    set_session_cookie(response, create_session_token(user.id, settings), settings)
    return SessionUser(user=to_user_read(user), profile=to_profile_read(profile))


@router.post("/login", response_model=SessionUser)
async def login(
    payload: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> SessionUser:
    email = payload.email.strip().lower()
    user = (await session.exec(select(User).where(User.email == email))).first()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    profile = await session.get(UserProfile, user.id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    set_session_cookie(response, create_session_token(user.id, settings), settings)
    return SessionUser(user=to_user_read(user), profile=to_profile_read(profile))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    settings: Settings = Depends(get_settings_dep),
) -> None:
    clear_session_cookie(response, settings)


@router.get("/me", response_model=SessionUser)
async def me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SessionUser:
    profile = await session.get(UserProfile, user.id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return SessionUser(user=to_user_read(user), profile=to_profile_read(profile))
