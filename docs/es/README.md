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
7. [Sandboxing de Archivos y Terminal](#sandboxing-de-archivos-y-terminal)
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
| Sandbox de capacidades | `kiro/capability_executor.py` | Sandboxing de readFile / writeFile / listDirectory / runCommand |
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
| **Python 3.11+** | Requerido solo para la ruta de metal desnudo |
| **Docker** | Requerido solo para la ruta de contenedor |

### Opción A — Metal desnudo

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # editar PROXY_API_KEY
kiro auth login
python main.py
```

### Opción B — Docker (imagen publicada)

```bash
docker pull ghcr.io/ankitcharolia/kiro-gateway:latest
docker run -d \
  --name kiro-gateway \
  -p 8000:8000 \
  -e PROXY_API_KEY=change-me \
  -v "${HOME}/.kiro:/root/.kiro:ro" \
  ghcr.io/ankitcharolia/kiro-gateway:latest
```

### Opción C — Docker Compose

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway
cp .env.example .env   # editar PROXY_API_KEY
docker compose up -d
```

---

## Configuración

```env
# Requerido
PROXY_API_KEY=change-me

# Ruta del CLI
KIRO_CLI_COMMAND=kiro

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
| Clave API | valor de `PROXY_API_KEY` |
| Modelo | `claude-sonnet-4-5` |

### Clientes compatibles con Anthropic
_(Claude Code, Kilo Code, Craft-agent, OpenClaw, …)_

| Configuración | Valor |
|---|---|
| URL Base | `http://localhost:8000` |
| Encabezado API Key | `x-api-key: <PROXY_API_KEY>` |
| Modelo | `claude-sonnet-4-5` |

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

## Sandboxing de Archivos y Terminal

| Capacidad | Comportamiento |
|---|---|
| `capability/readFile` | Solo dentro de `filesystem_roots` con `read: true`. Máx. 10 MB. |
| `capability/writeFile` | Solo dentro de raíces con `write: true`. |
| `capability/listDirectory` | Lista entradas dentro de raíces permitidas. |
| `capability/runCommand` | Solo comandos en `terminal.allowed_commands`. |

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
pip install -e ".[dev]"
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

## Licencia

AGPL-3.0 — ver [LICENSE](../../LICENSE).
