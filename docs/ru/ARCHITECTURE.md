# Архитектурный обзор: Kiro Gateway

## 1. Назначение

Kiro Gateway — это **мост, ориентированный на соблюдение правил (compliance-first)**, который позволяет любому инструменту, работающему с API OpenAI, Anthropic или с нативным протоколом ACP, использовать единственную подписку Kiro.

Ключевой принцип: **каждый запрос обслуживается путём обращения к официальному бинарному файлу `kiro-cli` в режиме `acp`** через Agent Client Protocol (ACP) — то есть через JSON-RPC 2.0 поверх stdio.

Шлюз **никогда**:

- не вызывает приватные HTTP-API Kiro;
- не объединяет учётные записи в пул;
- не работает с учётными данными напрямую — вся аутентификация выполняется внутри `kiro-cli` командой `kiro-cli login`.

Ценность шлюза — **трансляция протоколов**: он переводит формы запросов и ответов между API OpenAI/Anthropic, нативным ACP и протоколом `kiro-cli`, не искажая и не отбрасывая содержимое пользователя.

### Поддерживаемые форматы API

| Формат | Эндпоинты | Аутентификация |
|--------|-----------|----------------|
| **Native ACP** | `POST /acp/chat`, `POST /acp/chat/stream` | — |
| **OpenAI** | `GET /v1/models`, `POST /v1/chat/completions` | `Authorization: Bearer <KIRO_GATEWAY_API_KEY>` |
| **Anthropic** | `GET /v1/models`, `POST /v1/messages` | `x-api-key: <KIRO_GATEWAY_API_KEY>` |

Все форматы работают одновременно на одном сервере.

### Архитектурная модель

```
┌───────────────────────────────────────────────────────────────────┐
│                            Клиенты                                  │
│  ┌──────────────┐   ┌──────────────────┐   ┌────────────────────┐  │
│  │ OpenAI-       │   │ Anthropic-       │   │ Нативные           │  │
│  │ совместимые   │   │ совместимые      │   │ ACP-клиенты        │  │
│  │ (Cursor,      │   │ (Claude Code,    │   │ (Zed, плагины IDE) │  │
│  │  Cline, ...)  │   │  Kilo Code, ...) │   │                    │  │
│  └──────┬───────┘   └────────┬─────────┘   └──────────┬─────────┘  │
└─────────┼────────────────────┼────────────────────────┼────────────┘
          │                    │                        │
          ▼                    ▼                        ▼
┌───────────────────────────────────────────────────────────────────┐
│                          Kiro Gateway                               │
│  routes_openai_shim.py   routes_anthropic_shim.py   routes_acp.py   │
│            └──────────────────┬─────────────────────────┘           │
│                               ▼                                     │
│                        shim_service.py                              │
│             (жизненный цикл сессии на запрос,                       │
│              проброс/агрегация событий)                             │
│                               ▼                                     │
│                         acp_client.py                               │
│              (один подпроцесс kiro-cli,                            │
│               JSON-RPC 2.0 поверх stdio)                           │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
                  ┌───────────────────────────┐
                  │      kiro-cli acp         │  ← только официальный бинарь
                  │  (официальный, авториз.)  │
                  └─────────────┬─────────────┘
                                │
                                ▼
                  ┌───────────────────────────┐
                  │      Kiro Backend         │
                  └───────────────────────────┘
```

> **Контроль единственной учётной записи.** При запуске шлюз проверяет, что одновременно активна не более чем одна сессия `kiro-cli` (`kiro.compliance.validate_single_account_compliance`). Попытка запустить параллельные учётные записи вызывает жёсткую ошибку `ComplianceError`.

## 2. Структура проекта

```
kiro-gateway/
├── main.py                       # Точка входа + lifespan: загрузка .env,
│                                 # запуск ACPClient, однократная initialize
├── kiro/
│   ├── acp_client.py             # Подпроцесс kiro-cli + JSON-RPC мост +
│   │                             # трансляция протокола + обработка разрешений
│   ├── acp_models.py             # Pydantic-модели (конверты JSON-RPC,
│   │                             # параметры prompt, блоки контента)
│   ├── shim_service.py           # session/new на запрос, проброс стрима,
│   │                             # агрегация для non-streaming
│   ├── routes_openai_shim.py     # /v1/chat/completions, /v1/models
│   ├── routes_anthropic_shim.py  # /v1/messages, /v1/models
│   ├── routes_acp.py             # /acp/chat, /acp/chat/stream
│   ├── config.py                 # Настройки из окружения (объект settings
│   │                             # + модульные константы)
│   ├── compliance.py             # Контроль единственной учётной записи
│   └── capability_executor.py    # Заглушка (сохранена, НЕ в активном пути)
├── tests/                        # conftest.py + unit/ + integration/
├── docs/                         # Переводы документации (en, ru, ...)
├── .env.example                  # Шаблон конфигурации
├── requirements.txt
└── pytest.ini
```

