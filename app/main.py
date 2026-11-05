from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings, get_settings
from app.db import create_engine
from app.routers import auth


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Parecut", version="0.1.0")
    app.state.settings = settings
    settings.storage_dir.mkdir(parents=True, exist_ok=True)

    engine = create_engine(settings)
    app.state.engine = engine
    app.state.sessionmaker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)

    return app
