from app.security import (
    create_session_token,
    decode_session_token,
    hash_password,
    verify_password,
)


def test_password_hash_round_trip(settings):
    hashed = hash_password("correct horse")
    assert hashed != "correct horse"
    assert verify_password("correct horse", hashed)
    assert not verify_password("wrong", hashed)


def test_session_token_round_trip(settings):
    token = create_session_token("user-123", settings)
    assert decode_session_token(token, settings) == "user-123"


def test_expired_token_is_rejected(settings):
    settings.session_ttl_days = -1
    token = create_session_token("user-123", settings)
    assert decode_session_token(token, settings) is None


def test_tampered_token_is_rejected(settings):
    token = create_session_token("user-123", settings)
    assert decode_session_token(token + "x", settings) is None