> Некоторые устаревшие модули могут оставаться в `kiro/`, но активный путь ACP составляют именно перечисленные выше файлы. `capability_executor.py` сохранён ради совместимости, но в живом пути обработки запросов не участвует.

## 3. Архитектурная топология и компоненты

Система построена на асинхронном фреймворке FastAPI и использует событийную модель управления жизненным циклом (`lifespan`).

### 3.1. Точка входа (`main.py`)

При старте приложения `main.py`:

1. **Загружает `.env`** (через `python-dotenv`) до импорта `kiro.config`, при этом реальные переменные окружения имеют приоритет над значениями из `.env`.
2. **Настраивает логирование** через loguru (цветной вывод, уровень `INFO`).
3. **В `lifespan`** создаёт единственный экземпляр `ACPClient`, запускает подпроцесс `kiro-cli acp` (`acp_client.start()`) и однократно выполняет ACP-рукопожатие `initialize` (`acp_client.initialize()`).
4. **Сохраняет состояние** в `app.state.acp_client` и `app.state.shim_service` (один общий `ShimService` на процесс).
5. **Подключает роутеры** в зависимости от флагов `ACP_ENABLED`, `OPENAI_SHIM_ENABLED`, `ANTHROPIC_SHIM_ENABLED`, добавляет CORS-middleware и эндпоинт `GET /health`.
6. **При остановке** корректно завершает подпроцесс `kiro-cli` (`acp_client.stop()`).

### 3.2. ACP-клиент (`kiro/acp_client.py`)

`ACPClient` управляет одним подпроцессом `kiro-cli acp` на весь процесс шлюза. Он безопасен для конкурентного использования: `initialize` выполняется один раз при старте, а `new_session` вызывается на каждый запрос, что обеспечивает изоляцию параллельных промптов.

Ответственность компонента:

- **Запуск подпроцесса** и чтение его stdout/stderr в отдельных asyncio-задачах.
- **JSON-RPC плумбинг**: отправка запросов, сопоставление ответов по `id` через `Future`, маршрутизация уведомлений `session/update` в очереди событий по `sessionId`.
- **Трансляция протокола**: преобразование «сырых» ACP-форм в нормализованный внутренний контракт событий (см. раздел 3.4).
- **Обработка разрешений**: ответы на запросы `session/request_permission`, приходящие от агента.

Параметр `command` напрямую соответствует переменной окружения `KIRO_CLI_PATH`.

### 3.3. Протокол ACP (формат обмена по stdio)

`kiro-cli acp` реализует протокол Zed Agent Client Protocol. Точность форм обязательна — некорректный `initialize` приводит к немедленному выходу агента.

1. **`initialize`** — один раз на процесс.
   Параметры:
   ```json
   {
     "protocolVersion": 1,
     "clientCapabilities": {
       "fs": {"readTextFile": false, "writeTextFile": false},
       "terminal": false
     }
   }
   ```
   Возвращает `agentCapabilities`, `authMethods`, `agentInfo`. **Идентификатор сессии не возвращается.**

2. **`session/new`** — один раз на запрос шлюза.
   Параметры: `{"cwd": "<абсолютный путь>", "mcpServers": []}` → результат `{sessionId, modes}`.

3. **`session/prompt`** — на каждый ход (turn).
   Параметры: `{"sessionId", "prompt": [{"type": "text", "text": "..."}]}` → результат `{stopReason}`.

4. **`session/update`** — уведомления (без `id`), приходящие во время выполнения промпта; различаются по полю `update.sessionUpdate`:
   `agent_message_chunk`, `agent_thought_chunk`, `tool_call`, `tool_call_update`.

5. **`session/request_permission`** — запрос (с `id`), который агент отправляет шлюзу перед запуском встроенного инструмента. Шлюз отвечает:
   ```json
   {"outcome": {"outcome": "selected", "optionId": "<id опции>"}}
   ```

