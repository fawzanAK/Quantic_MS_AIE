"""Policy corpus loading: markdown, HTML and TXT -> normalised (doc, sections) -> chunks.

Chunking strategy (justified in design-and-evaluation.md):
  * heading-aware: a chunk never crosses a section boundary, so a citation always points at one section;
  * sections longer than CHUNK_WORDS are split into overlapping word windows;
  * each chunk is prefixed with "<title> | <section heading>" so the embedding carries the context.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

import settings

SUPPORTED = {".md": "markdown", ".html": "html", ".htm": "html", ".txt": "txt"}
_DOC_ID_RE = re.compile(r"POL-\d{3}")
_NUM_HEAD_RE = re.compile(r"^\s*(\d+)\.\s*(.+?)\s*$")


# ----------------------------------------------------------------------------- helpers
def _clean(text: str) -> str:
    text = text.replace("**", "").replace("__", "").replace("`", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_number_heading(h: str) -> tuple[str, str]:
    m = _NUM_HEAD_RE.match(h)
    return (m.group(1), m.group(2)) if m else ("", h.strip())


def _table_to_lines(rows: list[list[str]]) -> list[str]:
    """Render a table as 'Header: value; Header: value' lines so facts stay attached to their labels."""
    if len(rows) < 2:
        return ["; ".join(rows[0])] if rows else []
    head = rows[0]
    return ["- " + "; ".join(f"{h}: {v}" for h, v in zip(head, r)) for r in rows[1:]]


# ----------------------------------------------------------------------------- loaders
def parse_markdown(raw: str) -> dict:
    title_line, sections, cur = "", [], None
    pending_table: list[list[str]] = []

    def flush_table():
        nonlocal pending_table
        if pending_table and cur is not None:
            cur["lines"].extend(_table_to_lines(pending_table))
        pending_table = []

    for line in raw.splitlines():
        if line.startswith("# ") and not title_line:
            title_line = line[2:].strip()
            cur = {"heading": "Document information", "number": "0", "lines": []}
            sections.append(cur)
            continue
        if line.startswith("## "):
            flush_table()
            num, head = _split_number_heading(line[3:])
            cur = {"heading": head, "number": num or str(len(sections)), "lines": []}
            sections.append(cur)
            continue
        if cur is None:
            continue
        if line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            pending_table.append(cells)
            continue
        flush_table()
        cur["lines"].append(line)
    flush_table()
    return {"title_line": title_line, "sections": sections}


def parse_html(raw: str) -> dict:
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()  # cleaning step: scripts/nav/boilerplate never reach the index
    title_line = (soup.title.get_text(strip=True) if soup.title else "") or (soup.h1.get_text(strip=True) if soup.h1 else "")
    sections, cur = [], {"heading": "Document information", "number": "0", "lines": []}
    sections.append(cur)
    body = soup.body or soup
    for el in body.find_all(["h1", "h2", "p", "ul", "ol", "table"]):
        if el.name == "h1":
            continue
        if el.name == "h2":
            num, head = _split_number_heading(el.get_text(" ", strip=True))
            cur = {"heading": head, "number": num or str(len(sections)), "lines": []}
            sections.append(cur)
        elif el.name in ("ul", "ol"):
            for li in el.find_all("li", recursive=False):
                cur["lines"].append("- " + li.get_text(" ", strip=True))
        elif el.name == "table":
            rows = [[c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])] for tr in el.find_all("tr")]
            cur["lines"].extend(_table_to_lines(rows))
        else:
            cur["lines"].append(el.get_text(" ", strip=True))
    return {"title_line": title_line, "sections": sections}


_TXT_SECTION_RE = re.compile(r"^SECTION\s+(\d+)\.\s+(.+?)\s*$")


def parse_txt(raw: str) -> dict:
    lines = raw.splitlines()
    title_line = next((l.strip() for l in lines if l.strip()), "")
    sections, cur = [], {"heading": "Document information", "number": "0", "lines": []}
    sections.append(cur)
    for line in lines[1:]:
        if re.fullmatch(r"=+", line.strip()):
            continue
        m = _TXT_SECTION_RE.match(line.strip())
        if m:
            cur = {"heading": m.group(2).title(), "number": m.group(1), "lines": []}
            sections.append(cur)
            continue
        cur["lines"].append(line)
    return {"title_line": title_line, "sections": sections}


def parse_title_line(title_line: str, fallback_stem: str) -> tuple[str, str]:
    """'POL-001: Title' or 'POL-002 | Title' -> (doc_id, title)."""
    m = _DOC_ID_RE.search(title_line)
    doc_id = m.group(0) if m else fallback_stem.upper()
    title = re.sub(r"^\s*POL-\d{3}\s*[:|\-]\s*", "", title_line).strip() or fallback_stem
    return doc_id, title


def load_documents(corpus_dir: Path | None = None) -> list[dict]:
    corpus_dir = Path(corpus_dir or settings.CORPUS_DIR)
    docs = []
    for path in sorted(corpus_dir.iterdir()):
        fmt = SUPPORTED.get(path.suffix.lower())
        if not fmt:
            continue
        raw = path.read_text(encoding="utf-8")
        parsed = {"markdown": parse_markdown, "html": parse_html, "txt": parse_txt}[fmt](raw)
        doc_id, title = parse_title_line(parsed["title_line"], path.stem)
        sections = []
        for s in parsed["sections"]:
            text = _clean("\n".join(s["lines"]))
            if text:
                sections.append({"number": s["number"], "heading": s["heading"], "text": text})
        docs.append({"doc_id": doc_id, "title": title, "source_file": path.name, "format": fmt, "sections": sections})
    return docs


# ----------------------------------------------------------------------------- chunking
def _snippet(text: str, n: int = 300) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"


def chunk_documents(docs: list[dict], chunk_words: int | None = None, overlap: int | None = None) -> list[dict]:
    chunk_words = chunk_words or settings.CHUNK_WORDS
    overlap = settings.CHUNK_OVERLAP if overlap is None else overlap
    step = max(1, chunk_words - overlap)
    chunks = []
    for d in docs:
        for s in d["sections"]:
            words = s["text"].split()
            if len(words) <= chunk_words * 1.25:  # keep near-limit sections whole
                windows = [s["text"]]
            else:
                windows = []
                for start in range(0, len(words), step):
                    piece = words[start : start + chunk_words]
                    windows.append(" ".join(piece))
                    if start + chunk_words >= len(words):
                        break
            for k, w in enumerate(windows):
                label = f"§{s['number']} {s['heading']}" if s["number"] != "0" else s["heading"]
                chunks.append(
                    {
                        "chunk_id": f"{d['doc_id']}#s{s['number']}-c{k}",
                        "doc_id": d["doc_id"],
                        "title": d["title"],
                        "section_number": s["number"],
                        "section_heading": s["heading"],
                        "section": label,
                        "source_file": d["source_file"],
                        "format": d["format"],
                        "chunk_index": k,
                        "text": w,
                        "embed_text": f"{d['title']} | {s['heading']}\n{w}",
                        "snippet": _snippet(w),
                        "word_count": len(w.split()),
                    }
                )
    return chunks


def corpus_stats(docs: list[dict], chunks: list[dict]) -> dict:
    words = sum(len(s["text"].split()) for d in docs for s in d["sections"])
    return {
        "documents": len(docs),
        "formats": sorted({d["format"] for d in docs}),
        "words": words,
        "est_pages_at_400_words_per_page": round(words / 400, 1),
        "sections": sum(len(d["sections"]) for d in docs),
        "chunks": len(chunks),
    }


def main(argv: list[str] | None = None) -> int:
    """CLI: build and persist the index (`python -m rag.ingest`)."""
    import argparse

    from rag.index import PolicyIndex

    ap = argparse.ArgumentParser(description="Build the policy RAG index")
    ap.add_argument("--chunk-words", type=int, default=settings.CHUNK_WORDS)
    ap.add_argument("--overlap", type=int, default=settings.CHUNK_OVERLAP)
    ap.add_argument("--out", type=Path, default=settings.INDEX_DIR)
    args = ap.parse_args(argv)

    docs = load_documents()
    chunks = chunk_documents(docs, args.chunk_words, args.overlap)
    idx = PolicyIndex.build(chunks)
    idx.save(args.out)
    print(json.dumps({"index_dir": str(args.out), **corpus_stats(docs, chunks)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
