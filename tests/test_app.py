from pathlib import Path

import pytest

from app import BlacklistEntry, create_app, db


@pytest.fixture
def client():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "JWT_SECRET_KEY": "test-secret-key-with-at-least-32-bytes",
            "AUTH_USERNAME": "tester",
            "AUTH_PASSWORD": "test-password",
        }
    )
    with app.test_client() as test_client:
        yield test_client
    with app.app_context():
        db.drop_all()


@pytest.fixture
def auth_headers(client):
    response = client.post(
        "/auth/token", json={"username": "tester", "password": "test-password"}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json['access_token']}"}


def test_token_requires_valid_credentials(client):
    response = client.post("/auth/token", json={"username": "tester", "password": "wrong"})
    assert response.status_code == 401


def test_blacklist_requires_jwt(client):
    response = client.get("/blacklists/person@example.com")
    assert response.status_code == 401


def test_create_and_lookup_blacklist_entry(client, auth_headers):
    response = client.post(
        "/blacklists",
        headers=auth_headers,
        json={
            "email": "Person@Example.com",
            "app_uuid": "123e4567-e89b-12d3-a456-426614174000",
            "blocked_reason": "Chargeback",
        },
    )
    assert response.status_code == 201
    assert response.json["email"] == "person@example.com"

    lookup = client.get("/blacklists/PERSON@example.com", headers=auth_headers)
    assert lookup.status_code == 200
    assert lookup.json == {
        "email": "person@example.com",
        "blacklisted": True,
        "blocked_reason": "Chargeback",
    }

    with client.application.app_context():
        entry = db.session.execute(db.select(BlacklistEntry)).scalar_one()
        assert entry.source_ip
        assert entry.created_at is not None


def test_duplicate_email_is_case_insensitive_conflict(client, auth_headers):
    payload = {
        "email": "person@example.com",
        "app_uuid": "123e4567-e89b-12d3-a456-426614174000",
    }
    assert client.post("/blacklists", headers=auth_headers, json=payload).status_code == 201
    payload["email"] = "PERSON@EXAMPLE.COM"
    assert client.post("/blacklists", headers=auth_headers, json=payload).status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "app_uuid": "123e4567-e89b-12d3-a456-426614174000"},
        {"email": "person@example.com", "app_uuid": "not-a-uuid"},
        {
            "email": "person@example.com",
            "app_uuid": "123e4567-e89b-12d3-a456-426614174000",
            "blocked_reason": "x" * 256,
        },
    ],
)
def test_invalid_payload_returns_bad_request(client, auth_headers, payload):
    response = client.post("/blacklists", headers=auth_headers, json=payload)
    assert response.status_code == 400


def test_lookup_of_unlisted_email_returns_false(client, auth_headers):
    response = client.get("/blacklists/missing@example.com", headers=auth_headers)
    assert response.status_code == 200
    assert response.json["blacklisted"] is False
    assert response.json["blocked_reason"] is None


def test_version_header_is_present_on_health_and_authenticated_response(client, auth_headers):
    expected_version = Path(__file__).parents[1].joinpath("VERSION").read_text(encoding="utf-8").strip()
    health = client.get("/health")
    lookup = client.get("/blacklists/missing@example.com", headers=auth_headers)
    assert health.status_code == 200
    assert health.headers["X-App-Version"] == expected_version
    assert lookup.headers["X-App-Version"] == expected_version


def test_authentication_errors_are_401_in_production_mode():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite://"})
    client = app.test_client()
    assert client.get("/blacklists/person@example.com").status_code == 401
    assert client.get(
        "/blacklists/person@example.com", headers={"Authorization": "Bearer invalid"}
    ).status_code == 422
