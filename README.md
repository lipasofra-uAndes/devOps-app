# Microservicio de lista negra

API REST Flask para registrar y consultar emails bloqueados. Persiste en PostgreSQL en AWS y permite SQLite para desarrollo local. Todos los endpoints de la lista negra requieren un JWT Bearer generado por `/auth/token`.

## Ejecución local

Requiere Python 3.10 o superior.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export JWT_SECRET_KEY='local-secret-key-change-before-deploying-123456'
export AUTH_USERNAME='api-client'
export AUTH_PASSWORD='local-password'
flask --app application run
```

Sin `DATABASE_URL`, la app crea `blacklist.db` en SQLite. Para probar con PostgreSQL, configura `DATABASE_URL` con una URI `postgresql://...`.

## Autenticación

`POST /auth/token` acepta credenciales configurables por `AUTH_USERNAME` y `AUTH_PASSWORD`. La respuesta incluye un JWT firmado con `JWT_SECRET_KEY`; se debe enviar como `Authorization: Bearer <access_token>`. Los valores de desarrollo predeterminados solo permiten ejecutar localmente: define credenciales propias y una clave aleatoria de al menos 32 bytes en Elastic Beanstalk. Nunca guardes secretos reales en Git.

```http
POST /auth/token
Content-Type: application/json

{"username":"api-client","password":"local-password"}
```

## Endpoints

### `POST /blacklists`

Requiere JWT. Registra un email y retorna `201`; si ya existe (ignorando mayúsculas/minúsculas), retorna `409`.

```json
{
  "email": "cliente@example.com",
  "app_uuid": "123e4567-e89b-12d3-a456-426614174000",
  "blocked_reason": "Contracargo confirmado"
}
```

`email` debe tener formato válido, `app_uuid` debe ser UUID y `blocked_reason` es opcional con máximo 255 caracteres. Errores de validación retornan `400`. La API almacena la IP de origen y la fecha/hora UTC.

### `GET /blacklists/<email>`

Requiere JWT. Siempre retorna `200`, incluso si el email no existe.

```json
{
  "email": "cliente@example.com",
  "blacklisted": true,
  "blocked_reason": "Contracargo confirmado"
}
```

Para un email no registrado, `blacklisted` es `false` y `blocked_reason` es `null`. La comparación de emails no distingue mayúsculas/minúsculas.

### `GET /health`

Health check sin autenticación que ejecuta una consulta a la base de datos. Retorna `200` cuando está disponible y `503` si falla.

## Pruebas

```bash
pip install pytest
python -m pytest -q
```

## AWS Elastic Beanstalk y RDS

El `Procfile` inicia Gunicorn con `application:application`. En la configuración de entorno de Elastic Beanstalk define `DATABASE_URL`, `JWT_SECRET_KEY`, `AUTH_USERNAME` y `AUTH_PASSWORD`. El grupo de seguridad de RDS debe permitir el puerto PostgreSQL (5432) desde el grupo de seguridad de las instancias de Elastic Beanstalk; no expongas la base de datos públicamente. Configura la ruta de health check del balanceador como `/health`.

La aplicación crea las tablas al iniciar. Antes de utilizarla con datos importantes, planifica migraciones versionadas en lugar de depender de `create_all` para cambios futuros de esquema.

## Postman

Importa `postman/blacklist-api.postman_collection.json` y `postman/local.postman_environment.json`. Ejecuta primero **Obtener JWT**; la colección guarda automáticamente el token en el environment. Luego prueba los escenarios de alta, duplicado, consulta, validación y autenticación.