**Важно:** `kiro-cli` запускает **собственные** встроенные инструменты (правка файлов, выполнение команд, поиск и т. д.) и делает это сам, внутри рабочего каталога сессии. Шлюз не объявляет клиентских возможностей `fs`/`terminal` и поэтому никогда не выполняет инструменты за агента — он лишь **отвечает на запросы разрешений**:

| Запрос агента | Поведение шлюза |
|---------------|-----------------|
| `session/request_permission` при `ACP_TRUST_TOOLS=true` | Автоматически одобряет одно выполнение (`allow_once`) |
| `session/request_permission` при `ACP_TRUST_TOOLS=false` | Отклоняет (`reject_once`) |

### 3.4. Внутренний контракт событий

`ACPClient` нормализует уведомления `session/update` и финальный результат промпта в **простые словари (dict)**. `ShimService` пробрасывает их без изменений, а транслирующие роуты преобразуют их в SSE формата OpenAI/Anthropic/ACP.

| Событие (dict) | Поля | Источник |
|----------------|------|----------|
| `{"type": "text"}` | `content: str` | `agent_message_chunk` |
| `{"type": "thinking"}` | `content: str` | `agent_thought_chunk` |
| `{"type": "tool_call"}` | `id, name, arguments: dict` | `tool_call` |
| `{"type": "done"}` | `finish_reason: str, usage: dict` | `stopReason` результата промпта |
| `{"type": "error"}` | `message: str` | ошибка JSON-RPC / выход подпроцесса |

Особенности:

- События — это **словари**; доступ через `event.get("type")`, а не через атрибуты.
- `stopReason` нормализуется: `end_turn → stop`, `max_tokens → length`, `tool_use → tool_calls` (Anthropic-роут при необходимости преобразует `stop → end_turn` обратно).
- `thinking` **не выводится** в потоки контента OpenAI/Anthropic — оно предназначено только для нативных ACP-потребителей через `POST /acp/chat/stream`.

### 3.5. Оркестрация (`kiro/shim_service.py`)

`ShimService` — это разделяемый без состояния слой оркестрации для всех семейств роутов. Отвечает за:

1. **Жизненный цикл сессии**: на каждый запрос создаёт новую ACP-сессию (`ACPClient.new_session`), чтобы конкурентные запросы оставались изолированными.
2. **Потоковую передачу в реальном времени**: метод `stream_tokens` выдаёт нормализованные dict-события по мере их поступления.
3. **Непотоковое завершение**: метод `complete` агрегирует тот же конвейер в один итоговый словарь ответа `{content, tool_calls, finish_reason, usage}`.

Рабочий каталог сессии (`cwd`) определяется так: при наличии `filesystem_roots` берётся путь первого корня, иначе используется `ACP_WORKSPACE_DIR` / рабочий каталог процесса.

### 3.6. Транслирующие роуты

- **`routes_openai_shim.py`** — `GET /v1/models`, `POST /v1/chat/completions`. Преобразует сообщения OpenAI в ACP-сообщения, транслирует dict-события в чанки `chat.completion.chunk` (для стрима) или в объект `chat.completion` (для non-stream). Параллельные tool-calls отражаются через индексированные дельта-чанки `tool_calls`.
- **`routes_anthropic_shim.py`** — `GET /v1/models`, `POST /v1/messages`. Транслирует события в таксономию SSE Anthropic: `message_start`, `content_block_start`, `content_block_delta` (`text_delta` и `input_json_delta`), `content_block_stop`, `message_delta`, `message_stop`.
- **`routes_acp.py`** — `POST /acp/chat`, `POST /acp/chat/stream`. Передаёт нативные ACP-события почти один-к-одному (`acp_text`, `acp_tool_call`, `acp_thinking`, `acp_done`, `acp_error`).

### 3.7. Контроль соответствия (`kiro/compliance.py`)

`validate_single_account_compliance(session_count)` гарантирует, что одновременно активна не более чем одна сессия Kiro: при `session_count > 1` поднимается `ComplianceError`. Объединение учётных записей в пул не поддерживается принципиально.

## 4. Поток данных

### 4.1. Общая схема

