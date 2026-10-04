from rag.ingest import chunk_documents, load_documents
from rag.index import PolicyIndex


def test_corpus_has_multiple_formats_and_size():
    docs = load_documents()
    assert {d["format"] for d in docs} >= {"markdown", "html", "txt"}
    assert 5 <= len(docs) <= 20
    assert sum(len(s["text"].split()) for d in docs for s in d["sections"]) > 10000


def test_html_boilerplate_is_removed():
    doc = next(d for d in load_documents() if d["source_file"].endswith(".html") and d["doc_id"] == "POL-006")
    text = " ".join(s["text"] for s in doc["sections"])
    assert "console.log" not in text and "People Site" not in text


def test_chunk_metadata_supports_citations():
    for c in chunk_documents(load_documents()):
        assert c["doc_id"].startswith("POL-") and c["title"] and c["section"] and c["snippet"] and c["source_file"]


def test_chunking_is_deterministic():
    a = [c["chunk_id"] for c in chunk_documents(load_documents())]
    b = [c["chunk_id"] for c in chunk_documents(load_documents())]
    assert a == b and len(set(a)) == len(a)


def test_retrieval_finds_right_section():
    idx = PolicyIndex.from_corpus()
    top = idx.search("How many PTO days carry over to next year?", 3)["results"][0]
    assert (top["doc_id"], top["section_number"]) == ("POL-001", "4")
    top = idx.search("Who must approve an expense over $2,500?", 3)["results"][0]
    assert top["doc_id"] == "POL-005"


def test_out_of_corpus_query_has_insufficient_evidence():
    idx = PolicyIndex.from_corpus()
    assert not idx.search("What is the weather in Paris today?")["evidence"]["sufficient"]
    assert not idx.search("stock option vesting schedule")["evidence"]["sufficient"]


def test_get_section_roundtrip():
    idx = PolicyIndex.from_corpus()
    s = idx.get_section("POL-003", "5")
    assert s and "20 business days" in s["text"]
    assert idx.get_section("POL-003", "Carryover") is None
    assert idx.get_section("POL-001", "Carryover")["section_number"] == "4"


def test_out_of_corpus_word_blocks_false_match():
    """'vesting' stems onto the 401(k) 'vested' sentence, but 'stock' appears nowhere in the corpus -> not sufficient evidence."""
    from rag.index import PolicyIndex
    ix = PolicyIndex.load_or_build()
    assert not ix.search("What is the company stock option vesting schedule?", 4)["evidence"]["sufficient"]
    assert ix.search("How many paid holidays do US employees get each year?", 4)["evidence"]["sufficient"]  # short tokens like 'US' must not trigger it
