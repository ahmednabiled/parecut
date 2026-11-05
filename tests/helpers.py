import io
import math
import wave
from array import array


async def register(client, email: str = "a@example.com", password: str = "password123") -> None:
    response = await client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "full_name": "A"},
    )
    assert response.status_code == 201, response.text


async def upload(client, data: bytes, filename: str = "clip.wav") -> str:
    response = await client.post(
        "/api/uploads",
        json={
            "filename": filename,
            "size_bytes": len(data),
            "content_type": "audio/wav",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    put = await client.put(body["upload_url"], content=data)
    assert put.status_code == 204, put.text
    return body["upload_key"]


def make_wav(seconds: float = 2, rate: int = 48000, channels: int = 1) -> bytes:
    frames = int(seconds * rate)
    samples = array(
        "h",
        (int(1000 * math.sin(2 * math.pi * 220 * i / rate)) for i in range(frames)),
    )
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(samples.tobytes())
    return buffer.getvalue()
