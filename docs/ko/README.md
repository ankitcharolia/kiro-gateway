# Kiro Gateway — 문서

**완전한 ACP 준수** 브리지로, OpenAI 또는 Anthropic 호환 AI 도구가 공식 `kiro` CLI 바이너리를 통해 요청을 라우팅하여 단일 Kiro 구독을 사용할 수 있게 해줍니다.

---

## 목차

1. [아키텍처](#아키텍처)
2. [설치](#설치)
3. [설정](#설정)
4. [클라이언트 설정](#클라이언트-설정)
5. [API 엔드포인트](#api-엔드포인트)
6. [도구 호출](#도구-호출)
7. [도구 실행 및 권한](#도구-실행-및-권한)
8. [스트리밍 이벤트](#스트리밍-이벤트)
9. [테스트 실행](#테스트-실행)
10. [릴리스 프로세스](#릴리스-프로세스)

---

## 아키텍처

모든 요청은 stdio를 통한 JSON-RPC 2.0으로 공식 `kiro` CLI를 통과합니다. 비공개 HTTP 엔드포인트 없음, 자격 증명 공유 없음, 계정 풀링 없음.

```
모든 OpenAI / Anthropic 클라이언트
               │
  ┌────────────┴────────────┐
  │                         │
routes_openai_shim    routes_anthropic_shim
 /v1/chat/completions   /v1/messages
               │
         shim_service.py
    (오케스트레이션 + 도구 호출 왕복)
               │
         acp_client.py
     (stdio를 통한 JSON-RPC 2.0)
               │
           kiro CLI
      (공식, 인증됨)
               │
         Kiro 백엔드
```

### 핵심 구성 요소

| 구성 요소 | 파일 | 목적 |
|---|---|---|
| ACP 브리지 | `kiro/acp_client.py` | `kiro` CLI 실행; stdio를 통한 JSON-RPC 2.0 |
| ACP 모델 | `kiro/acp_models.py` | 모든 ACP 유형에 대한 Pydantic 모델 |
| 권한 처리 | `kiro/acp_client.py` | `session/request_permission` 에 응답 (`ACP_TRUST_TOOLS` 에 따라 자동 승인/거부) |
| 오케스트레이션 | `kiro/shim_service.py` | 스트리밍, 도구 호출 왕복, 세션 수명주기 |
| ACP 라우트 | `kiro/routes_acp.py` | `/acp/chat`, `/acp/chat/stream` |
| OpenAI shim | `kiro/routes_openai_shim.py` | `/v1/chat/completions`, `/v1/models` |
| Anthropic shim | `kiro/routes_anthropic_shim.py` | `/v1/messages`, `/v1/models` |
| 컴플라이언스 가드 | `kiro/compliance.py` | 시작 시 단일 계정 강제 |
| 모델 리졸버 | `kiro/model_resolver.py` | 모델 이름을 Kiro 지원 ID에 매핑 |
| 페이로드 가드 | `kiro/payload_guards.py` | 요청 유효성 검사 및 크기 제한 |
| 토크나이저 | `kiro/tokenizer.py` | 잘라내기 결정을 위한 토큰 카운팅 |
| 잘라내기 | `kiro/truncation_state.py` | 대화 기록 잘라내기 |

---

## 설치

### 전제 조건

| 요구사항 | 참고 |
|---|---|
| **Kiro CLI** | [kiro.dev](https://kiro.dev)에서 설치 후 `kiro auth login` 실행 |
| **Python 3.11+** | 베어메탈 경로에만 필요 |
| **Docker** | 컨테이너 경로에만 필요 |

### 옵션 A — 베어메탈

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # PROXY_API_KEY 편집
kiro auth login
python main.py
```

### 옵션 B — Docker (공개 이미지)

```bash
docker pull ghcr.io/ankitcharolia/kiro-gateway:latest
docker run -d \
  --name kiro-gateway \
  -p 8000:8000 \
  -e PROXY_API_KEY=change-me \
  -v "${HOME}/.kiro:/root/.kiro:ro" \
  ghcr.io/ankitcharolia/kiro-gateway:latest
```

### 옵션 C — Docker Compose

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway
cp .env.example .env   # PROXY_API_KEY 편집
docker compose up -d
```

---

## 설정

```env
# 필수
PROXY_API_KEY=change-me

# CLI 경로
KIRO_CLI_PATH=kiro-cli

ACP_TRUST_TOOLS=true        # kiro-cli 가 자체 내장 도구를 실행하며 권한을 요청; true=승인, false=거부
ACP_WORKSPACE_DIR=          # 세션 작업 디렉터리 (기본값: 프로세스 cwd)
ACP_TIMEOUT=120             # JSON-RPC 응답 대기 초

# 기능 플래그
ACP_ENABLED=true
OPENAI_SHIM_ENABLED=true
ANTHROPIC_SHIM_ENABLED=true

# 서버
SERVER_HOST=0.0.0.0
SERVER_PORT=8000

# 컴플라이언스
COMPLIANCE_MODE=true
```

---

## 도구 실행 및 권한

`kiro-cli`는 세션 작업 디렉터리에서 **자체** 내장 도구(파일 편집, 명령 실행)를 직접 실행합니다. 게이트웨이는 클라이언트 측 `fs`/`terminal` 기능을 전혀 광고하지 않으며, 에이전트가 보내는 `session/request_permission` 요청에만 응답합니다 — `ACP_TRUST_TOOLS=true`이면 한 번의 호출을 자동 승인(`allow_once`)하고, 그렇지 않으면 거부(`reject_once`)합니다.

| 에이전트 요청 | 게이트웨이 동작 |
|---|---|
| `session/request_permission` | `ACP_TRUST_TOOLS=true`일 때 단일 호출을 자동 승인(`allow_once`)하고, `false`일 때 거부(`reject_once`)합니다. |

```env
ACP_TRUST_TOOLS=true     # 내장 도구 실행 자동 승인 (파일 편집, 명령)
ACP_TRUST_TOOLS=false    # 응답 전용: 모든 권한 요청 거부
ACP_WORKSPACE_DIR=/path  # kiro-cli 작업 디렉터리 (기본값: 프로세스 cwd)
```

> **보안:** `ACP_TRUST_TOOLS=true`이면 에이전트가 확인 없이 파일을 쓰고 명령을 실행할 수 있습니다. 응답 전용 배포에는 `false`를 사용하세요.

---

## 스트리밍 이벤트

| ACP 이벤트 | OpenAI SSE | Anthropic SSE |
|---|---|---|
| `text` | `delta.content` 청크 | `content_block_delta[text_delta]` |
| `tool_call` | `delta.tool_calls` 청크 | `content_block_start[tool_use]` |
| `thinking` | `delta.content` 청크 | `content_block_delta[text_delta]` |
| `done` | `[DONE]` + `finish_reason` | `message_delta` + `message_stop` |
| `error` | 오류 청크 + `[DONE]` | `error` 이벤트 |

---

## 라이선스

AGPL-3.0 — [LICENSE](../../LICENSE) 참조.
