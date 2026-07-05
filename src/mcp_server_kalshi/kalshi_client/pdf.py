import io
from typing import Any

import httpx
from pypdf import PdfReader


async def fetch_pdf_text(url: str, max_chars: int = 40000) -> dict[str, Any]:
    """Download a public PDF (e.g. a Kalshi contract-terms / certification doc) and
    extract its text.

    Kalshi hosts rules PDFs on public S3 (``kalshi-public-docs.s3...``), so no auth is
    needed. Returns the extracted text plus metadata; text is truncated to ``max_chars``
    with a flag so callers/agents know to page further if needed.
    """
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.content

    reader = PdfReader(io.BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    full_text = "\n\n".join(pages).strip()
    truncated = len(full_text) > max_chars

    return {
        "url": url,
        "page_count": len(reader.pages),
        "char_count": len(full_text),
        "truncated": truncated,
        "text": full_text[:max_chars],
    }
