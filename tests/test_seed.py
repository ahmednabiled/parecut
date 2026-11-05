from decimal import Decimal

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from app.config import Settings
from app.db import create_db_and_tables
from app.main import create_app
from app.models import CreditLedger, Job, JobArtifact
from app.seed import reconcile_orphan_jobs


async def test_seed_is_idempotent_and_logs_in(tmp_path):
    settings = Settings(
        app_env="test",
        secret_key="test-secret-key-with-at-least-32-bytes",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}",
        storage_dir=tmp_path / "storage",
        mock_stage_delay_ms=0,
        seed_demo=True,
    )
    app = create_app(settings)
    await create_db_and_tables(app.state.engine)
    async with LifespanManager(app):
        pass
    async with LifespanManager(app):  # second startup
        pass

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        login = await client.post(
            "/api/auth/login", json={"email": "demo@parecut.app", "password": "parecut-demo"}
        )
        assert login.status_code == 200
        profile = (await client.get("/api/profile")).json()
        assert len(profile["jobs"]) == 1
        assert profile["jobs"][0]["status"] == "completed"
        assert profile["jobs"][0]["artifacts"]

    async with app.state.sessionmaker() as session:
        assert len((await session.exec(select(Job))).all()) == 1
        assert len((await session.exec(select(JobArtifact))).all()) >= 9


async def test_reconcile_marks_running_job_failed_and_refunds(tmp_path):
    settings = Settings(
        app_env="test",
        secret_key="test-secret-key-with-at-least-32-bytes",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}",
        storage_dir=tmp_path / "storage",
        seed_demo=False,
    )
    app = create_app(settings)
    await create_db_and_tables(app.state.engine)
    async with app.state.sessionmaker() as session:
        from app.models import User, UserProfile

        user = User(email="a@example.com", hashed_password="x", full_name="A")
        session.add(user)
        await session.flush()
        session.add(UserProfile(user_id=user.id, credit_balance_minutes=Decimal("10")))
        job = Job(
            user_id=user.id,
            status="running",
            source_filename="x.wav",
            source_r2_key="uploads/x.wav",
            duration_seconds=120.0,
            fps="25",
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    await reconcile_orphan_jobs(app.state.sessionmaker, settings)

    async with app.state.sessionmaker() as session:
        job = await session.get(Job, job_id)
        from app.models import UserProfile

        profile = (await session.exec(select(UserProfile))).one()
        refund = (
            await session.exec(select(CreditLedger).where(CreditLedger.reason == "job_refund"))
        ).one()
        assert job.status == "failed"
        assert job.error_code == "server_restart"
        assert refund.delta_minutes == Decimal("2")
        assert profile.credit_balance_minutes == Decimal("12")
