from __future__ import annotations

from pydantic import SecretStr
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.controller.auth_controller import require_internal_token
from app.config import settings
from app.db import Base, EmailToken, RefreshSession, User, get_db
from app.main import app
from app.service import avatar_storage_service as avatar_storage
from app.service import mail_service as mailer
from app.service.auth_security_service import hash_token


def _register(client: TestClient, email: str = "Person@Example.COM"):
    return client.post(
        "/internal/v1/auth/register",
        json={"email": email, "display_name": "Test Person", "password": "correct-horse-battery"},
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _activate_and_login(client: TestClient, db_factory, email: str = "person@example.com"):
    with db_factory() as db:
        user = db.scalar(select(User).where(User.email == email.lower()))
        user.email_verified = True
        db.commit()
    response = client.post(
        "/internal/v1/auth/login",
        json={"email": email, "password": "correct-horse-battery"},
    )
    assert response.status_code == 200
    return response.json()


def test_register_login_me_and_duplicate(client, db_factory):
    response = _register(client)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "person@example.com"
    assert body["requires_email_verification"] is True

    pending_login = client.post(
        "/internal/v1/auth/login",
        json={"email": "PERSON@example.com", "password": "correct-horse-battery"},
    )
    assert pending_login.json()["requires_email_verification"] is True
    tokens = _activate_and_login(client, db_factory)
    me = client.get("/internal/v1/auth/me", headers=_auth(tokens["access_token"]))
    assert me.status_code == 200
    assert me.json()["display_name"] == "Test Person"
    assert _register(client).status_code == 409

    login = client.post(
        "/internal/v1/auth/login",
        json={"email": "PERSON@example.com", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200
    assert client.post(
        "/internal/v1/auth/login",
        json={"email": "person@example.com", "password": "wrong"},
    ).status_code == 401


def test_refresh_rotates_and_logout_revokes(client, db_factory):
    _register(client)
    original = _activate_and_login(client, db_factory)["refresh_token"]
    rotated = client.post("/internal/v1/auth/refresh", json={"refresh_token": original})
    assert rotated.status_code == 200
    replacement = rotated.json()["refresh_token"]
    assert replacement != original
    assert client.post(
        "/internal/v1/auth/refresh", json={"refresh_token": original}
    ).status_code == 401
    assert client.post(
        "/internal/v1/auth/logout", json={"refresh_token": replacement}
    ).status_code == 200
    assert client.post(
        "/internal/v1/auth/refresh", json={"refresh_token": replacement}
    ).status_code == 401


def test_email_verification_and_password_reset(client, monkeypatch):
    sent: dict[str, str] = {}
    monkeypatch.setattr(
        mailer,
        "send_verification_email",
        lambda _email, _name, token: sent.update(verification=token),
    )
    monkeypatch.setattr(
        mailer,
        "send_reset_email",
        lambda _email, _name, token: sent.update(reset=token),
    )
    registered = _register(client).json()
    assert registered["requires_email_verification"] is True
    assert sent["verification"].isdigit() and len(sent["verification"]) == 6
    verify = client.post(
        "/internal/v1/auth/verify-email",
        json={"email": "person@example.com", "code": sent["verification"]},
    )
    assert verify.status_code == 200
    assert client.get(
        "/internal/v1/auth/me", headers=_auth(verify.json()["access_token"])
    ).json()["email_verified"] is True
    assert client.post(
        "/internal/v1/auth/verify-email",
        json={"email": "person@example.com", "code": sent["verification"]},
    ).status_code == 400

    forgot = client.post(
        "/internal/v1/auth/forgot-password", json={"email": "person@example.com"}
    )
    assert forgot.status_code == 200
    assert sent["reset"].isdigit() and len(sent["reset"]) == 6
    reset = client.post(
        "/internal/v1/auth/reset-password",
        json={
            "email": "person@example.com",
            "code": sent["reset"],
            "password": "a-brand-new-secure-password",
        },
    )
    assert reset.status_code == 200
    assert client.post(
        "/internal/v1/auth/refresh",
        json={"refresh_token": verify.json()["refresh_token"]},
    ).status_code == 401
    assert client.post(
        "/internal/v1/auth/login",
        json={"email": "person@example.com", "password": "a-brand-new-secure-password"},
    ).status_code == 200


def test_profile_and_avatar_updates(client, db_factory):
    _register(client)
    token = _activate_and_login(client, db_factory)["access_token"]
    profile = client.patch(
        "/internal/v1/auth/profile",
        headers=_auth(token),
        json={"display_name": "Updated Name"},
    )
    assert profile.status_code == 200
    avatar = client.patch(
        "/internal/v1/auth/avatar",
        headers=_auth(token),
        json={"avatar_key": "avatars/user.webp", "avatar_url": "https://cdn.example.com/user.webp"},
    )
    assert avatar.status_code == 200
    assert avatar.json()["avatar_key"] == "avatars/user.webp"


def test_avatar_upload_and_delete(client, db_factory, monkeypatch):
    _register(client)
    token = _activate_and_login(client, db_factory)["access_token"]

    async def fake_upload(user_id, file):
        assert user_id
        assert file.content_type == "image/png"
        return f"avatars/{user_id}/avatar.png", "https://cdn.example/avatar.png"

    monkeypatch.setattr(avatar_storage, "put_upload", fake_upload)
    monkeypatch.setattr(avatar_storage, "delete", lambda _key: None)
    uploaded = client.post(
        "/internal/v1/auth/profile/avatar",
        headers=_auth(token),
        files={"file": ("avatar.png", b"png", "image/png")},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["avatar_url"] == "https://cdn.example/avatar.png"
    removed = client.delete(
        "/internal/v1/auth/profile/avatar",
        headers=_auth(token),
    )
    assert removed.status_code == 200
    assert removed.json()["avatar_url"] is None


def test_admin_promotion_and_introspection(client, db_factory, monkeypatch):
    _register(client, "admin@example.com")
    _register(client, "target@example.com")
    with db_factory() as db:
        admin = db.scalar(select(User).where(User.email == "admin@example.com"))
        admin.role = "ADMIN"
        admin.email_verified = True
        db.commit()
    admin_tokens = client.post(
        "/internal/v1/auth/login",
        json={"email": "admin@example.com", "password": "correct-horse-battery"},
    ).json()
    monkeypatch.setattr(settings, "internal_service_token", SecretStr("service-secret"))
    headers = {**_auth(admin_tokens["access_token"]), "X-Internal-Service-Token": "service-secret"}
    promoted = client.post(
        "/internal/v1/auth/admin/promote",
        headers=headers,
        json={"email": "target@example.com", "reason": "operations owner"},
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "ADMIN"
    introspection = client.get("/internal/v1/auth/authorize/admin", headers=headers)
    assert introspection.status_code == 200
    assert introspection.json()["admin"] is True
    assert client.get(
        "/internal/v1/auth/authorize/admin",
        headers=_auth(admin_tokens["access_token"]),
    ).status_code == 401


def test_google_start_is_disabled_without_configuration(client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "")
    assert client.get("/internal/v1/auth/google/start").status_code == 503


import pytest


@pytest.fixture
def db_factory():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    yield factory
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def client(db_factory, monkeypatch):
    monkeypatch.setattr(mailer, "send_verification_email", lambda *_args: None)
    monkeypatch.setattr(mailer, "send_reset_email", lambda *_args: None)
    return TestClient(app)
