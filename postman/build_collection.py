"""Build the importable Postman collection and safe example environment."""

import json
from pathlib import Path


HERE = Path(__file__).parent
UUID = "123e4567-e89b-12d3-a456-426614174000"
AWS_BASE_URL = "http://devops-blacklist-api-dev.eba-2zph7mid.us-east-1.elasticbeanstalk.com"
LOCAL_BASE_URL = "http://127.0.0.1:5000"


def item(name, method, path, description, tests, body=None, no_auth=False, pre=None, examples=None):
    request = {
        "method": method,
        "header": [{"key": "Content-Type", "value": "application/json"}] if body else [],
        "url": "{{base_url}}" + path,
        "description": description,
    }
    if body:
        request["body"] = {"mode": "raw", "raw": json.dumps(body, ensure_ascii=False, indent=2), "options": {"raw": {"language": "json"}}}
    if no_auth:
        request["auth"] = {"type": "noauth"}
    events = []
    if pre:
        events.append({"listen": "prerequest", "script": {"type": "text/javascript", "exec": pre}})
    events.append({"listen": "test", "script": {"type": "text/javascript", "exec": tests}})
    result = {"name": name, "request": request, "event": events}
    if examples:
        result["response"] = examples
    return result


def example(name, code, method, path, body, request_body=None):
    original_request = {"method": method, "header": [], "url": "{{base_url}}" + path}
    if request_body is not None:
        original_request["header"] = [{"key": "Content-Type", "value": "application/json"}]
        original_request["body"] = {"mode": "raw", "raw": json.dumps(request_body, ensure_ascii=False, indent=2), "options": {"raw": {"language": "json"}}}
    return {
        "name": name,
        "originalRequest": original_request,
        "status": {200: "OK", 201: "Created", 400: "Bad Request", 401: "Unauthorized", 409: "Conflict"}[code],
        "code": code,
        "header": [{"key": "Content-Type", "value": "application/json"}],
        "body": json.dumps(body, ensure_ascii=False, indent=2),
    }


