# Evidencia de pruebas de la API con Postman

## Alcance

La colección versionada en `postman/blacklist-api.postman_collection.json` contiene los escenarios funcionales de la API y ejemplos de solicitud y respuesta. Usa variables para la URL, el usuario y la contraseña. No contiene credenciales reales. Los environments de ejemplo (`local` y `aws`) también dejan la contraseña vacía.

## Documentación publicada

- URL pública: <https://documenter.getpostman.com/view/14923156/2sBYHSxfXh>
- Workspace del equipo: `UniAndes` (udeapp.postman.co), colección `Global Email Blacklist API - Entrega 1`.
- `base_url` publicada: `http://devops-blacklist-api-dev.eba-2zph7mid.us-east-1.elasticbeanstalk.com` (Elastic Beanstalk, us-east-1). Se publicó sin environment, de modo que no expone usuario ni contraseña.
- La URL solo responde mientras el entorno de Beanstalk está activo; el equipo lo terminó el 17/10/2026 para ahorrar créditos.

## Ejecución local verificada

El 17 de octubre de 2026 se ejecutó la colección completa con Newman contra la aplicación Flask local. El registro está en la carpeta de entrega del equipo (`workspace/entrega1/newman_local.txt`, fuera de este repositorio): **11 solicitudes, 12 aserciones, 0 fallos**. Las pruebas de Python del repositorio dieron **11 aprobadas**. Estas ejecuciones verifican el código y la colección, no el entorno AWS.

| N.º | Escenario | Resultado esperado | Resultado local |
|---:|---|---|---|
| 1 | Obtener JWT con credenciales válidas | 200 y token | Aprobado |
| 2 | Consultar salud y versión | 200, `status=ok`, cabecera `X-App-Version` | Aprobado |
| 3 | Registrar email con UUID y motivo | 201 | Aprobado |
| 4 | Registrar email duplicado | 409 | Aprobado |
| 5 | Consultar email bloqueado | 200, `blacklisted=true` y motivo | Aprobado |
| 6 | Consultar email no registrado | 200, `blacklisted=false` | Aprobado |
| 7 | Enviar email inválido | 400 | Aprobado |
| 8 | Enviar UUID inválido | 400 | Aprobado |
| 9 | Enviar motivo de más de 255 caracteres | 400 | Aprobado |
| 10 | Consultar sin token | 401 | Aprobado |
| 11 | Autenticarse con contraseña incorrecta | 401 | Aprobado |

## Observación del servicio durante despliegues AWS

El monitor del repositorio consultó continuamente un email inexistente mientras el equipo ejecutaba All at Once, Rolling, Rolling with Additional Batch e Immutable. Los CSV/JSON de la carpeta del equipo `workspace/entrega1/results/` respaldan los conteos de respuestas, fallos y versiones antiguas/nuevas. El informe `workspace/entrega1/Informe_Comparativo_Estrategias_Despliegue.docx` analiza esos datos. El monitor no ejecuta todos los escenarios funcionales de Postman: **hace falta correr la colección completa contra el entorno AWS cuando esté activo**.

## Pasos pendientes de esta parte

1. Solicitar al administrador la URL activa de Beanstalk y credenciales de prueba de la API por un canal seguro. El entorno fue terminado por el equipo para ahorrar créditos; no reactivarlo sin coordinarlo con el responsable.
2. Cuando el equipo active el entorno, correr la colección completa con Newman o Postman usando un environment local con secretos no versionados. Guardar el resumen de ejecución y capturas de las solicitudes `POST /blacklists` y `GET /blacklists/<email>` en AWS.
3. ~~Publicar la documentación de Postman~~ (hecho el 17/10/2026; URL arriba). Anexar la URL al PDF de entrega.
4. En el video, mostrar la colección, sus aserciones y una ejecución real contra la API en AWS; explicar que los resultados CSV miden continuidad del servicio durante los cuatro despliegues.


