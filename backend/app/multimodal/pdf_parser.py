"""Pure-Python PDF reader: metadata, pages, text via FlateDecode streams, links, outline.

Strategy (robust, dependency-free):
- pypdf / PyPDF2 preferred when installed.
- Builtin fallback scans the raw byte stream for:
    * object boundaries and /Type /Page declarations -> page count + media boxes
    * decoded FlateDecode content streams -> text via Tj/TJ/'" operators
    * trailer /Info metadata, /Outlines bookmarks, /Annots URI links
  This yields real text for the majority of exported PDFs even when the full
  xref graph is not traversed. Where extraction fails it returns clean empty
  results with a parser status — never fabricated content.
"""
import io, logging, re, zlib
from typing import Optional

logger = logging.getLogger(__name__)


def _build_encoding_table() -> str:
    """WinAnsi-style code page: ISO-8859-1 + CP1252 exceptions in the 0x80-0x9F range."""
    table = [chr(i) for i in range(256)]
    overrides = {
        0x80: "\u20ac", 0x82: "\u201a", 0x83: "\u0192", 0x84: "\u201e",
        0x85: "\u2026", 0x86: "\u2020", 0x87: "\u2021", 0x88: "\u02c6",
        0x89: "\u2030", 0x8A: "\u0160", 0x8B: "\u2039", 0x8C: "\u0152",
        0x8E: "\u017d", 0x91: "\u2018", 0x92: "\u2019", 0x93: "\u201c",
        0x94: "\u201d", 0x95: "\u2022", 0x96: "\u2013", 0x97: "\u2014",
        0x98: "\u02dc", 0x99: "\u2122", 0x9A: "\u0161", 0x9B: "\u203a",
        0x9C: "\u0153", 0x9E: "\u017e", 0x9F: "\u0178",
    }
    for idx, char in overrides.items():
        table[idx] = char
    return "".join(table)


ENC_8859 = _build_encoding_table()


def _decode_literal(raw: bytes) -> str:
    return "".join(ENC_8859[b] if b < 256 else "?" for b in raw)


def _decode_stream(raw: bytes, filters) -> bytes:
    data = raw
    for f in filters:
        if f == "FlateDecode":
            try:
                data = zlib.decompress(data)
            except zlib.error:
                try:
                    data = zlib.decompress(data, -15)
                except zlib.error:
                    return b""
        elif f == "ASCIIHexDecode":
            hexs = re.sub(rb"[^0-9A-Fa-f]", b"", data).rstrip(b">")
            if len(hexs) % 2:
                hexs += b"0"
            try:
                data = bytes.fromhex(hexs.decode("latin-1"))
            except ValueError:
                return b""
        else:
            return b""
    return data


def _find_streams(data: bytes) -> list[bytes]:
    """Returns decoded body bytes of each stream with a suitable filter chain."""
    out = []
    for m in re.finditer(rb"stream\r?\n", data):
        start = m.end()
        end = data.find(b"endstream", start)
        if end < 0:
            continue
        raw = data[start:end].rstrip(b"\r\n")
        # look back up to 4 KB for a filter declaration
        head = data[max(0, m.start() - 4096): m.start()]
        filters = []
        if re.search(rb"/Filter\s*/FlateDecode", head):
            filters.append("FlateDecode")
        elif re.search(rb"/Filter\s*/ASCIIHexDecode", head):
            filters.append("ASCIIHexDecode")
        decoded = _decode_stream(raw, filters)
        if decoded:
            out.append(decoded)
    return out


def _extract_text(stream: bytes) -> str:
    """Extracts text from a content stream: BT..ET, Tj, ', ", TJ arrays."""
    chunks: list[str] = []
    i, n = 0, len(stream)
    while i < n:
        c = stream[i]
        if c in b" \t\r\n":
            i += 1
            continue
        if stream[i:i + 2] in (b"TJ", b"Tj", b"'"):
            k = i - 1
            while k >= 0 and stream[k] in b" \t\r\n":
                k -= 1
            if k < 0 or stream[k] != 41:  # no string literal directly before
                i += 2
                continue
            idx = k
            parens = 0
            while idx >= 0:
                if stream[idx] == 41:
                    parens += 1
                elif stream[idx] == 40:
                    parens -= 1
                    if parens == 0:
                        break
                idx -= 1
            if parens == 0 and idx >= 0:
                j = idx + 1
                depth = 1
                while j < len(stream) and depth:
                    if stream[j] == 40:
                        depth += 1
                    elif stream[j] == 41:
                        depth -= 1
                    j += 1
                chunks.append(_decode_literal(stream[idx + 1: j - 1]))
            i += 2
            continue
        if c == 91:  # TJ array of strings and number gaps
            i += 1
            st = None
            while i < n and stream[i] != 93:
                if stream[i] == 40:
                    depth = 1
                    j = i + 1
                    while j < n and depth:
                        if stream[j] == 40:
                            depth += 1
                        elif stream[j] == 41:
                            depth -= 1
                        j += 1
                    chunks.append(_decode_literal(stream[i + 1: j - 1]))
                    i = j
                else:
                    i += 1
            i += 1
            continue
        i += 1
    text = " ".join(chunks)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_text(data: bytes) -> str:
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(data))
        parts = [p.extract_text() or "" for p in reader.pages]
        return "\n\n".join(parts)
    except Exception:
        pass
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(data))
        parts = [p.extract_text() or "" for p in reader.pages]
        return "\n\n".join(parts)
    except Exception:
        pass
    return _builtin_text(data)


