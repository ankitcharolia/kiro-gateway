# -*- coding: utf-8 -*-
"""
Multimodal content normalization for the OpenAI and Anthropic shims (issue #33).

Capability ground truth — verified against a **live kiro-cli 2.10.0 ACP probe**
(``initialize`` → ``agentCapabilities.promptCapabilities``)::

    {"image": true, "audio": false, "embeddedContext": false}

So the gateway:

* **Images — forwarded.** OpenAI ``image_url`` / Responses ``input_image`` and
  Anthropic ``image`` blocks are translated into ACP image content blocks
  (``{"type": "image", "mimeType": "<mime>", "data": "<base64>"}``) and included
  in ``session/prompt``. The shape was confirmed end-to-end against the live
  probe: a forwarded 32×32 PNG made the model answer with the image's colour.
  Only base64 data URLs are forwarded; a **remote URL is not fetched** (kiro-cli
  has no URL content-block capability, and fetching untrusted URLs server-side
  is an SSRF/egress risk) — it is surfaced as text instead.
* **Documents — extracted when text, else placeholder.** kiro-cli rejects
  embedded resources (``embeddedContext: false``), so documents are never
  forwarded as binary. Text-like documents (``text/*``, JSON, XML, CSV, …) are
  **decoded and injected as text** so the model actually reads them. PDFs are
  extracted with ``pypdf`` (a standard dependency); a scanned/image-only PDF
  that yields no text, or any other binary format, falls back to an explicit
  ``[document: … omitted]`` placeholder — never a silent drop.
* **Audio — placeholder.** Not supported by kiro-cli; surfaced as a placeholder.

Normalized internal blocks (carried in :class:`~kiro.acp_models.PromptMessage`
content and consumed by :meth:`ACPClient._build_prompt_blocks`)::

    {"type": "text",  "text": "<str>"}
    {"type": "image", "mimeType": "<mime>", "data": "<base64>"}
"""
from __future__ import annotations

import base64
import binascii
import json
from typing import Any, Optional

from loguru import logger

# Mime types (and prefixes) treated as plain text → decoded and injected.
_TEXT_MIME_PREFIXES = ("text/",)
_TEXT_MIME_EXACT = {
    "application/json",
    "application/xml",
    "application/x-yaml",
    "application/yaml",
    "application/csv",
    "application/x-ndjson",
    "application/javascript",
    "application/x-sh",
    "application/sql",
}
# Cap injected document text so a huge attachment cannot blow up the prompt.
_MAX_DOC_TEXT_CHARS = 200_000


def _text_block(text: str) -> dict:
    """Build a normalized text block."""
    return {"type": "text", "text": text}


def _image_block(mime: str, data: str) -> dict:
    """Build a normalized image block (ACP wire shape)."""
    return {"type": "image", "mimeType": mime or "image/png", "data": data}


def parse_data_url(url: str) -> Optional[tuple[str, str]]:
    """Parse a base64 ``data:`` URL into ``(mime, base64_data)``.

    Only base64-encoded data URLs are recognised (the form harnesses use for
    inline attachments, e.g. ``data:image/png;base64,iVBOR…``).

    Args:
        url: A candidate URL string.

    Returns:
        ``(mime, base64_data)`` when *url* is a base64 data URL, else ``None``.
    """
    if not isinstance(url, str) or not url.startswith("data:"):
        return None
    try:
        header, data = url.split(",", 1)
    except ValueError:
        return None
    meta = header[len("data:"):]
    if ";base64" not in meta:
        return None
    mime = meta.split(";", 1)[0].strip() or "application/octet-stream"
    data = data.strip()
    if not data:
        return None
    return mime, data


def _is_text_mime(mime: Optional[str]) -> bool:
    """Return ``True`` when *mime* denotes a text-like (decodable) document."""
    if not mime:
        return False
    mime = mime.split(";", 1)[0].strip().lower()
    return mime.startswith(_TEXT_MIME_PREFIXES) or mime in _TEXT_MIME_EXACT


def _decode_base64(data: str) -> Optional[bytes]:
    """Decode base64 *data*, returning bytes or ``None`` on failure."""
    try:
        return base64.b64decode(data, validate=False)
    except (binascii.Error, ValueError):
        return None


