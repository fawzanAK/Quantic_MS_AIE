"""Vector index + retriever.

Embeddings: TF-IDF (stemmed unigrams+bigrams) -> truncated SVD (LSA, 128 dims, fixed seed) -> L2-normalised
dense vectors stored in a FAISS inner-product index. Retrieval is *hybrid*: dense (FAISS) cosine blended with
sparse TF-IDF cosine, then a light heading-aware lexical rerank. Everything is local, free, offline and
deterministic - no model download or API key is required, which keeps the free-tier deploy small.
"""
from __future__ import annotations

import json
import pickle
import re
from pathlib import Path

import faiss
import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

import settings
from rag.ingest import chunk_documents, load_documents
from rag.text import analyzer, rewrite_query, tokens

DENSE_WEIGHT = 0.5  # hybrid blend: 0.5 dense (LSA/FAISS) + 0.5 sparse (TF-IDF)


class PolicyIndex:
    def __init__(self, chunks, tfidf, svd, sparse, dense):
        self.chunks: list[dict] = chunks
        self.tfidf: TfidfVectorizer = tfidf
        self.svd: TruncatedSVD = svd
        self.sparse = sparse  # (n_chunks, vocab) L2-normalised CSR
        self.dense = dense.astype("float32")  # (n_chunks, dims) L2-normalised
        self.faiss = faiss.IndexFlatIP(self.dense.shape[1])
        self.faiss.add(self.dense)
        self._by_section: dict[tuple[str, str], list[int]] = {}
        for i, c in enumerate(chunks):
            self._by_section.setdefault((c["doc_id"], c["section_number"]), []).append(i)
        self._chunk_tokens = [set(tokens(c["text"])) for c in chunks]

    # ------------------------------------------------------------------ build / persist
    @classmethod
    def build(cls, chunks: list[dict]) -> "PolicyIndex":
        tfidf = TfidfVectorizer(analyzer=analyzer, sublinear_tf=True, norm="l2")
        sparse = tfidf.fit_transform([c["embed_text"] for c in chunks])
        dims = max(2, min(settings.LSA_DIMS, sparse.shape[0] - 1, sparse.shape[1] - 1))
        svd = TruncatedSVD(n_components=dims, random_state=settings.SEED)  # fixed seed -> reproducible
        dense = normalize(svd.fit_transform(sparse))
        return cls(chunks, tfidf, svd, sparse, dense)

    @classmethod
    def from_corpus(cls, chunk_words: int | None = None, overlap: int | None = None) -> "PolicyIndex":
        return cls.build(chunk_documents(load_documents(), chunk_words, overlap))

    def save(self, directory: Path | str) -> None:
        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        (d / "chunks.json").write_text(json.dumps(self.chunks, indent=1), encoding="utf-8")
        faiss.write_index(self.faiss, str(d / "vectors.faiss"))
        with open(d / "models.pkl", "wb") as f:  # locally built artifact, never loaded from untrusted sources
            pickle.dump({"tfidf": self.tfidf, "svd": self.svd, "sparse": self.sparse, "dense": self.dense}, f)

    @classmethod
    def load(cls, directory: Path | str) -> "PolicyIndex":
        d = Path(directory)
        chunks = json.loads((d / "chunks.json").read_text(encoding="utf-8"))
        with open(d / "models.pkl", "rb") as f:
            m = pickle.load(f)
        return cls(chunks, m["tfidf"], m["svd"], m["sparse"], m["dense"])

    @classmethod
    def load_or_build(cls, directory: Path | str | None = None) -> "PolicyIndex":
        d = Path(directory or settings.INDEX_DIR)
        try:
            return cls.load(d)
        except Exception:
            idx = cls.from_corpus()
            try:
                idx.save(d)
            except OSError:
                pass  # read-only filesystem: still usable in memory
            return idx

    # ------------------------------------------------------------------ search
    def search(self, query: str, top_k: int | None = None, doc_id: str | None = None, rewrite: bool = True) -> dict:
        top_k = top_k or settings.TOP_K
        q = rewrite_query(query) if rewrite else query
        qs = self.tfidf.transform([q])
        sparse_scores = (self.sparse @ qs.T).toarray().ravel()
        qd = normalize(self.svd.transform(qs)).astype("float32")
        n = self.dense.shape[0]
        d_scores, d_ids = self.faiss.search(qd, n)  # corpus is tiny: score everything
        dense_scores = np.zeros(n, dtype="float32")
        dense_scores[d_ids[0]] = d_scores[0]
        hybrid = DENSE_WEIGHT * np.clip(dense_scores, 0, None) + (1 - DENSE_WEIGHT) * sparse_scores

        qtok = set(tokens(query))
        final = hybrid.copy()
        for i, c in enumerate(self.chunks):
            head_hits = len(qtok & set(tokens(c["section_heading"] + " " + c["title"])))
            final[i] += min(0.15, 0.04 * head_hits)  # heading-aware lexical rerank boost
        order = np.argsort(-final)
        results = []
        for i in order:
            c = self.chunks[int(i)]
            if doc_id and c["doc_id"] != doc_id:
                continue
            results.append({**{k: c[k] for k in ("chunk_id", "doc_id", "title", "section", "section_number", "section_heading", "source_file", "snippet", "text")},
                            "score": round(float(final[int(i)]), 4)})
            if len(results) >= top_k:
                break
        for r_i, r in enumerate(results, 1):
            r["rank"] = r_i
        return {"query": query, "rewritten_query": q, "top_k": top_k, "results": results, "evidence": self._evidence(query, qtok, results)}

    def _evidence(self, query: str, qtok: set[str], results: list[dict]) -> dict:
        """Guardrail signal: best score + share of query content terms found in the top-3 chunks."""
        if not results:
            return {"max_score": 0.0, "term_coverage": 0.0, "uncovered_terms": sorted(qtok), "sufficient": False}
        top_text = set()
        for r in results[:3]:
            top_text |= set(tokens(r["text"] + " " + r["title"] + " " + r["section_heading"]))
        # IDF-weighted coverage: a distinctive term missing from the evidence (e.g. "cryptocurrency")
        # costs more than a generic one. Terms absent from the whole corpus get the maximum IDF.
        idf, vocab = self.tfidf.idf_, self.tfidf.vocabulary_
        max_idf = float(idf.max())
        w = {t: (float(idf[vocab[t]]) if t in vocab else max_idf) for t in qtok}
        total = sum(w.values())
        coverage = sum(w[t] for t in qtok & top_text) / total if total else 0.0
        # map uncovered stems back to the words the user typed, for transparent caveats
        words = {}
        for w in re.findall(r"[A-Za-z0-9]+", query):
            for t in tokens(w):
                words.setdefault(t, w.lower())
        uncovered = sorted(words[t] for t in (qtok - top_text) if t in words)
        mx = results[0]["score"]
        # A question term that appears nowhere in the whole corpus (e.g. "stock") is a strong out-of-corpus signal even when
        # other words ("vesting" ~ "vested") match: demand near-complete coverage in that case.
        oov = [t for t in qtok if t not in vocab and len(t) >= 4]
        ok = mx >= settings.MIN_RELEVANCE and coverage >= (max(settings.MIN_TERM_COVERAGE, 0.85) if oov else settings.MIN_TERM_COVERAGE)
        return {"max_score": round(mx, 4), "term_coverage": round(coverage, 3), "uncovered_terms": uncovered, "sufficient": bool(ok)}

    # ------------------------------------------------------------------ section lookup
    def get_section(self, doc_id: str, section: str) -> dict | None:
        """Look up a section by number ('5', '§5') or by (partial) heading text."""
        doc_id = doc_id.strip().upper()
        sec = section.strip().lstrip("§").strip()
        idxs = self._by_section.get((doc_id, sec))
        if not idxs:
            low = sec.lower()
            for (d, num), ids in self._by_section.items():
                if d == doc_id and low and low in self.chunks[ids[0]]["section_heading"].lower():
                    idxs = ids
                    break
        if not idxs:
            return None
        first = self.chunks[idxs[0]]
        text = " ".join(self.chunks[i]["text"] for i in idxs) if len(idxs) == 1 else self._merge_overlapping([self.chunks[i]["text"] for i in idxs])
        return {"doc_id": doc_id, "title": first["title"], "section_number": first["section_number"],
                "section_heading": first["section_heading"], "section": first["section"],
                "source_file": first["source_file"], "text": text}

    @staticmethod
    def _merge_overlapping(parts: list[str]) -> str:
        """Re-join overlapping word windows back into the original section text."""
        merged = parts[0].split()
        for p in parts[1:]:
            w = p.split()
            overlap = 0
            for k in range(min(len(merged), len(w)), 0, -1):
                if merged[-k:] == w[:k]:
                    overlap = k
                    break
            merged.extend(w[overlap:])
        return " ".join(merged)

    def sections_of(self, doc_id: str) -> list[dict]:
        seen, out = set(), []
        for c in self.chunks:
            if c["doc_id"] == doc_id and c["section_number"] not in seen:
                seen.add(c["section_number"])
                out.append({"section_number": c["section_number"], "section_heading": c["section_heading"]})
        return out

    def documents(self) -> list[dict]:
        docs: dict[str, dict] = {}
        for c in self.chunks:
            d = docs.setdefault(c["doc_id"], {"doc_id": c["doc_id"], "title": c["title"], "source_file": c["source_file"], "format": c["format"], "chunks": 0})
            d["chunks"] += 1
        return sorted(docs.values(), key=lambda d: d["doc_id"])
