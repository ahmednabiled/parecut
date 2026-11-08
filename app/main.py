from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings, get_settings
from app.db import create_engine
from app.events import InMemoryEventBroker
from app.routers import auth, jobs, profile, uploads
from app.seed import reconcile_orphan_jobs, seed_demo
from app.services.pipeline import MockPipelineRunner
from app.services.runpod import HttpRunpodClient, RunpodPipelineRunner
from app.storage import LocalObjectStorage, R2ObjectStorage


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.seed_demo:
            await seed_demo(app.state.sessionmaker, app.state.storage, settings)
        await reconcile_orphan_jobs(app.state.sessionmaker, settings)
        try:
            yield
        finally:
            runpod_client = getattr(app.state, "runpod_client", None)
            if runpod_client is not None:
                await runpod_client.aclose()

    app = FastAPI(title="Parecut", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    settings.storage_dir.mkdir(parents=True, exist_ok=True)

    engine = create_engine(settings)
    app.state.engine = engine
    app.state.sessionmaker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    if settings.storage_backend == "r2":
        app.state.storage = R2ObjectStorage(
            bucket=settings.r2_bucket or "",
            endpoint_url=settings.r2_endpoint_url or "",
            access_key_id=settings.r2_access_key_id or "",
            secret_access_key=settings.r2_secret_access_key or "",
            region=settings.r2_region,
        )
    else:
        app.state.storage = LocalObjectStorage(settings.storage_dir, settings.secret_key)
    app.state.broker = InMemoryEventBroker()
    if settings.pipeline_runner == "runpod":
        runpod_client = HttpRunpodClient(
            api_key=settings.runpod_api_key or "",
            base_url=settings.runpod_api_base_url,
            timeout=settings.runpod_request_timeout_seconds,
        )
        app.state.runpod_client = runpod_client
        app.state.runner = RunpodPipelineRunner(
            app.state.sessionmaker,
            app.state.storage,
            app.state.broker,
            settings,
            runpod_client,
        )
    else:
        app.state.runner = MockPipelineRunner(
            app.state.sessionmaker,
            app.state.storage,
            app.state.broker,
            settings,
        )

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(profile.router)
    app.include_router(uploads.router)
    app.include_router(jobs.router)

    return app


app = create_app()
