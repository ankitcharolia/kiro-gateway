# Kiro Gateway — Dokumentasi

Jembatan **yang sepenuhnya mematuhi ACP** yang memungkinkan alat AI kompatibel OpenAI atau Anthropic menggunakan langganan Kiro tunggal Anda — dengan merutekan setiap permintaan melalui biner resmi `kiro` CLI.

---

## Daftar Isi

1. [Arsitektur](#arsitektur)
2. [Instalasi](#instalasi)
3. [Konfigurasi](#konfigurasi)
4. [Pengaturan Klien](#pengaturan-klien)
5. [Endpoint API](#endpoint-api)
6. [Pemanggilan Alat](#pemanggilan-alat)
7. [Sandboxing Filesystem & Terminal](#sandboxing-filesystem--terminal)
8. [Event Streaming](#event-streaming)
9. [Menjalankan Tes](#menjalankan-tes)
10. [Proses Rilis](#proses-rilis)

---

## Arsitektur

Setiap permintaan mengalir melalui CLI resmi `kiro` melalui JSON-RPC 2.0 melalui stdio — tanpa endpoint HTTP privat, tanpa berbagi kredensial, tanpa pooling akun.

```
Klien OpenAI / Anthropic mana pun
               │
  ┌────────────┴────────────┐
  │                         │
routes_openai_shim    routes_anthropic_shim
 /v1/chat/completions   /v1/messages
               │
         shim_service.py
    (orkestrasi + putaran panggilan alat)
               │
         acp_client.py
     (JSON-RPC 2.0 melalui stdio)
               │
           kiro CLI
      (resmi, terotentikasi)
               │
         Backend Kiro
```

### Komponen Inti

| Komponen | File | Tujuan |
|---|---|---|
| Jembatan ACP | `kiro/acp_client.py` | Meluncurkan CLI `kiro`; JSON-RPC 2.0 melalui stdio |
| Model ACP | `kiro/acp_models.py` | Model Pydantic untuk semua tipe ACP |
| Sandbox kemampuan | `kiro/capability_executor.py` | Sandboxing readFile/writeFile/listDirectory/runCommand |
| Orkestrasi | `kiro/shim_service.py` | Streaming, putaran alat, siklus hidup sesi |
| Rute ACP | `kiro/routes_acp.py` | `/acp/chat`, `/acp/chat/stream` |
| Shim OpenAI | `kiro/routes_openai_shim.py` | `/v1/chat/completions`, `/v1/models` |
| Shim Anthropic | `kiro/routes_anthropic_shim.py` | `/v1/messages`, `/v1/models` |
| Penjaga kepatuhan | `kiro/compliance.py` | Penegakan satu akun saat startup |
| Resolver model | `kiro/model_resolver.py` | Memetakan nama model ke ID yang didukung Kiro |
| Penjaga payload | `kiro/payload_guards.py` | Validasi permintaan dan batas ukuran |
| Tokenizer | `kiro/tokenizer.py` | Penghitungan token untuk keputusan pemotongan |
| Pemotongan | `kiro/truncation_state.py` | Pemotongan riwayat percakapan |

---

## Instalasi

### Prasyarat

| Persyaratan | Catatan |
|---|---|
| **Kiro CLI** | Instal dari [kiro.dev](https://kiro.dev), lalu jalankan `kiro auth login` |
| **Python 3.11+** | Hanya diperlukan untuk jalur bare-metal |
| **Docker** | Hanya diperlukan untuk jalur kontainer |

### Opsi A — Bare metal

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit PROXY_API_KEY
kiro auth login
python main.py
```

### Opsi B — Docker (gambar yang diterbitkan)

```bash
docker pull ghcr.io/ankitcharolia/kiro-gateway:latest
docker run -d \
  --name kiro-gateway \
  -p 8000:8000 \
  -e PROXY_API_KEY=change-me \
  -v "${HOME}/.kiro:/root/.kiro:ro" \
  ghcr.io/ankitcharolia/kiro-gateway:latest
```

### Opsi C — Docker Compose

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway
cp .env.example .env   # edit PROXY_API_KEY
docker compose up -d
```

---

## Konfigurasi

```env
# Wajib
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

## Event Streaming

| Event ACP | SSE OpenAI | SSE Anthropic |
|---|---|---|
| `text` | chunk `delta.content` | `content_block_delta[text_delta]` |
| `tool_call` | chunk `delta.tool_calls` | `content_block_start[tool_use]` |
| `thinking` | chunk `delta.content` | `content_block_delta[text_delta]` |
| `done` | `[DONE]` + `finish_reason` | `message_delta` + `message_stop` |
| `error` | chunk error + `[DONE]` | event `error` |

---

## Lisensi

AGPL-3.0 — lihat [LICENSE](../../LICENSE).
