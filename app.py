import hmac
import os
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, request
from flask_jwt_extended import JWTManager, create_access_token, jwt_required
from flask_jwt_extended.exceptions import JWTExtendedException
from flask_marshmallow import Marshmallow
from flask_restful import Api, Resource
from flask_sqlalchemy import SQLAlchemy
from marshmallow import ValidationError, fields, validate
from jwt.exceptions import PyJWTError
from sqlalchemy.exc import IntegrityError
from werkzeug.middleware.proxy_fix import ProxyFix


db = SQLAlchemy()
ma = Marshmallow()
jwt = JWTManager()


class AuthAwareApi(Api):
    def error_router(self, original_handler, error):
        if isinstance(error, (JWTExtendedException, PyJWTError)):
            return original_handler(error)
        return super().error_router(original_handler, error)


class BlacklistEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(320), unique=True, nullable=False, index=True)
    app_uuid = db.Column(db.String(36), nullable=False)
    blocked_reason = db.Column(db.String(255), nullable=True)
    source_ip = db.Column(db.String(45), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class BlacklistCreateSchema(ma.Schema):
    email = fields.Email(required=True, validate=validate.Length(max=320))
    app_uuid = fields.UUID(required=True)
    blocked_reason = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=255)
    )


class TokenSchema(ma.Schema):
    username = fields.String(required=True)
    password = fields.String(required=True)


def create_app(test_config=None):
    app = Flask(__name__)
    # VERSION travels inside each source bundle, so old and new instances are distinguishable.
    app_version = (Path(__file__).with_name("VERSION").read_text(encoding="utf-8").strip())
    database_url = os.getenv("DATABASE_URL", "sqlite:///blacklist.db")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
        JWT_SECRET_KEY=os.getenv(
            "JWT_SECRET_KEY", "dev-only-change-me-use-a-real-secret-in-deployment"
        ),
        AUTH_USERNAME=os.getenv("AUTH_USERNAME", "dev-user"),
        AUTH_PASSWORD=os.getenv("AUTH_PASSWORD", "dev-password"),
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    ma.init_app(app)
    jwt.init_app(app)
    api = AuthAwareApi(app)

    # Elastic Beanstalk's load balancer is the single trusted proxy in front of the app.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    @app.after_request
    def add_deployment_version(response):
        response.headers["X-App-Version"] = app_version
        return response

    @app.get("/health")
    def health():
        try:
            db.session.execute(db.text("SELECT 1"))
        except Exception:
            return {"status": "unhealthy"}, 503
        return {"status": "ok"}, 200

    class TokenResource(Resource):
        def post(self):
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict):
                return {"message": "Request body must be a JSON object."}, 400
            try:
                credentials = TokenSchema().load(payload)
            except ValidationError as error:
                return {"message": "Invalid credentials format.", "errors": error.messages}, 400

            valid_user = hmac.compare_digest(credentials["username"], app.config["AUTH_USERNAME"])
            valid_password = hmac.compare_digest(credentials["password"], app.config["AUTH_PASSWORD"])
            if not (valid_user and valid_password):
                return {"message": "Invalid username or password."}, 401

            return {"access_token": create_access_token(identity=credentials["username"])}, 200

    class BlacklistResource(Resource):
        @jwt_required()
        def post(self):
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict):
                return {"message": "Request body must be a JSON object."}, 400
            try:
                values = BlacklistCreateSchema().load(payload)
            except ValidationError as error:
                return {"message": "Invalid request.", "errors": error.messages}, 400

            email = values["email"].strip().casefold()
            entry = BlacklistEntry(
                email=email,
                app_uuid=str(values["app_uuid"]),
                blocked_reason=values.get("blocked_reason"),
                source_ip=request.remote_addr or "0.0.0.0",
            )
            db.session.add(entry)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                return {"message": "This email already belongs to the blacklist."}, 409

            return {"message": "Email added to the blacklist.", "email": email}, 201

    class BlacklistLookupResource(Resource):
        @jwt_required()
        def get(self, email):
            normalized_email = email.strip().casefold()
            entry = db.session.execute(
                db.select(BlacklistEntry).where(BlacklistEntry.email == normalized_email)
            ).scalar_one_or_none()
            return {
                "email": normalized_email,
                "blacklisted": entry is not None,
                "blocked_reason": entry.blocked_reason if entry else None,
            }, 200

    api.add_resource(TokenResource, "/auth/token")
    api.add_resource(BlacklistResource, "/blacklists")
    api.add_resource(BlacklistLookupResource, "/blacklists/<string:email>")

    with app.app_context():
        create_schema()

    return app


# Arbitrary application-wide key for the PostgreSQL advisory lock that guards schema creation.
SCHEMA_LOCK_KEY = 4815162342


def create_schema():
    # Elastic Beanstalk starts several instances at once; without the lock, two of them can race
    # on CREATE TABLE against an empty RDS database and one fails to boot.
    with db.engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(db.text("SELECT pg_advisory_xact_lock(:key)"), {"key": SCHEMA_LOCK_KEY})
        db.metadata.create_all(connection)