```
Клиент (OpenAI / Anthropic / native-ACP)
        │  HTTP
        ▼
routes_openai_shim.py / routes_anthropic_shim.py / routes_acp.py
        │  (трансляция запроса в ACP-сообщения)
        ▼
shim_service.py
        │  new_session() → sessionId    (изоляция на запрос)
        ▼
acp_client.py
        │  JSON-RPC 2.0 поверх stdio
        ▼
kiro-cli acp   (официальный авторизованный бинарь)
        │
        ▼
Kiro Backend
        │
        ▼  поток session/update (agent_message_chunk, tool_call, ...)
acp_client.py
        │  нормализация → dict-события (text / thinking / tool_call / done / error)
        ▼
shim_service.py  (проброс / агрегация)
        │
        ▼  трансляция в SSE целевого формата
Клиент
```

### 4.2. Потоковый запрос (streaming)

1. Роут принимает HTTP-запрос, проверяет API-ключ и преобразует сообщения в ACP-форму.
2. `ShimService.stream_tokens` создаёт новую сессию (`session/new`) и запускает `session/prompt`.
3. `ACPClient` отправляет промпт и читает уведомления `session/update`, помещая нормализованные события в очередь сессии.
4. Роут получает события и на лету транслирует их в SSE целевого формата.
5. Завершающее событие `done` (или `error`) закрывает поток; OpenAI добавляет `finish_reason` и `[DONE]`, Anthropic — `message_delta` + `message_stop`.

### 4.3. Непотоковый запрос (non-streaming)

`ShimService.complete` использует тот же конвейер `prompt_stream`, но аккумулирует текст и tool-calls в единый ответ, который роут оборачивает в `chat.completion` (OpenAI) или объект `message` (Anthropic).

## 5. Доступные модели

`GET /v1/models` возвращает список идентификаторов моделей. По умолчанию объявляются:

| ID модели | Описание |
|-----------|----------|
| `claude-sonnet-4.6` | Сбалансированная модель (по умолчанию) |
| `claude-opus-4-5` | Топовая модель |
| `claude-haiku-3-5` | Быстрая модель |

Фактический набор поддерживаемых моделей определяется учётной записью и версией `kiro-cli`. Идентификатор модели передаётся `kiro-cli`, который и выполняет выбор.

## 6. Конфигурация

Все настройки читаются из переменных окружения (или файла `.env`, загружаемого в `main.py`). Реальные переменные окружения имеют приоритет над `.env`.

| Переменная | По умолчанию | Назначение |
|------------|--------------|------------|
| `KIRO_GATEWAY_API_KEY` | `test-proxy-key` | Секрет для аутентификации клиентов |
| `KIRO_CLI_PATH` | `kiro-cli` | Путь/имя бинаря Kiro CLI |
| `ACP_TRUST_TOOLS` | `true` | Автоодобрение (`true`) или отклонение (`false`) запросов разрешений на инструменты |
| `ACP_WORKSPACE_DIR` | рабочий каталог процесса | Рабочий каталог сессии по умолчанию (`cwd`) |
| `ACP_TIMEOUT` | `120` | Таймаут ожидания ответа JSON-RPC (секунды) |
| `ACP_ENABLED` | `true` | Включение роутера нативного ACP |
| `OPENAI_SHIM_ENABLED` | `true` | Включение OpenAI-шима |
| `ANTHROPIC_SHIM_ENABLED` | `true` | Включение Anthropic-шима |
| `SERVER_HOST` / `SERVER_PORT` | `0.0.0.0` / `8000` | Адрес и порт прослушивания |
| `COMPLIANCE_MODE` | `true` | Контроль единственной учётной записи |

> **Безопасность.** При `ACP_TRUST_TOOLS=true` агент `kiro-cli` может писать файлы и выполнять команды в каталоге сессии без подтверждения. Для развёртываний «только ответы» (read/answer-only) установите `ACP_TRUST_TOOLS=false` и ограничьте `ACP_WORKSPACE_DIR` каталогом проекта. Вся аутентификация Kiro остаётся внутри `kiro-cli` — шлюз не работает с учётными данными.

### Пример `.env`

```env
KIRO_GATEWAY_API_KEY=change-me
KIRO_CLI_PATH=kiro-cli
ACP_TRUST_TOOLS=true
ACP_WORKSPACE_DIR=
ACP_TIMEOUT=120
ACP_ENABLED=true
OPENAI_SHIM_ENABLED=true
ANTHROPIC_SHIM_ENABLED=true
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
COMPLIANCE_MODE=true
```

## 7. API Endpoints