def _extract_pdf_text(raw: bytes) -> Optional[str]:
    """Extract text from PDF bytes using ``pypdf``.

    ``pypdf`` is a standard dependency (see ``pyproject.toml`` /
    ``requirements.txt``), so PDF text extraction works out of the box. Returns
    the extracted text, or ``None`` when the PDF yields no extractable text
    (e.g. a scanned/image-only PDF) or fails to parse — the caller then falls
    back to an explicit placeholder. The import is kept lazy so a broken/absent
    install degrades gracefully rather than breaking unrelated image handling.
    """
    try:
        import pypdf
    except ImportError:  # pragma: no cover - pypdf is a declared dependency
        logger.warning("pypdf not importable; PDF text extraction unavailable")
        return None
    try:
        import io

        reader = pypdf.PdfReader(io.BytesIO(raw))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(p for p in pages if p).strip()
        return text or None
    except Exception as exc:  # noqa: BLE001 - any pypdf parse error → placeholder
        logger.debug(f"pypdf extraction failed: {exc}")
        return None


def _document_block(
    *,
    mime: Optional[str],
    data: Optional[str],
    name: Optional[str] = None,
    raw_text: Optional[str] = None,
) -> dict:
    """Render a document attachment as a text block (extracted or placeholder).

    Resolution order:

    1. ``raw_text`` provided directly (e.g. Anthropic ``text`` document source)
       → injected verbatim.
    2. Text-like mime → base64-decode to UTF-8 and inject the content.
    3. PDF → extract text via ``pypdf`` (placeholder if it yields no text or
       fails to parse).
    4. Anything else → explicit ``[document: … omitted]`` placeholder.

    kiro-cli cannot ingest embedded documents (``embeddedContext: false``), so
    the content always travels as text; this surfaces it instead of silently
    dropping it.

    Args:
        mime: The document media type, if known.
        data: Base64-encoded document bytes, if present.
        name: A display name (filename / title) for the placeholder.
        raw_text: Already-decoded document text, if the source provided it.

    Returns:
        A normalized text block — extracted content (labelled) or a placeholder.
    """
    label = name or (mime or "attachment")

    if raw_text:
        return _text_block(_labelled_document(label, raw_text))

    if data:
        raw = _decode_base64(data)
        if raw is not None:
            if _is_text_mime(mime):
                try:
                    text = raw.decode("utf-8")
                    return _text_block(_labelled_document(label, text))
                except UnicodeDecodeError:
                    logger.debug(f"document {label!r} not valid UTF-8; placeholder")
            elif (mime or "").lower().startswith("application/pdf"):
                extracted = _extract_pdf_text(raw)
                if extracted:
                    return _text_block(_labelled_document(label, extracted))

    return _text_block(f"[document: {label} omitted — unsupported by kiro-cli]")


def _labelled_document(label: str, text: str) -> str:
    """Wrap extracted document text with a clear, bounded label."""
    if len(text) > _MAX_DOC_TEXT_CHARS:
        text = text[:_MAX_DOC_TEXT_CHARS] + "\n…[document truncated]"
    return f"[document: {label}]\n{text}"


def _remote_image_text(url: str) -> str:
    """Placeholder text for a remote (non-data-URL) image reference."""
    url = url or ""
    return (
        f"[image: {url} (remote URL not fetched — send a base64 data URL "
        "to forward the image)]"
    )


# ---------------------------------------------------------------------------
# OpenAI content parts
# ---------------------------------------------------------------------------

def openai_part_to_blocks(part: Any) -> list[dict]:
    """Normalize one OpenAI content part into internal blocks.

    Handles chat ``image_url`` and Responses ``input_image`` / ``input_file`` /
    ``input_audio`` shapes plus plain text. Unsupported attachments become an
    explicit text placeholder (or extracted text for documents) rather than
    being silently dropped.

    Args:
        part: One element of an OpenAI message ``content`` list.

    Returns:
        A list of normalized blocks (usually one).
    """
    if not isinstance(part, dict):
        return [_text_block(str(part))]

    ptype = part.get("type")

    if ptype in ("text", "input_text", "output_text"):
        return [_text_block(part.get("text", ""))]

    if ptype in ("image_url", "input_image"):
        url = part.get("image_url")
        if isinstance(url, dict):
            url = url.get("url")
        if not url:
            url = part.get("url")
        if isinstance(url, str) and url:
            parsed = parse_data_url(url)
            if parsed:
                return [_image_block(parsed[0], parsed[1])]
            return [_text_block(_remote_image_text(url))]
        return [_text_block("[image omitted — no source provided]")]

    if ptype in ("input_file", "file", "document"):
        f = part.get("file") if isinstance(part.get("file"), dict) else {}
        name = f.get("filename") or part.get("filename") or f.get("file_id") or part.get("file_id")
        file_data = part.get("file_data") or f.get("file_data")
        mime, data = None, None
        if isinstance(file_data, str):
            parsed = parse_data_url(file_data)
            if parsed:
                mime, data = parsed
            else:
                # Raw (non-data-URL) base64 string.
                data = file_data
        return [_document_block(mime=mime, data=data, name=name)]

    if ptype in ("input_audio", "audio"):
        return [_text_block("[audio omitted — unsupported by kiro-cli]")]

    if ptype == "tool_result":
        return [_text_block(str(part.get("content", "")))]

    text = part.get("text")
    return [_text_block(text)] if text else []