collection = {
    "info": {
        "name": "Global Email Blacklist API - Entrega 1",
        "description": "Escenarios reproducibles para la API de lista negra. Ejecutar la colección completa en orden. base_url apunta por defecto al entorno Elastic Beanstalk (us-east-1); usar el environment local para pruebas en 127.0.0.1:5000. Configurar auth_username y auth_password en un environment. No exportar credenciales reales. El email se genera por ejecución.",
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "auth": {"type": "bearer", "bearer": [{"key": "token", "value": "{{access_token}}", "type": "string"}]},
    "variable": [{"key": "base_url", "value": AWS_BASE_URL}, {"key": "access_token", "value": ""}, {"key": "test_email", "value": ""}],
    "item": [
        item("01 Obtener JWT", "POST", "/auth/token", "Genera JWT Bearer. 200: access_token; 401: credenciales inválidas.",
             ["pm.test('JWT emitido', function () { pm.response.to.have.status(200); const data = pm.response.json(); pm.expect(data.access_token).to.be.a('string').and.not.empty; pm.collectionVariables.set('access_token', data.access_token); });"],
             body={"username": "{{auth_username}}", "password": "{{auth_password}}"}, no_auth=True,
             pre=["pm.collectionVariables.set('test_email', 'probe-' + Date.now() + '-' + Math.floor(Math.random() * 1000000) + '@example.com');", "pm.collectionVariables.unset('access_token');"],
             examples=[example("200 JWT", 200, "POST", "/auth/token", {"access_token": "<JWT>"},
                               request_body={"username": "api-client", "password": "<password>"})]),
        item("02 Health y versión", "GET", "/health", "Comprueba la base de datos (200 o 503) y la versión empaquetada en X-App-Version.",
             ["pm.test('Servicio saludable', function () { pm.response.to.have.status(200); pm.expect(pm.response.json().status).to.eql('ok'); });",
              "pm.test('Versión disponible', function () { pm.expect(pm.response.headers.get('X-App-Version')).to.be.a('string').and.not.empty; });"], no_auth=True,
             examples=[example("200 saludable", 200, "GET", "/health", {"status": "ok"})]),
        item("03 Agregar email", "POST", "/blacklists", "Registra email, UUID obligatorio y motivo opcional de máximo 255 caracteres. Requiere JWT. 201: creado; 400: inválido; 409: duplicado.",
             ["pm.test('Alta 201', function () { pm.response.to.have.status(201); pm.expect(pm.response.json().email).to.eql(pm.collectionVariables.get('test_email')); });"],
             body={"email": "{{test_email}}", "app_uuid": UUID, "blocked_reason": "Prueba Postman Entrega 1"},
             examples=[example("201 creado", 201, "POST", "/blacklists", {"message": "Email added to the blacklist.", "email": "cliente@example.com"},
                               request_body={"email": "cliente@example.com", "app_uuid": UUID, "blocked_reason": "Prueba Postman Entrega 1"})]),
        item("04 Duplicado", "POST", "/blacklists", "El mismo email registrado en 03 debe retornar 409.",
             ["pm.test('Duplicado 409', function () { pm.response.to.have.status(409); });"],
             body={"email": "{{test_email}}", "app_uuid": UUID},
             examples=[example("409 duplicado", 409, "POST", "/blacklists", {"message": "This email already belongs to the blacklist."},
                               request_body={"email": "cliente@example.com", "app_uuid": UUID})]),
        item("05 Consultar email bloqueado", "GET", "/blacklists/{{test_email}}", "Devuelve blacklisted true y el motivo cuando el email existe.",
             ["pm.test('Bloqueado y motivo', function () { pm.response.to.have.status(200); const data = pm.response.json(); pm.expect(data.blacklisted).to.eql(true); pm.expect(data.blocked_reason).to.eql('Prueba Postman Entrega 1'); });"],
             examples=[example("200 bloqueado", 200, "GET", "/blacklists/cliente@example.com", {"email": "cliente@example.com", "blacklisted": True, "blocked_reason": "Prueba Postman Entrega 1"})]),
        item("06 Consultar email no registrado", "GET", "/blacklists/no-registrado-{{test_email}}", "Devuelve blacklisted false y blocked_reason null cuando no existe.",
             ["pm.test('No bloqueado', function () { pm.response.to.have.status(200); const data = pm.response.json(); pm.expect(data.blacklisted).to.eql(false); pm.expect(data.blocked_reason).to.eql(null); });"],
             examples=[example("200 no bloqueado", 200, "GET", "/blacklists/otro@example.com", {"email": "otro@example.com", "blacklisted": False, "blocked_reason": None})]),
        item("07 Email inválido", "POST", "/blacklists", "Un email mal formado debe retornar 400.",
             ["pm.test('Email inválido 400', function () { pm.response.to.have.status(400); });"],
             body={"email": "no-es-correo", "app_uuid": UUID},
             examples=[example("400 email inválido", 400, "POST", "/blacklists",
                               {"message": "Invalid request.", "errors": {"email": ["Not a valid email address."]}},
                               request_body={"email": "no-es-correo", "app_uuid": UUID})]),
        item("08 UUID inválido", "POST", "/blacklists", "app_uuid debe tener formato UUID; un valor inválido retorna 400.",
             ["pm.test('UUID inválido 400', function () { pm.response.to.have.status(400); });"],
             body={"email": "otro-{{test_email}}", "app_uuid": "no-es-uuid"},
             examples=[example("400 UUID inválido", 400, "POST", "/blacklists",
                               {"message": "Invalid request.", "errors": {"app_uuid": ["Not a valid UUID."]}},
                               request_body={"email": "otro@example.com", "app_uuid": "no-es-uuid"})]),
        item("09 Motivo demasiado largo", "POST", "/blacklists", "blocked_reason de 256 caracteres debe retornar 400.",
             ["pm.test('Motivo largo 400', function () { pm.response.to.have.status(400); });"],
             body={"email": "otro-{{test_email}}", "app_uuid": UUID, "blocked_reason": "x" * 256},
             examples=[example("400 motivo demasiado largo", 400, "POST", "/blacklists",
                               {"message": "Invalid request.", "errors": {"blocked_reason": ["Longer than maximum length 255."]}},
                               request_body={"email": "otro@example.com", "app_uuid": UUID, "blocked_reason": "x" * 256})]),
        item("10 Sin token", "GET", "/blacklists/{{test_email}}", "Sin Bearer token debe retornar 401.",
             ["pm.test('Sin token 401', function () { pm.response.to.have.status(401); });"], no_auth=True,
             examples=[example("401 sin token", 401, "GET", "/blacklists/cliente@example.com", {"msg": "Missing Authorization Header"})]),
        item("11 Credenciales inválidas", "POST", "/auth/token", "Contraseña incorrecta debe retornar 401; conserva el token válido de la colección.",
             ["pm.test('Credenciales inválidas 401', function () { pm.response.to.have.status(401); });"],
             body={"username": "{{auth_username}}", "password": "invalid-password"}, no_auth=True,
             examples=[example("401 credenciales inválidas", 401, "POST", "/auth/token", {"message": "Invalid username or password."},
                               request_body={"username": "api-client", "password": "invalid-password"})]),
    ],
}

def environment(env_id, name, base_url):
    return {
        "id": env_id,
        "name": name,
        "values": [
            {"key": "base_url", "value": base_url, "type": "default", "enabled": True},
            {"key": "auth_username", "value": "", "type": "default", "enabled": True},
            {"key": "auth_password", "value": "", "type": "secret", "enabled": True},
        ],
        "_postman_variable_scope": "environment",
        "_postman_exported_using": "Postman/11",
    }


for name, data in [
    ("blacklist-api.postman_collection.json", collection),
    ("local.postman_environment.json", environment("bfeec443-8b78-455e-91f2-0dfd58c9e14b", "Blacklist API - local", LOCAL_BASE_URL)),
    ("aws.postman_environment.json", environment("5c1f7a1e-3d2b-4c8e-9f60-2a7b1d4e8c31", "Blacklist API - AWS Elastic Beanstalk", AWS_BASE_URL)),
]:
    (HERE / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
