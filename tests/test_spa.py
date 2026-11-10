from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app


def _settings(tmp_path, dist):
    return Settings(
        app_env="test",
        secret_key="test-secret-key-with-at-least-32-bytes",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}",
        storage_dir=tmp_path / "storage",
        storage_backend="local",
        pipeline_runner="mock",
        frontend_dist=dist,
        seed_demo=False,
    )


async def test_spa_fallback_serves_index_and_static_assets(tmp_path):
    dist = tmp_path / "dist"
    assets = dist / "assets"
    brand = dist / "brand"
    assets.mkdir(parents=True)
    brand.mkdir()
    (dist / "index.html").write_text("<html><body>parecut-shell</body></html>")
    (assets / "app.js").write_text("console.log('ok')")
    (brand / "logo.png").write_bytes(b"PNG")

    app = create_app(_settings(tmp_path, dist))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        deep_link = await client.get("/jobs/abc")
        assert deep_link.status_code == 200
        assert "parecut-shell" in deep_link.text

        asset = await client.get("/assets/app.js")
        assert asset.status_code == 200
        assert "console.log" in asset.text

        brand_asset = await client.get("/brand/logo.png")
        assert brand_asset.status_code == 200
        assert brand_asset.content == b"PNG"

        missing_api = await client.get("/api/does-not-exist")
        assert missing_api.status_code == 404


async def test_missing_frontend_build_returns_a_hint(tmp_path):
    app = create_app(_settings(tmp_path, tmp_path / "missing-dist"))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/api/health")).status_code == 200
        response = await client.get("/jobs/abc")
        assert response.status_code == 404
        assert "npm run build" in response.text
