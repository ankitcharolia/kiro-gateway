# Kiro Gateway — Documentación

Un puente **completamente compatible con ACP** que permite a cualquier herramienta de IA compatible con OpenAI o Anthropic utilizar tu suscripción única de Kiro, enrutando cada solicitud a través del binario oficial `kiro` CLI.

---

## Tabla de Contenidos

1. [Arquitectura](#arquitectura)
2. [Instalación](#instalación)
3. [Configuración](#configuración)
4. [Configuración del Cliente](#configuración-del-cliente)
5. [Endpoints de la API](#endpoints-de-la-api)
6. [Llamadas a Herramientas](#llamadas-a-herramientas)
7. [Ejecución de Herramientas y Permisos](#ejecución-de-herramientas-y-permisos)
8. [Eventos de Streaming](#eventos-de-streaming)
9. [Ejecución de Pruebas](#ejecución-de-pruebas)
10. [Proceso de Publicación](#proceso-de-publicación)

---

## Arquitectura

Cada solicitud pasa por el CLI oficial de `kiro` mediante JSON-RPC 2.0 sobre stdio — sin endpoints HTTP privados, sin compartir credenciales, sin agrupación de cuentas.

```
Cualquier cliente OpenAI / Anthropic
               │
  ┌────────────┴────────────┐
  │                         │
routes_openai_shim    routes_anthropic_shim
 /v1/chat/completions   /v1/messages
               │
         shim_service.py
   (orquestación + rondas de llamadas a herramientas)
               │
         acp_client.py
     (JSON-RPC 2.0 sobre stdio)
               │
           kiro CLI
     (oficial, autenticado)
               │
         Backend de Kiro
```

### Componentes Principales

| Componente | Archivo | Propósito |
|---|---|---|
| Puente ACP | `kiro/acp_client.py` | Lanza el CLI `kiro`; JSON-RPC 2.0 sobre stdio |
| Modelos ACP | `kiro/acp_models.py` | Modelos Pydantic para todos los tipos ACP |
| Manejo de permisos | `kiro/acp_client.py` | Responde a `session/request_permission` (aprobación automática o rechazo según `ACP_TRUST_TOOLS`) |
| Orquestación | `kiro/shim_service.py` | Streaming, rondas de herramientas, ciclo de vida de sesión |
| Rutas ACP | `kiro/routes_acp.py` | `/acp/chat`, `/acp/chat/stream` |
| Shim OpenAI | `kiro/routes_openai_shim.py` | `/v1/chat/completions`, `/v1/models` |
| Shim Anthropic | `kiro/routes_anthropic_shim.py` | `/v1/messages`, `/v1/models` |
| Guarda de cumplimiento | `kiro/compliance.py` | Aplicación de cuenta única al inicio |
| Resolutor de modelos | `kiro/model_resolver.py` | Mapea nombres de modelos a IDs compatibles con Kiro |
| Guardias de payload | `kiro/payload_guards.py` | Validación de solicitudes y límites de tamaño |
| Tokenizador | `kiro/tokenizer.py` | Conteo de tokens para decisiones de truncamiento |
| Truncamiento | `kiro/truncation_state.py` | Truncamiento del historial de conversación |

---

## Instalación

### Requisitos Previos

| Requisito | Notas |
|---|---|
| **Kiro CLI** | Instalar desde [kiro.dev](https://kiro.dev), luego ejecutar `kiro auth login` |
| **Python 3.14+** | Requerido solo para la ruta de metal desnudo |
| **Docker** | Requerido solo para la ruta de contenedor |

### Opción A — Metal desnudo

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway
uv sync
cp .env.example .env   # editar KIRO_GATEWAY_API_KEY
kiro auth login
uv run main.py
```

### Opción B — Docker (imagen publicada)

```bash
docker pull ghcr.io/ankitcharolia/kiro-gateway:latest
docker run -d \
  --name kiro-gateway \
  -p 8000:8000 \
  -e KIRO_GATEWAY_API_KEY=change-me \
  -v "${HOME}/.kiro:/root/.kiro:ro" \
  ghcr.io/ankitcharolia/kiro-gateway:latest
```

### Opción C — Docker Compose

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway
cp .env.example .env   # editar KIRO_GATEWAY_API_KEY
docker compose up -d
```

---

## Configuración

```env
# Requerido
KIRO_GATEWAY_API_KEY=change-me

# Ruta del CLI
KIRO_CLI_PATH=kiro-cli

ACP_TRUST_TOOLS=true        # kiro-cli ejecuta sus propias herramientas y pide permiso; true = aprobar, false = rechazar
ACP_WORKSPACE_DIR=          # Directorio de trabajo de la sesion (por defecto: cwd del proceso)
ACP_TIMEOUT=120             # Segundos de espera de una respuesta JSON-RPC

# Indicadores de características
ACP_ENABLED=true
OPENAI_SHIM_ENABLED=true
ANTHROPIC_SHIM_ENABLED=true

# Servidor
SERVER_HOST=0.0.0.0
SERVER_PORT=8000

# Cumplimiento
COMPLIANCE_MODE=true
```

---

## Configuración del Cliente

### Clientes compatibles con OpenAI
_(Cursor, Cline, Continue, OpenCode, Hermes-agent, OpenClaw, …)_

| Configuración | Valor |
|---|---|
| URL Base | `http://localhost:8000/v1` |
| Clave API | valor de `KIRO_GATEWAY_API_KEY` |
| Modelo | `claude-sonnet-4.6` |

### Clientes compatibles con Anthropic
_(Claude Code, Kilo Code, Craft-agent, OpenClaw, …)_

| Configuración | Valor |
|---|---|
| URL Base | `http://localhost:8000` |
| Encabezado API Key | `x-api-key: <KIRO_GATEWAY_API_KEY>` |
| Modelo | `claude-sonnet-4.6` |

### Clientes ACP nativos

```
http://localhost:8000/acp/chat          # sin streaming
http://localhost:8000/acp/chat/stream   # streaming SSE
```

---

## Endpoints de la API

| Modo | Método | Endpoint | Descripción |
|---|---|---|---|
| ACP | POST | `/acp/chat` | Conversación ACP sin streaming |
| ACP | POST | `/acp/chat/stream` | Conversación ACP con streaming SSE |
| OpenAI | GET | `/v1/models` | Listar modelos disponibles |
| OpenAI | POST | `/v1/chat/completions` | Completaciones con y sin streaming |
| Anthropic | GET | `/v1/models` | Listar modelos disponibles |
| Anthropic | POST | `/v1/messages` | Mensajes con y sin streaming |

---

## Llamadas a Herramientas

1. El CLI `kiro` emite un evento `tool_call` ACP durante el streaming.
2. El shim lo traduce al formato del cliente (`function_call` / `tool_use`) y lo transmite.
3. El cliente ejecuta la herramienta y envía los resultados de vuelta.
4. El gateway inyecta los resultados en un `session/prompt` de seguimiento.

---

## Ejecución de Herramientas y Permisos

El CLI `kiro` incluye sus **propias** herramientas integradas (lecturas/ediciones
de archivos, ejecución de comandos, búsqueda) y las ejecuta él mismo dentro del
directorio de trabajo de la sesión. El gateway **no** anuncia ninguna capacidad
de sistema de archivos ni de terminal del lado del cliente, por lo que nunca
ejecuta herramientas en nombre del agente — solo responde a las solicitudes de
permiso que el agente le envía.

| Solicitud del agente | Comportamiento del gateway |
|---|---|
| `session/request_permission` | Aprueba automáticamente una sola invocación (`allow_once`) cuando `ACP_TRUST_TOOLS=true`; la rechaza (`reject_once`) cuando es `false`. |

```env
ACP_TRUST_TOOLS=true     # aprobar automáticamente las ejecuciones de herramientas integradas (ediciones de archivos, comandos)
ACP_TRUST_TOOLS=false    # solo respuestas: se deniega toda solicitud de permiso de herramienta
ACP_WORKSPACE_DIR=/path  # directorio de trabajo donde opera kiro-cli (por defecto: cwd del proceso)
```

Una solicitud también puede pasar `filesystem_roots`; la ruta de la primera raíz
se convierte en el `cwd` de `session/new`.

> **Seguridad:** con `ACP_TRUST_TOOLS=true` el agente puede escribir archivos y
> ejecutar comandos en el directorio de trabajo sin confirmación humana. Usa
> `false` para un despliegue de solo lectura/respuesta.

---

## Eventos de Streaming

| Evento ACP | SSE OpenAI | SSE Anthropic |
|---|---|---|
| `text` | chunk `delta.content` | `content_block_delta[text_delta]` |
| `tool_call` | chunk `delta.tool_calls` | `content_block_start[tool_use]` |
| `thinking` | chunk `delta.content` | `content_block_delta[text_delta]` |
| `done` | `[DONE]` + `finish_reason` | `message_delta` + `message_stop` |
| `error` | chunk de error + `[DONE]` | evento `error` |

---

## Ejecución de Pruebas

```bash
uv sync
pytest tests/ -v
pytest --cov=kiro --cov-report=term-missing
```

---

## Proceso de Publicación

```bash
git tag v2.1.0
git push origin v2.1.0
# CI construye linux/amd64 + linux/arm64 y publica la imagen Docker
# y también crea un GitHub Release con archivos de código fuente.
```

---

## Apoyo

Si este proyecto te ahorra tiempo, considera apoyar su desarrollo continuo:

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/achar)
[![PayPal](https://img.shields.io/badge/Donate-PayPal-blue.svg)](https://paypal.me/ankitcharolia)

---

## Licencia

AGPL-3.0 — ver [LICENSE](../../LICENSE).
