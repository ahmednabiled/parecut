import io

import pytest
from botocore.exceptions import ClientError

from app.config import Settings
from app.main import create_app
from app.storage import InvalidToken, R2ObjectStorage


class FakeS3:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.objects: dict[str, bytes] = {}

    def put_object(self, **kwargs):
        self.calls.append(("put_object", kwargs))
        self.objects[kwargs["Key"]] = kwargs["Body"]
        return {}

    def get_object(self, **kwargs):
        self.calls.append(("get_object", kwargs))
        try:
            body = self.objects[kwargs["Key"]]
        except KeyError as exc:
            raise ClientError({"Error": {"Code": "404"}}, "GetObject") from exc
        return {"Body": io.BytesIO(body)}

    def copy_object(self, **kwargs):
        self.calls.append(("copy_object", kwargs))
        src = kwargs["CopySource"]
        self.objects[kwargs["Key"]] = self.objects[src["Key"]]
        return {}

    def delete_object(self, **kwargs):
        self.calls.append(("delete_object", kwargs))
        self.objects.pop(kwargs["Key"], None)
        return {}

    def head_object(self, **kwargs):
        self.calls.append(("head_object", kwargs))
        try:
            body = self.objects[kwargs["Key"]]
        except KeyError as exc:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject") from exc
        return {"ContentLength": len(body)}


def make_storage(client: FakeS3 | None = None) -> R2ObjectStorage:
    return R2ObjectStorage(
        bucket="parecut",
        endpoint_url="https://account.r2.cloudflarestorage.com",
        access_key_id="key",
        secret_access_key="secret",
        secret_key="test-secret-key",
        client=client or FakeS3(),
    )


async def test_r2_put_get_copy_delete_and_size():
    storage = make_storage()

    await storage.put("jobs/1/a.wav", b"hello", "audio/wav")
    assert await storage.get("jobs/1/a.wav") == b"hello"
    assert await storage.exists("jobs/1/a.wav") is True
    assert await storage.size("jobs/1/a.wav") == 5

    await storage.copy("jobs/1/a.wav", "jobs/1/b.wav")
    assert await storage.get("jobs/1/b.wav") == b"hello"

    await storage.delete("jobs/1/a.wav")
    assert await storage.exists("jobs/1/a.wav") is False


async def test_r2_exists_returns_false_for_missing_object():
    assert await make_storage().exists("jobs/1/missing.wav") is False


async def test_r2_exists_reraises_unexpected_client_errors():
    class BrokenS3(FakeS3):
        def head_object(self, **kwargs):
            raise ClientError({"Error": {"Code": "403"}}, "HeadObject")

    with pytest.raises(ClientError):
        await make_storage(BrokenS3()).exists("jobs/1/a.wav")


def test_r2_browser_upload_is_proxied_and_worker_upload_is_presigned():
    storage = R2ObjectStorage(
        bucket="parecut",
        endpoint_url="https://account.r2.cloudflarestorage.com",
        access_key_id="key",
        secret_access_key="secret",
        secret_key="test-secret-key",
    )

    upload = storage.signed_upload_url("jobs/1/a.wav", 900)
    worker_upload = storage.signed_direct_upload_url("jobs/1/b.wav", 900)
    download = storage.signed_download_url("jobs/1/a.wav", "a.wav", 900)

    assert upload.startswith("/api/uploads/")
    token = upload.rsplit("/", 1)[-1]
    assert storage.verify_upload_token(token) == "jobs/1/a.wav"
    assert "https://account.r2.cloudflarestorage.com/parecut/jobs/1/b.wav" in worker_upload
    assert "X-Amz-Signature=" in worker_upload
    assert "https://account.r2.cloudflarestorage.com/parecut/jobs/1/a.wav" in download
    assert "X-Amz-Signature=" in download
    assert "response-content-disposition" in download


def test_r2_rejects_tampered_upload_tokens():
    storage = make_storage()

    with pytest.raises(InvalidToken):
        storage.verify_upload_token("not-a-token")


def test_r2_storage_is_selected_by_settings(tmp_path):
    settings = Settings(
        app_env="test",
        secret_key="test-secret-key-with-at-least-32-bytes",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        storage_dir=tmp_path / "storage",
        storage_backend="r2",
        pipeline_runner="mock",
        r2_account_id="account",
        r2_access_key_id="key",
        r2_secret_access_key="secret",
        r2_bucket="parecut",
        r2_endpoint_url="https://account.r2.cloudflarestorage.com",
        seed_demo=False,
    )

    app = create_app(settings)

    assert isinstance(app.state.storage, R2ObjectStorage)
