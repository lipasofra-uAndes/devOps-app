"""Endpoint contracts with mocked persistence: no database connection or AWS."""

from datetime import timedelta
from secrets import token_hex
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask_jwt_extended import create_access_token, decode_token
from sqlalchemy.exc import IntegrityError

import app as app_module


@pytest.fixture
def unit_client(monkeypatch):
    monkeypatch.setattr(app_module, "create_schema", MagicMock())
    application = app_module.create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "JWT_SECRET_KEY": token_hex(32),
        "AUTH_USERNAME": "unit-user",
        "AUTH_PASSWORD": token_hex(16),
    })
    session = MagicMock()
    monkeypatch.setattr(app_module.db, "session", session)
    with application.test_client() as client:
        yield client, session


@pytest.fixture
def unit_auth(unit_client):
    client, _ = unit_client
    with client.application.app_context():
        token = create_access_token(identity="unit-user")
    return {"Authorization": f"Bearer {token}"}


def payload(**changes):
    return {
        "email": "Person@Example.com",
        "app_uuid": "123e4567-e89b-12d3-a456-426614174000",
        "blocked_reason": "Chargeback",
        **changes,
    }


def test_token_issues_valid_signed_jwt(unit_client):
    client, session = unit_client
    response = client.post("/auth/token", json={
        "username": "unit-user",
        "password": client.application.config["AUTH_PASSWORD"],
    })
    assert response.status_code == 200
    with client.application.app_context():
        assert decode_token(response.json["access_token"])["sub"] == "unit-user"
    session.execute.assert_not_called()


@pytest.mark.parametrize("field", ["username", "password"])
def test_token_rejects_each_incorrect_credential(unit_client, field):
    client, _ = unit_client
    credentials = {"username": "unit-user", "password": client.application.config["AUTH_PASSWORD"]}
    credentials[field] = "incorrect"
    response = client.post("/auth/token", json=credentials)
    assert response.status_code == 401
    assert "access_token" not in response.json


@pytest.mark.parametrize("body", [None, [], "text", {}, {"username": "unit-user"}, {"username": 1, "password": 2}])
def test_token_rejects_invalid_body(unit_client, body):
    client, _ = unit_client
    assert client.post("/auth/token", json=body).status_code == 400


def test_health_executes_probe(unit_client):
    client, session = unit_client
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}
    assert str(session.execute.call_args.args[0]) == "SELECT 1"


def test_health_reports_database_failure(unit_client):
    client, session = unit_client
    session.execute.side_effect = RuntimeError("simulated database outage")
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json == {"status": "unhealthy"}


@pytest.mark.parametrize("reason", [None, "", "x" * 255])
def test_create_persists_normalized_fields_and_source_ip(unit_client, unit_auth, reason):
    client, session = unit_client
    response = client.post("/blacklists", headers=unit_auth, json=payload(blocked_reason=reason),
                           environ_overrides={"REMOTE_ADDR": "192.0.2.10"})
    assert response.status_code == 201
    assert response.json == {"message": "Email added to the blacklist.", "email": "person@example.com"}
    entry = session.add.call_args.args[0]
    assert entry.email == "person@example.com"
    assert entry.app_uuid == "123e4567-e89b-12d3-a456-426614174000"
    assert entry.blocked_reason == reason
    assert entry.source_ip == "192.0.2.10"
    session.commit.assert_called_once_with()
    session.rollback.assert_not_called()


def test_create_accepts_omitted_optional_reason(unit_client, unit_auth):
    client, session = unit_client
    body = payload()
    del body["blocked_reason"]
    assert client.post("/blacklists", headers=unit_auth, json=body).status_code == 201
    assert session.add.call_args.args[0].blocked_reason is None


@pytest.mark.parametrize("body", [None, [], "text", {},
    {"email": "person@example.com"}, {"app_uuid": "123e4567-e89b-12d3-a456-426614174000"},
    payload(email="invalid"), payload(app_uuid="invalid"), payload(blocked_reason="x" * 256)])
def test_create_rejects_invalid_input_without_writing(unit_client, unit_auth, body):
    client, session = unit_client
    assert client.post("/blacklists", headers=unit_auth, json=body).status_code == 400
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_create_rolls_back_unique_conflict(unit_client, unit_auth):
    client, session = unit_client
    session.commit.side_effect = IntegrityError("INSERT", {}, Exception("duplicate"))
    response = client.post("/blacklists", headers=unit_auth, json=payload())
    assert response.status_code == 409
    assert response.json == {"message": "This email already belongs to the blacklist."}
    session.rollback.assert_called_once_with()


@pytest.mark.parametrize("entry", [None, SimpleNamespace(blocked_reason="Chargeback"), SimpleNamespace(blocked_reason=None)])
def test_lookup_contract_and_normalized_query(unit_client, unit_auth, entry):
    client, session = unit_client
    session.execute.return_value.scalar_one_or_none.return_value = entry
    response = client.get("/blacklists/PERSON@EXAMPLE.COM", headers=unit_auth)
    assert response.status_code == 200
    assert response.json == {"email": "person@example.com", "blacklisted": entry is not None,
                             "blocked_reason": entry.blocked_reason if entry else None}
    statement = session.execute.call_args.args[0]
    assert list(statement.compile().params.values()) == ["person@example.com"]
    session.commit.assert_not_called()


@pytest.mark.parametrize("method,path", [("POST", "/blacklists"), ("GET", "/blacklists/person@example.com")])
@pytest.mark.parametrize("token_state,status", [("missing", 401), ("malformed", 422), ("expired", 401)])
def test_protected_endpoints_reject_invalid_tokens_before_persistence(unit_client, method, path, token_state, status):
    client, session = unit_client
    headers = {}
    if token_state == "malformed":
        headers["Authorization"] = "Bearer invalid"
    elif token_state == "expired":
        with client.application.app_context():
            token = create_access_token(identity="unit-user", expires_delta=timedelta(seconds=-1))
        headers["Authorization"] = f"Bearer {token}"
    assert client.open(path, method=method, headers=headers, json=payload()).status_code == status
    session.execute.assert_not_called()
    session.add.assert_not_called()
    session.commit.assert_not_called()
