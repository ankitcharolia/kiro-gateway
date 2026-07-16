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
7. [Eksekusi Alat & Izin](#eksekusi-alat--izin)
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
| Penanganan izin | `kiro/acp_client.py` | Menjawab `session/request_permission` (setujui otomatis atau tolak via `ACP_TRUST_TOOLS`) |
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
| **Python 3.14+** | Hanya diperlukan untuk jalur bare-metal |
| **Docker** | Hanya diperlukan untuk jalur kontainer |

### Opsi A — Bare metal

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway
uv sync
cp .env.example .env   # edit KIRO_GATEWAY_API_KEY
kiro auth login
uv run main.py
```

### Opsi B — Docker (gambar yang diterbitkan)

```bash
docker pull ghcr.io/ankitcharolia/kiro-gateway:latest
docker run -d \
  --name kiro-gateway \
  -p 8000:8000 \
  -e KIRO_GATEWAY_API_KEY=change-me \
  -v "${HOME}/.kiro:/root/.kiro:ro" \
  ghcr.io/ankitcharolia/kiro-gateway:latest
```

### Opsi C — Docker Compose

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway
cp .env.example .env   # edit KIRO_GATEWAY_API_KEY
docker compose up -d
```

---

## Konfigurasi

```env
# Wajib
KIRO_GATEWAY_API_KEY=change-me

KIRO_CLI_PATH=kiro-cli
ACP_TRUST_TOOLS=true        # kiro-cli menjalankan alatnya sendiri dan meminta izin; true = setujui, false = tolak
ACP_WORKSPACE_DIR=          # Direktori kerja sesi (default: cwd proses)
ACP_TIMEOUT=120             # Detik menunggu respons JSON-RPC
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
COMPLIANCE_MODE=true
```

---

## Eksekusi Alat & Izin

`kiro-cli` menyediakan alat bawaannya **sendiri** (baca/edit file, eksekusi
perintah, pencarian) dan menjalankannya sendiri di dalam direktori kerja sesi.
Gateway **tidak** mengiklankan kemampuan filesystem atau terminal sisi klien,
sehingga tidak pernah menjalankan alat atas nama agen — ia hanya menjawab
permintaan izin yang dikirim balik oleh agen.

| Permintaan agen | Perilaku gateway |
|---|---|
| `session/request_permission` | Menyetujui otomatis satu pemanggilan (`allow_once`) saat `ACP_TRUST_TOOLS=true`; menolak (`reject_once`) saat `false`. |

```env
ACP_TRUST_TOOLS=true     # setujui otomatis eksekusi alat bawaan (edit file, perintah)
ACP_TRUST_TOOLS=false    # hanya-jawab: setiap permintaan izin alat ditolak
ACP_WORKSPACE_DIR=/path  # direktori kerja tempat kiro-cli beroperasi (default: cwd proses)
```

Sebuah permintaan juga dapat menyertakan `filesystem_roots`; path root pertama
menjadi `cwd` untuk `session/new`.

> **Keamanan:** dengan `ACP_TRUST_TOOLS=true` agen dapat menulis file dan
> menjalankan perintah di direktori kerja tanpa konfirmasi manusia. Gunakan
> `false` untuk deployment hanya-baca/hanya-jawab.

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

## Dukungan

Jika proyek ini menghemat waktu Anda, pertimbangkan untuk mendukung pengembangannya:

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/achar)
[![PayPal](https://img.shields.io/badge/Donate-PayPal-blue.svg)](https://paypal.me/ankitcharolia)

---

## Lisensi

AGPL-3.0 — lihat [LICENSE](../../LICENSE).
