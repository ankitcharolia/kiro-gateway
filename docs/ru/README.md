# Kiro Gateway — Документация

**Полностью совместимый с ACP** шлюз, позволяющий любому инструменту ИИ, совместимому с OpenAI или Anthropic, использовать единственную подписку Kiro, маршрутизируя каждый запрос через официальный бинарный файл `kiro` CLI.

---

## Содержание

1. [Архитектура](#архитектура)
2. [Установка](#установка)
3. [Конфигурация](#конфигурация)
4. [Настройка клиента](#настройка-клиента)
5. [API эндпоинты](#api-эндпоинты)
6. [Вызовы инструментов](#вызовы-инструментов)
7. [Песочница файловой системы и терминала](#песочница-файловой-системы-и-терминала)
8. [Потоковые события](#потоковые-события)
9. [Запуск тестов](#запуск-тестов)
10. [Процесс выпуска](#процесс-выпуска)

---

## Архитектура

Каждый запрос проходит через официальный `kiro` CLI через JSON-RPC 2.0 по stdio — без приватных HTTP-эндпоинтов, без совместного использования учётных данных, без пулинга аккаунтов.

```
Любой клиент OpenAI / Anthropic
               │
  ┌────────────┴────────────┐
  │                         │
routes_openai_shim    routes_anthropic_shim
 /v1/chat/completions   /v1/messages
               │
         shim_service.py
    (оркестрация + циклы вызовов инструментов)
               │
         acp_client.py
     (JSON-RPC 2.0 по stdio)
               │
           kiro CLI
      (официальный, аутентифицированный)
               │
         Бэкенд Kiro
```

### Основные компоненты

| Компонент | Файл | Назначение |
|---|---|---|
| ACP-мост | `kiro/acp_client.py` | Запускает CLI `kiro`; JSON-RPC 2.0 по stdio |
| Модели ACP | `kiro/acp_models.py` | Pydantic-модели для всех типов ACP |
| Песочница возможностей | `kiro/capability_executor.py` | Песочница readFile/writeFile/listDirectory/runCommand |
| Оркестрация | `kiro/shim_service.py` | Стриминг, циклы инструментов, жизненный цикл сессии |
| Маршруты ACP | `kiro/routes_acp.py` | `/acp/chat`, `/acp/chat/stream` |
| OpenAI shim | `kiro/routes_openai_shim.py` | `/v1/chat/completions`, `/v1/models` |
| Anthropic shim | `kiro/routes_anthropic_shim.py` | `/v1/messages`, `/v1/models` |
| Страж соответствия | `kiro/compliance.py` | Принудительное использование одного аккаунта при запуске |
| Резолвер моделей | `kiro/model_resolver.py` | Сопоставление имён моделей с ID, поддерживаемыми Kiro |
| Стражи нагрузки | `kiro/payload_guards.py` | Валидация запросов и ограничения размера |
| Токенизатор | `kiro/tokenizer.py` | Подсчёт токенов для принятия решений об усечении |
| Усечение | `kiro/truncation_state.py` | Усечение истории разговора |

---

## Установка

### Предварительные условия

| Требование | Примечания |
|---|---|
| **Kiro CLI** | Установить с [kiro.dev](https://kiro.dev), затем запустить `kiro auth login` |
| **Python 3.11+** | Требуется только для варианта bare-metal |
| **Docker** | Требуется только для варианта с контейнером |

### Вариант A — Bare metal

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # отредактировать PROXY_API_KEY
kiro auth login
python main.py
```

### Вариант B — Docker (опубликованный образ)

```bash
docker pull ghcr.io/ankitcharolia/kiro-gateway:latest
docker run -d \
  --name kiro-gateway \
  -p 8000:8000 \
  -e PROXY_API_KEY=change-me \
  -v "${HOME}/.kiro:/root/.kiro:ro" \
  ghcr.io/ankitcharolia/kiro-gateway:latest
```

### Вариант C — Docker Compose

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway
cp .env.example .env   # отредактировать PROXY_API_KEY
docker compose up -d
```

---

## Конфигурация

```env
# Обязательно
PROXY_API_KEY=change-me

KIRO_CLI_COMMAND=kiro
ACP_ENABLED=true
OPENAI_SHIM_ENABLED=true
ANTHROPIC_SHIM_ENABLED=true
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
COMPLIANCE_MODE=true
```

---

## Потоковые события

| Событие ACP | OpenAI SSE | Anthropic SSE |
|---|---|---|
| `text` | чанк `delta.content` | `content_block_delta[text_delta]` |
| `tool_call` | чанк `delta.tool_calls` | `content_block_start[tool_use]` |
| `thinking` | чанк `delta.content` | `content_block_delta[text_delta]` |
| `done` | `[DONE]` + `finish_reason` | `message_delta` + `message_stop` |
| `error` | чанк ошибки + `[DONE]` | событие `error` |

---

## Лицензия

AGPL-3.0 — см. [LICENSE](../../LICENSE).
