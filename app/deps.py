from fastapi import Depends, HTTPException, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.db import get_session
from app.models import User
from app.security import decode_session_token


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> User:
    token = request.cookies.get(settings.session_cookie)
    user_id = decode_session_token(token, settings) if token else None
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


async def get_current_user_id(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
) -> str:
    """Authenticate with a short-lived session.

    Used by media endpoints that keep the response open for a long time; they
    must not pin a pooled connection while streaming from object storage.
    """
    token = request.cookies.get(settings.session_cookie)
    user_id = decode_session_token(token, settings) if token else None
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    async with request.app.state.sessionmaker() as session:
        user = await session.get(User, user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )
    return user_id


async def get_current_user_optional(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> User | None:
    token = request.cookies.get(settings.session_cookie)
    user_id = decode_session_token(token, settings) if token else None
    if not user_id:
        return None
    user = await session.get(User, user_id)
    return user if user is not None and user.is_active else None
