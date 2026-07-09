"""Tests for fetch_pdf_text: download + extract + truncation, without network or real PDFs.

The httpx download and pypdf reader are both stubbed so extracted text is deterministic.
"""

import httpx
import pytest

from mcp_server_kalshi.kalshi_client import pdf


class _FakeResponse:
    def __init__(self, status_code: int, content: bytes):
        self.status_code = status_code
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=httpx.Request("GET", "http://x"), response=None  # type: ignore[arg-type]
            )


class _FakeAsyncClient:
    """Async-context-manager stand-in for httpx.AsyncClient with a canned GET response."""

    response = _FakeResponse(200, b"%PDF-bytes")

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url):
        return self.response


class _FakePage:
    def __init__(self, text: str):
        self._text = text

    def extract_text(self) -> str:
        return self._text


class _FakeReader:
    pages_text = ["A" * 50, "B" * 50]

    def __init__(self, stream):
        self.pages = [_FakePage(t) for t in self.pages_text]


@pytest.fixture
def stub_pdf(monkeypatch):
    """Patch the download client and the PDF reader; return a knob to set the HTTP status."""
    monkeypatch.setattr(pdf.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(pdf, "PdfReader", _FakeReader)

    def set_status(code: int):
        _FakeAsyncClient.response = _FakeResponse(code, b"%PDF-bytes")

    set_status(200)
    yield set_status
    _FakeAsyncClient.response = _FakeResponse(200, b"%PDF-bytes")


async def test_extracts_text_and_metadata(stub_pdf):
    result = await pdf.fetch_pdf_text("https://docs/x.pdf", max_chars=1000)

    assert result["url"] == "https://docs/x.pdf"
    assert result["page_count"] == 2
    assert result["char_count"] == 102  # 50 + "\n\n" + 50
    assert result["truncated"] is False
    assert result["text"] == "A" * 50 + "\n\n" + "B" * 50


async def test_truncates_to_max_chars_and_flags_it(stub_pdf):
    result = await pdf.fetch_pdf_text("https://docs/x.pdf", max_chars=10)

    assert result["truncated"] is True
    assert result["text"] == "A" * 10  # sliced to max_chars
    assert result["char_count"] == 102  # full length still reported


async def test_raises_on_http_error(stub_pdf):
    stub_pdf(404)
    with pytest.raises(httpx.HTTPStatusError):
        await pdf.fetch_pdf_text("https://docs/missing.pdf")