# ---------------------------------------------------------------------------
# Anthropic content blocks
# ---------------------------------------------------------------------------

def anthropic_block_to_blocks(block: Any) -> list[dict]:
    """Normalize one Anthropic content block into internal blocks.

    Handles ``text`` / ``image`` / ``document`` plus ``tool_use`` / ``tool_result``
    (rendered as the same markers the OpenAI shim uses, so the serialised
    transcript is consistent across APIs — issue #43). Images with a base64
    source are forwarded; ``url`` sources and documents are surfaced as text.

    Args:
        block: One element of an Anthropic message ``content`` list.

    Returns:
        A list of normalized blocks (usually one).
    """
    if not isinstance(block, dict):
        return [_text_block(str(block))]

    btype = block.get("type")

    if btype == "text":
        return [_text_block(block.get("text", ""))]

    if btype == "image":
        src = block.get("source") or {}
        stype = src.get("type")
        if stype == "base64" and src.get("data"):
            return [_image_block(src.get("media_type") or "image/png", src["data"])]
        if stype == "url":
            return [_text_block(_remote_image_text(src.get("url") or ""))]
        return [_text_block("[image omitted — unsupported source]")]

    if btype == "document":
        src = block.get("source") or {}
        name = block.get("title") or block.get("name")
        stype = src.get("type")
        if stype == "text":
            return [_document_block(mime="text/plain", data=None, name=name,
                                    raw_text=src.get("data") or "")]
        if stype == "base64":
            return [_document_block(mime=src.get("media_type"), data=src.get("data"), name=name)]
        if stype == "url":
            return [_text_block(
                f"[document: {src.get('url') or name or 'attachment'} "
                "(remote URL not fetched) — unsupported by kiro-cli]"
            )]
        return [_document_block(mime=src.get("media_type"), data=None, name=name)]

    if btype == "tool_use":
        return [_text_block(
            f"[tool_use id={block.get('id')} name={block.get('name')}]\n"
            f"{json.dumps(block.get('input', {}))}"
        )]

    if btype == "tool_result":
        content = block.get("content", "")
        if isinstance(content, list):
            content = "\n".join(
                p.get("text", "") for p in content if isinstance(p, dict)
            )
        return [_text_block(f"[tool_result id={block.get('tool_use_id')}]\n{content}")]

    text = block.get("text")
    return [_text_block(text)] if text else []


# ---------------------------------------------------------------------------
# Collapse / merge helpers
# ---------------------------------------------------------------------------

def collapse_blocks(blocks: list[dict]) -> Any:
    """Collapse normalized blocks to a ``str`` (no images) or a block ``list``.

    When no image is present the blocks are joined into a single newline-
    separated string (the common, text-only case — keeps existing behaviour and
    the labelled-transcript serialisation simple). When at least one image block
    is present, the list is returned so :meth:`ACPClient._build_prompt_blocks`
    can emit the images as separate ACP content blocks.

    Args:
        blocks: Normalized text/image blocks.

    Returns:
        ``str`` for text-only content, else the ``list[dict]`` of blocks.
    """
    if not blocks:
        return ""
    if any(b.get("type") == "image" for b in blocks):
        return blocks
    texts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
    return "\n".join(t for t in texts if t)


def append_text(content: Any, text: str) -> Any:
    """Append *text* to a content value that may be a ``str`` or block ``list``.

    Used by the shims to attach tool-call markers to a turn whose content might
    already carry image blocks.

    Args:
        content: The current message content (``str`` or block ``list``).
        text: The text to append (ignored when empty).

    Returns:
        The updated content (same type as the input where possible).
    """
    if not text:
        return content
    if isinstance(content, list):
        return content + [_text_block(text)]
    if content:
        return f"{content}\n{text}"
    return text


def prepend_text(content: Any, text: str) -> Any:
    """Prepend *text* to a content value that may be a ``str`` or block ``list``.

    Args:
        content: The current message content (``str`` or block ``list``).
        text: The text to prepend (ignored when empty).

    Returns:
        The updated content.
    """
    if not text:
        return content
    if isinstance(content, list):
        return [_text_block(text)] + content
    if content:
        return f"{text}\n{content}"
    return text
