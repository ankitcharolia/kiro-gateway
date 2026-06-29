"""
Unit tests for kiro.multimodal — multimodal content normalization (issue #33).

Images are forwarded as ACP image blocks; text documents are extracted;
PDF/binary docs and audio become explicit placeholders (never silently dropped).
"""
from __future__ import annotations

import base64

import pytest

from kiro.multimodal import (
    anthropic_block_to_blocks,
    append_text,
    collapse_blocks,
    openai_part_to_blocks,
    parse_data_url,
    prepend_text,
)

PNG_DATA = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
PNG_URL = f"data:image/png;base64,{PNG_DATA}"
HELLO_B64 = base64.b64encode(b"hello world").decode()


# ---------------------------------------------------------------------------
# parse_data_url
# ---------------------------------------------------------------------------

class TestParseDataUrl:
    def test_valid_base64_data_url(self):
        assert parse_data_url(PNG_URL) == ("image/png", PNG_DATA)

    def test_default_mime_when_absent(self):
        assert parse_data_url("data:;base64,QQ==") == ("application/octet-stream", "QQ==")

    def test_non_data_url_returns_none(self):
        assert parse_data_url("https://example.com/x.png") is None

    def test_non_base64_data_url_returns_none(self):
        assert parse_data_url("data:text/plain,hello") is None

    def test_empty_payload_returns_none(self):
        assert parse_data_url("data:image/png;base64,") is None

    def test_non_string_returns_none(self):
        assert parse_data_url(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# OpenAI parts
# ---------------------------------------------------------------------------

class TestOpenAIParts:
    def test_text_part(self):
        assert openai_part_to_blocks({"type": "text", "text": "hi"}) == [
            {"type": "text", "text": "hi"}
        ]

    def test_image_url_data_url_forwarded(self):
        blocks = openai_part_to_blocks(
            {"type": "image_url", "image_url": {"url": PNG_URL}}
        )
        assert blocks == [{"type": "image", "mimeType": "image/png", "data": PNG_DATA}]

    def test_input_image_data_url_forwarded(self):
        blocks = openai_part_to_blocks({"type": "input_image", "image_url": PNG_URL})
        assert blocks == [{"type": "image", "mimeType": "image/png", "data": PNG_DATA}]

    def test_remote_image_url_becomes_placeholder(self):
        blocks = openai_part_to_blocks(
            {"type": "image_url", "image_url": {"url": "https://example.com/cat.png"}}
        )
        assert len(blocks) == 1 and blocks[0]["type"] == "text"
        assert "https://example.com/cat.png" in blocks[0]["text"]
        assert "remote URL not fetched" in blocks[0]["text"]

    def test_text_document_is_extracted(self):
        blocks = openai_part_to_blocks({
            "type": "input_file",
            "filename": "notes.txt",
            "file_data": f"data:text/plain;base64,{HELLO_B64}",
        })
        assert blocks[0]["type"] == "text"
        assert "[document: notes.txt]" in blocks[0]["text"]
        assert "hello world" in blocks[0]["text"]

    def test_binary_document_without_pypdf_is_placeholder(self):
        blocks = openai_part_to_blocks({
            "type": "input_file",
            "filename": "report.pdf",
            "file_data": f"data:application/pdf;base64,{HELLO_B64}",
        })
        assert blocks[0]["type"] == "text"
        assert "[document: report.pdf omitted" in blocks[0]["text"]

    def test_audio_is_placeholder(self):
        blocks = openai_part_to_blocks({"type": "input_audio", "input_audio": {"data": "x"}})
        assert blocks == [{"type": "text", "text": "[audio omitted — unsupported by kiro-cli]"}]

    def test_image_url_no_source_placeholder(self):
        blocks = openai_part_to_blocks({"type": "image_url", "image_url": {}})
        assert blocks[0]["type"] == "text"
        assert "no source" in blocks[0]["text"]


# ---------------------------------------------------------------------------
# Anthropic blocks
# ---------------------------------------------------------------------------

class TestAnthropicBlocks:
    def test_text_block(self):
        assert anthropic_block_to_blocks({"type": "text", "text": "hi"}) == [
            {"type": "text", "text": "hi"}
        ]

    def test_image_base64_forwarded(self):
        blocks = anthropic_block_to_blocks({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": PNG_DATA},
        })
        assert blocks == [{"type": "image", "mimeType": "image/jpeg", "data": PNG_DATA}]

    def test_image_url_source_placeholder(self):
        blocks = anthropic_block_to_blocks({
            "type": "image", "source": {"type": "url", "url": "https://x/y.png"},
        })
        assert blocks[0]["type"] == "text"
        assert "https://x/y.png" in blocks[0]["text"]

    def test_document_text_source_extracted(self):
        blocks = anthropic_block_to_blocks({
            "type": "document", "title": "spec.md",
            "source": {"type": "text", "media_type": "text/markdown", "data": "# Title\nbody"},
        })
        assert blocks[0]["type"] == "text"
        assert "[document: spec.md]" in blocks[0]["text"]
        assert "# Title" in blocks[0]["text"]

    def test_document_base64_text_extracted(self):
        blocks = anthropic_block_to_blocks({
            "type": "document", "title": "data.csv",
            "source": {"type": "base64", "media_type": "text/csv", "data": HELLO_B64},
        })
        assert "[document: data.csv]" in blocks[0]["text"]
        assert "hello world" in blocks[0]["text"]

    def test_document_binary_placeholder(self):
        blocks = anthropic_block_to_blocks({
            "type": "document", "title": "scan.pdf",
            "source": {"type": "base64", "media_type": "application/pdf", "data": HELLO_B64},
        })
        assert "[document: scan.pdf omitted" in blocks[0]["text"]

    def test_tool_use_marker(self):
        blocks = anthropic_block_to_blocks({
            "type": "tool_use", "id": "t1", "name": "get_weather", "input": {"city": "B"},
        })
        assert "[tool_use id=t1 name=get_weather]" in blocks[0]["text"]
        assert '"city": "B"' in blocks[0]["text"]

    def test_tool_result_marker(self):
        blocks = anthropic_block_to_blocks({
            "type": "tool_result", "tool_use_id": "t1",
            "content": [{"type": "text", "text": "sunny"}],
        })
        assert "[tool_result id=t1]" in blocks[0]["text"]
        assert "sunny" in blocks[0]["text"]


# ---------------------------------------------------------------------------
# PDF extraction (optional pypdf) — success path via a fake extractor
# ---------------------------------------------------------------------------

class TestPdfExtraction:
    @staticmethod
    def _make_pdf(text: str) -> bytes:
        """Build a minimal but valid single-page PDF containing *text*."""
        objs = [
            b"<</Type/Catalog/Pages 2 0 R>>",
            b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
            b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 200]/Contents 4 0 R"
            b"/Resources<</Font<</F1 5 0 R>>>>>>",
        ]
        stream = b"BT /F1 24 Tf 40 100 Td (" + text.encode() + b") Tj ET"
        objs.append(b"<</Length %d>>stream\n" % len(stream) + stream + b"\nendstream")
        objs.append(b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>")
        out = b"%PDF-1.4\n"
        offsets = []
        for i, body in enumerate(objs, start=1):
            offsets.append(len(out))
            out += b"%d 0 obj" % i + body + b"endobj\n"
        xref_pos = len(out)
        n = len(objs) + 1
        out += b"xref\n0 %d\n0000000000 65535 f \n" % n
        for off in offsets:
            out += b"%010d 00000 n \n" % off
        out += b"trailer<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF" % (n, xref_pos)
        return out

    def test_real_pdf_text_is_extracted(self):
        """A real PDF is parsed by pypdf and its text injected (no mocking)."""
        pdf_b64 = base64.b64encode(self._make_pdf("Invoice total 42 EUR")).decode()
        blocks = openai_part_to_blocks({
            "type": "input_file", "filename": "invoice.pdf",
            "file_data": f"data:application/pdf;base64,{pdf_b64}",
        })
        assert blocks[0]["type"] == "text"
        assert "[document: invoice.pdf]" in blocks[0]["text"]
        assert "Invoice total 42 EUR" in blocks[0]["text"]

    def test_invalid_pdf_bytes_degrade_to_placeholder(self):
        """Non-PDF bytes labelled as PDF parse-fail gracefully → placeholder."""
        bad = base64.b64encode(b"not a real pdf").decode()
        blocks = openai_part_to_blocks({
            "type": "input_file", "filename": "broken.pdf",
            "file_data": f"data:application/pdf;base64,{bad}",
        })
        assert "[document: broken.pdf omitted" in blocks[0]["text"]

    def test_pdf_extracted_when_available(self, monkeypatch):
        import kiro.multimodal as mm

        monkeypatch.setattr(mm, "_extract_pdf_text", lambda raw: "EXTRACTED PDF TEXT")
        blocks = mm.openai_part_to_blocks({
            "type": "input_file", "filename": "r.pdf",
            "file_data": f"data:application/pdf;base64,{HELLO_B64}",
        })
        assert "[document: r.pdf]" in blocks[0]["text"]
        assert "EXTRACTED PDF TEXT" in blocks[0]["text"]

    def test_pdf_placeholder_when_extraction_returns_none(self, monkeypatch):
        import kiro.multimodal as mm

        monkeypatch.setattr(mm, "_extract_pdf_text", lambda raw: None)
        blocks = mm.openai_part_to_blocks({
            "type": "input_file", "filename": "r.pdf",
            "file_data": f"data:application/pdf;base64,{HELLO_B64}",
        })
        assert "[document: r.pdf omitted" in blocks[0]["text"]


# ---------------------------------------------------------------------------
# collapse_blocks / append_text / prepend_text
# ---------------------------------------------------------------------------

class TestCollapseAndAppend:
    def test_collapse_text_only_to_string(self):
        blocks = [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
        assert collapse_blocks(blocks) == "a\nb"

    def test_collapse_keeps_list_when_image_present(self):
        blocks = [
            {"type": "text", "text": "look"},
            {"type": "image", "mimeType": "image/png", "data": PNG_DATA},
        ]
        assert collapse_blocks(blocks) == blocks

    def test_collapse_empty(self):
        assert collapse_blocks([]) == ""

    def test_append_text_to_string(self):
        assert append_text("a", "b") == "a\nb"

    def test_append_text_to_empty(self):
        assert append_text("", "b") == "b"

    def test_append_text_to_list_adds_block(self):
        content = [{"type": "image", "mimeType": "image/png", "data": PNG_DATA}]
        out = append_text(content, "note")
        assert out[-1] == {"type": "text", "text": "note"}
        assert len(out) == 2

    def test_append_empty_is_noop(self):
        assert append_text("a", "") == "a"

    def test_prepend_text_to_string(self):
        assert prepend_text("a", "marker") == "marker\na"

    def test_prepend_text_to_list(self):
        content = [{"type": "image", "mimeType": "image/png", "data": PNG_DATA}]
        out = prepend_text(content, "marker")
        assert out[0] == {"type": "text", "text": "marker"}