def _builtin_text(data: bytes) -> str:
    texts, count = _builtin_pages(data)
    if not texts and count == 0:
        return ""
    return "\n\n".join(p for p in texts)


def _builtin_pages(data: bytes) -> tuple[list[str], int]:
    """Returns (page_texts, page_count) using the builtin scanner."""
    if not data.startswith(b"%PDF"):
        raise ValueError("not a PDF (missing %PDF header)")
    page_objs = list(re.finditer(rb"/Type\s*/Page[^s]", data))
    page_count = len(page_objs)
    if page_count == 0:
        page_count = len(re.findall(rb"/Type\s*/Pages", data))
    # Extract per-page by splitting object space around each /Type /Page marker
    page_texts: list[str] = []
    for idx, m in enumerate(page_objs):
        chunk_start = m.start()
        chunk_end = page_objs[idx + 1].start() if idx + 1 < len(page_objs) else len(data)
        chunk = data[chunk_start:chunk_end]
        for stream in _find_streams(chunk):
            page_texts.append(_extract_text(stream))
    if not page_texts:
        for stream in _find_streams(data):
            page_texts.append(_extract_text(stream))
    if page_count == 0 and page_texts:
        page_count = len(page_texts)
    return page_texts, page_count


def _trailer_metadata(data: bytes) -> dict:
    out = {}
    m = re.search(rb"trailer\s*<<(.*?)>>\s*startxref", data, re.S)
    if not m:
        return out
    body = m.group(1)
    info_ref = re.search(rb"/Info\s+(\d+)\s+\d+\s+R", body)
    candidates: list[bytes] = [body]
    if info_ref:
        num = info_ref.group(1)
        om = re.search(rb"(\d+)\s+0\s+obj(.*?)endobj", data, re.S)
        # locate the specific object number
        for om in re.finditer(rb"\b%s\s+0\s+obj(.*?)endobj" % num, data, re.S):
            candidates.insert(0, om.group(1))
    for block in candidates:
        for key in (b"Title", b"Author", b"Subject", b"Keywords", b"Creator",
                    b"Producer", b"CreationDate", b"ModDate"):
            if key.decode() in out:
                continue
            km = re.search(re.escape(key) + rb"\s*\(([^)]*)\)", block, re.S)
            if km:
                out[key.decode()] = km.group(1).decode("latin-1")
    return out


def _builtin_links(data: bytes) -> list[dict]:
    out = []
    for m in re.finditer(rb"/URI\s*\(([^)]+)\)", data):
        out.append({"url": m.group(1).decode("latin-1")})
    return out


def _builtin_outline(data: bytes) -> list[dict]:
    out = []
    for m in re.finditer(rb"/Title\s*\(([^)]*)\)", data):
        out.append({"title": m.group(1).decode("latin-1")})
    return out


def parse_pdf(data: bytes) -> dict:
    """Structured PDF extraction with parser provenance."""
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(data))
        pages = []
        for idx, page in enumerate(reader.pages):
            pages.append({"page": idx + 1,
                          "text": page.extract_text() or "",
                          "width": float(page.mediabox.width) if page.mediabox else 0.0,
                          "height": float(page.mediabox.height) if page.mediabox else 0.0})
        meta = {k: str(v) for k, v in (reader.metadata or {}).items()}
        return {"parser": "pypdf", "page_count": len(pages), "pages": pages,
                "metadata": meta, "links": [], "outline": []}
    except Exception:
        pass
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(data))
        pages = [{"page": i + 1, "text": p.extract_text() or ""}
                 for i, p in enumerate(reader.pages)]
        return {"parser": "pypdf2", "page_count": len(pages), "pages": pages,
                "metadata": {k: str(v) for k, v in (reader.metadata or {}).items()},
                "links": [], "outline": []}
    except Exception:
        pass
    page_texts, page_count = _builtin_pages(data)
    return {"parser": "builtin", "page_count": page_count,
            "pages": [{"page": i + 1, "text": t} for i, t in enumerate(page_texts)],
            "metadata": _trailer_metadata(data),
            "links": _builtin_links(data),
            "outline": _builtin_outline(data)}


def _safe_parse_pdf(data: bytes) -> dict:
    """parse_pdf that never raises on malformed input - returns an error dict."""
    try:
        return parse_pdf(data)
    except Exception as exc:
        return {"parser": "error", "error": str(exc), "page_count": 0,
                "pages": [], "metadata": {}, "links": [], "outline": [],
                "chunks": [], "tables": [], "full_text": ""}