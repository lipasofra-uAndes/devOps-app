# Integrantes del equipo DevOps Legends
- Jesus Sierra Angarita
- Santiago Guerrero
- Danny Vasquez
- Lina Soler


# Entregas

## Entrega 1
- [video](https://uniandes-my.sharepoint.com/:v:/g/personal/l_solerf_uniandes_edu_co/IQAyQkBOVZDhRrzJq5mUBaWRASALO5vROyXbzKFKWZpkd8c?nav=eyJyZWZlcnJhbEluZm8iOnsicmVmZXJyYWxBcHAiOiJPbmVEcml2ZUZvckJ1c2luZXNzIiwicmVmZXJyYWxBcHBQbGF0Zm9ybSI6IldlYiIsInJlZmVycmFsTW9kZSI6InZpZXciLCJyZWZlcnJhbFZpZXciOiJNeUZpbGVzTGlua0NvcHkifX0&e=ryQQ67)

- [coleccion postman](https://documenter.getpostman.com/view/14923156/2sBYHSxfXh) 

- [archivo analisis despliegues]( https://uniandes-my.sharepoint.com/:w:/g/personal/ds_guerrerom1_uniandes_edu_co/IQA0L47yb3pQRZbkXz0ucXqsAU63AdL9yd5Ivn_liI8GNbY?e=UXuwhV)

## Entrega 2

- [video]()


- [archivo analisis corridas pipeline]()


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

Documentación publicada: <https://documenter.getpostman.com/view/14923156/2sBYHSxfXh>

Importa `postman/blacklist-api.postman_collection.json` y el environment que corresponda: `postman/aws.postman_environment.json` (Elastic Beanstalk, `http://devops-blacklist-api-dev.eba-2zph7mid.us-east-1.elasticbeanstalk.com`) o `postman/local.postman_environment.json` (`http://127.0.0.1:5000`). La colección usa la URL de AWS por defecto.
En el environment, configura `auth_username` y `auth_password` con las credenciales autorizadas. Mantén el environment con secretos fuera de Git. Ejecuta **toda la colección en orden**: crea un email único por ejecución y guarda el JWT solo como variable temporal de la colección. Incluye 11 escenarios de salud, alta, duplicado, consultas, validación y acceso no autorizado. Cada endpoint contiene descripción y ejemplos de respuesta para publicar la documentación desde Postman. La URL pública de la documentación debe incluirse en el informe.

Para verificar automáticamente desde Windows con Newman (sin guardar credenciales):

```powershell
$env:AUTH_USERNAME = '<usuario>'
$env:AUTH_PASSWORD = '<contraseña>'
npx --yes newman run postman/blacklist-api.postman_collection.json -e postman/local.postman_environment.json --env-var base_url=https://<dominio> --env-var auth_username=$env:AUTH_USERNAME --env-var auth_password=$env:AUTH_PASSWORD
```

`postman/build_collection.py` regenera los JSON versionados. Todos los escenarios incluyen un ejemplo de solicitud y respuesta; `tests/test_app.py` verifica que los ejemplos de error coincidan con lo que responde la API.

La evidencia de los escenarios y la ejecución local de la Entrega 1 está en [`docs/entrega1-postman.md`](docs/entrega1-postman.md).

## Medición de estrategias de despliegue

El archivo `VERSION` viaja dentro de cada paquete de código y aparece en la cabecera `X-App-Version` de todas las respuestas. Cambia `VERSION` (por ejemplo `v1` a `v2`) **antes de empaquetar** la versión nueva. No uses una variable de entorno para distinguir paquetes, porque las instancias antiguas podrían recibir el mismo valor.

El siguiente monitor consulta continuamente un email inexistente con JWT durante cada despliegue manual. Registra una fila por petición en CSV y un resumen JSON con éxitos, fallos, disponibilidad, latencia y cantidad de respuestas por versión. No modifica la lista negra. Ejecútalo antes de iniciar la estrategia en Elastic Beanstalk y déjalo activo hasta que el entorno vuelva a estar estable:

```powershell
$env:AUTH_USERNAME = '<usuario>'
$env:AUTH_PASSWORD = '<contraseña>'
python scripts/monitor_deployment.py --base-url https://<dominio> --strategy rolling --duration 900 --interval 1
```

Repite con nombres como `all-at-once`, `rolling-additional-batch` e `immutable`. Los archivos se guardan en `results/`, que está excluido de Git porque pueden contener la URL del entorno y datos de las pruebas. El monitor muestra `unknown` si el paquete desplegado todavía no envía `X-App-Version`. Una muestra con error incluye respuestas HTTP distintas de 200, tiempos de espera y respuestas cuyo JSON no corresponde a la consulta esperada. Los datos son observaciones del cliente durante la ventana de medición; usa eventos y capturas de AWS para determinar duración total, instancias originales o nuevas y cantidad de EC2 de cada estrategia.