| Режим | Метод | Эндпоинт | Описание |
|-------|-------|----------|----------|
| Health | GET | `/health` | Проверка состояния (`status`, `mode`, `version`) |
| OpenAI | GET | `/v1/models` | Список моделей |
| OpenAI | POST | `/v1/chat/completions` | Завершения (стрим + non-stream) |
| Anthropic | GET | `/v1/models` | Список моделей |
| Anthropic | POST | `/v1/messages` | Сообщения (стрим + non-stream) |
| ACP | POST | `/acp/chat` | Непотоковый ACP-чат |
| ACP | POST | `/acp/chat/stream` | Потоковый ACP-чат (SSE) |

**Аутентификация:** OpenAI использует `Authorization: Bearer <KIRO_GATEWAY_API_KEY>`; Anthropic — заголовок `x-api-key: <KIRO_GATEWAY_API_KEY>`.

### Карта потоковых событий

| Событие ACP | OpenAI SSE | Anthropic SSE |
|-------------|------------|---------------|
| `text` | чанк `delta.content` | `content_block_delta[text_delta]` |
| `tool_call` | чанк `delta.tool_calls` | `content_block_start[tool_use]` + `input_json_delta` |
| `thinking` | не выводится | не выводится |
| `done` | `finish_reason` + `[DONE]` | `message_delta` + `message_stop` |
| `error` | error-чанк + `[DONE]` | событие `error` |

## 8. Особенности реализации

- **Изоляция сессий на запрос.** Каждый HTTP-запрос открывает свою ACP-сессию (`session/new`), благодаря чему конкурентные запросы не пересекаются. Это и обеспечивает безопасную параллельность при одном подпроцессе `kiro-cli`.
- **Tool-calls внутри одного хода.** Поскольку каждый запрос открывает новую сессию, `kiro-cli` сам выполняет инструменты и продолжает тот же ход, стримя итоговый текст. Активность инструментов транслируется вызывающей стороне для наглядности (`tool_calls` у OpenAI, `tool_use` у Anthropic), но клиент не обязан выполнять их сам.
- **Нормализация причин завершения.** `stopReason` приводится к единому виду внутри шлюза; Anthropic-роут затем отображает его обратно в свой словарь (`end_turn`, `max_tokens`).
- **`thinking` скрыт от прикладных потоков.** Размышления модели не попадают в контент OpenAI/Anthropic и доступны лишь нативным ACP-клиентам.
- **Обработка ошибок.** Ошибки JSON-RPC и аварийный выход подпроцесса транслируются в событие `error`; в роутах внутренние сбои логируются и возвращаются клиенту в виде `HTTPException` (например, `502`).

## 9. Расширяемость

- **Добавление поля/возможности в шимы.** Изменения вносятся в **оба** файла — `routes_openai_shim.py` и `routes_anthropic_shim.py`, причём как в потоковую, так и в непотоковую ветку, с сохранением dict-контракта событий. Покрываются тестами все четыре комбинации (OpenAI/Anthropic × стрим/non-stream).
- **Изменение обработки протокола ACP.** Правится `kiro/acp_client.py`. Формы проверяются на живом `kiro-cli acp` по stdio; «сырые» ACP-структуры не должны просачиваться в роуты — они преобразуются в нормализованные dict-события.
- **Добавление эндпоинта.** Определяются модели запроса/ответа, добавляется роут в соответствующий `routes_*.py`, поток проходит через `ShimService`, добавляются тесты в `tests/unit/test_routes_*`.

Тесты полностью изолированы от сети и **никогда** не запускают реальный бинарь: фикстуры в `tests/conftest.py` мокируют подпроцесс и методы `ACPClient`.

## 10. Зависимости

Основные зависимости проекта:

| Пакет | Назначение |
|-------|------------|
| `fastapi` | Асинхронный веб-фреймворк |
| `uvicorn` | ASGI-сервер |
| `pydantic` | Валидация данных и модели |
| `pydantic-settings` | Настройки из окружения |
| `python-dotenv` | Загрузка переменных окружения из `.env` |
| `loguru` | Логирование |
| `tiktoken` | Подсчёт токенов |

Зависимости для тестирования:

| Пакет | Назначение |
|-------|------------|
| `pytest` | Фреймворк тестирования |
| `pytest-asyncio` | Поддержка асинхронных тестов |
| `pytest-cov` | Покрытие кода |
