import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.db import create_db_and_tables
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(
        app_env="test",
        secret_key="test-secret-key-with-at-least-32-bytes",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        storage_dir=tmp_path / "storage",
        mock_stage_delay_ms=0,
        seed_demo=False,
    )


@pytest.fixture
async def app(settings):
    application = create_app(settings)
    await create_db_and_tables(application.state.engine)
    yield application


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
