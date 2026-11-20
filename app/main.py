import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings, get_settings
from app.db import create_engine
from app.events import InMemoryEventBroker
from app.routers import auth, jobs, profile, uploads
from app.seed import reconcile_orphan_jobs, seed_demo
from app.services.cleanup import periodic_cleanup
from app.services.pipeline import MockPipelineRunner
from app.services.runpod import HttpRunpodClient, RunpodPipelineRunner
from app.storage import LocalObjectStorage, R2ObjectStorage


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.validate_runtime()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.seed_demo:
            await seed_demo(app.state.sessionmaker, app.state.storage, settings)
        await reconcile_orphan_jobs(
            app.state.sessionmaker, settings, runner=app.state.runner
        )
        cleanup_task: asyncio.Task | None = None
        if (
            settings.app_env != "test"
            and settings.orphan_upload_cleanup_interval_seconds > 0
        ):
            cleanup_task = asyncio.create_task(
                periodic_cleanup(
                    app.state.sessionmaker,
                    app.state.storage,
                    ttl_seconds=settings.orphan_upload_ttl_seconds,
                    interval_seconds=settings.orphan_upload_cleanup_interval_seconds,
                )
            )
        try:
            yield
        finally:
            if cleanup_task is not None:
                cleanup_task.cancel()
                try:
                    await cleanup_task
                except asyncio.CancelledError:
                    pass
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
            secret_key=settings.secret_key,
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

    @app.get("/api/ready")
    async def ready() -> dict[str, str]:
        async with app.state.sessionmaker() as session:
            await session.exec(text("SELECT 1"))
        return {"status": "ready"}

    app.include_router(auth.router)
    app.include_router(profile.router)
    app.include_router(uploads.router)
    app.include_router(jobs.router)

    dist = settings.frontend_dist
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa_fallback(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")

        root = dist.resolve()
        if path:
            candidate = (root / path).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                candidate = None
            if candidate is not None and candidate.is_file():
                return FileResponse(candidate)

        index = dist / "index.html"
        if index.is_file():
            return FileResponse(index)
        return PlainTextResponse(
            "Frontend build not found. Run `npm run build` in web/.",
            status_code=404,
        )

    return app


app = create_app()
