#!/usr/bin/env python3
"""Local retrieval index for the research engine.

Dense (sqlite-vec) + sparse (bm25s) + exact (FTS5), fused with RRF and
reranked by the caller.  One SQLite file, no server.

Composed from proven OSS: sqlite-vec (vectors), bm25s (BM25),
chonkie (chunking), fastembed (embeddings).

Env:
  RESEARCH_VAULT         vault dir (default ~/.autonect/research-vault)
  RESEARCH_EMBED_MODEL   fastembed model (default multilingual MiniLM)
  RESEARCH_EMBED_DIM     vector dim (default 384)
  RESEARCH_CHUNK_SIZE    target chars per chunk (default 1200)
"""
import os, json, sqlite3, hashlib, math
from pathlib import Path

VAULT = Path(os.environ.get("RESEARCH_VAULT",
             str(Path.home() / ".autonect/research-vault")))
IDX_DIR = VAULT / ".index"
DB_PATH = IDX_DIR / "research.db"
BM25_PATH = IDX_DIR / "bm25"

EMBED_MODEL = os.environ.get(
    "RESEARCH_EMBED_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
EMBED_DIM = int(os.environ.get("RESEARCH_EMBED_DIM", "384"))
CHUNK_SIZE = int(os.environ.get("RESEARCH_CHUNK_SIZE", "1200"))
RRF_K = 60

_EMB = None

def embed_model():
    """Lazy fastembed singleton."""
    global _EMB
    if _EMB is None:
        from fastembed import TextEmbedding
        _EMB = TextEmbedding(model_name=EMBED_MODEL)
    return _EMB

def embed_texts(texts, batch_size=16):
    """List[str] -> list[list[float]]."""
    return [list(map(float, v)) for v in
            embed_model().embed(list(texts), batch_size=batch_size)]

def _load_vec(conn):
    import sqlite_vec
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return sqlite_vec

def connect(path=None):
    """Open the index DB with sqlite-vec loaded and schema ensured."""
    IDX_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path or DB_PATH))
    conn.row_factory = sqlite3.Row
    sv = _load_vec(conn)
    init_schema(conn, sv)
    return conn, sv

def init_schema(conn, sv):
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS meta(
        key TEXT PRIMARY KEY, value TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS docs(
        id INTEGER PRIMARY KEY,
        url TEXT UNIQUE, title TEXT, sitename TEXT, date TEXT,
        path TEXT, mtime REAL, size INTEGER, sha TEXT,
        fetched_at REAL, n_chunks INTEGER DEFAULT 0)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS chunks(
        id INTEGER PRIMARY KEY,
        doc_id INTEGER NOT NULL,
        ord INTEGER, text TEXT,
        FOREIGN KEY(doc_id) REFERENCES docs(id) ON DELETE CASCADE)""")
    cur.execute(f"""CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vec
        USING vec0(embedding float[{EMBED_DIM}] distance_metric=cosine)""")
    cur.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
        USING fts5(text, tokenize='unicode61 remove_diacritics 2')""")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_chunks_doc ON chunks(doc_id)")
    # record model identity so a model change forces a rebuild
    m = cur.execute("SELECT value FROM meta WHERE key='embed_model'").fetchone()
    if m is None:
        cur.execute("INSERT INTO meta(key,value) VALUES('embed_model',?)",
                    (EMBED_MODEL,))
    elif m["value"] != EMBED_MODEL:
        raise RuntimeError(
            f"index built with {m['value']!r}, env wants {EMBED_MODEL!r}; "
            "run `research index --rebuild`")
    conn.commit()

# ---------------------------------------------------------------- chunk

def chunk_text(text, size=CHUNK_SIZE):
    """Split markdown into overlapping-ish chunks via chonkie, with a
    plain fallback so the index never hard-fails on odd input."""
    text = (text or "").strip()
    if not text:
        return []
    try:
        from chonkie import RecursiveChunker
        ch = RecursiveChunker(tokenizer="character", chunk_size=size,
                              min_characters_per_chunk=40)
        out = [c.text.strip() for c in ch.chunk(text) if c.text.strip()]
        if out:
            return out
    except Exception:
        pass
    # fallback: paragraph packing
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks, buf = [], ""
    for p in paras:
        if len(buf) + len(p) + 2 <= size:
            buf = (buf + "\n\n" + p) if buf else p
        else:
            if buf:
                chunks.append(buf)
            buf = p if len(p) <= size else p[:size]
    if buf:
        chunks.append(buf)
    return chunks

def parse_front_matter(text):
    """Return (meta_dict, body). Handles the vault's YAML-ish header."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    head, body = text[4:end], text[end + 5:]
    meta = {}
    for line in head.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, body

# ---------------------------------------------------------------- index

def _doc_row(conn, url):
    return conn.execute("SELECT * FROM docs WHERE url=?", (url,)).fetchone()

def index_doc(conn, sv, url, path, title="", meta=None, body="",
              mtime=None, force=False):
    """Insert or refresh one doc + its chunks. Returns (n_chunks, changed)."""
    meta = meta or {}
    raw = ""
    if path and Path(path).exists():
        raw = Path(path).read_text(encoding="utf-8", errors="ignore")
        fm, body2 = parse_front_matter(raw)
        meta = {**fm, **meta}
        if not body2.strip():
            body2 = body
        body = body2
        mtime = mtime or Path(path).stat().st_mtime
    sha = hashlib.sha1((body or "").encode("utf-8")).hexdigest()
    row = _doc_row(conn, url)
    if row and not force and row["sha"] == sha and row["mtime"] == mtime:
        return row["n_chunks"], False
    chunks = chunk_text(body)
    cur = conn.cursor()
    if row:
        did = row["id"]
        old = [r["id"] for r in cur.execute(
            "SELECT id FROM chunks WHERE doc_id=?", (did,))]
        if old:
            cur.executemany("DELETE FROM chunk_vec WHERE rowid=?",
                            [(i,) for i in old])
            cur.executemany("DELETE FROM chunks_fts WHERE rowid=?",
                            [(i,) for i in old])
        cur.execute("DELETE FROM chunks WHERE doc_id=?", (did,))
        cur.execute("""UPDATE docs SET title=?,sitename=?,date=?,path=?,
            mtime=?,size=?,sha=?,n_chunks=? WHERE id=?""",
            (title or meta.get("title", ""), meta.get("sitename", ""),
             meta.get("date", ""), str(path or ""), mtime,
             len(body or ""), sha, len(chunks), did))
    else:
        cur.execute("""INSERT INTO docs(url,title,sitename,date,path,mtime,
            size,sha,fetched_at,n_chunks) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (url, title or meta.get("title", ""), meta.get("sitename", ""),
             meta.get("date", ""), str(path or ""), mtime,
             len(body or ""), sha, __import__("time").time(), len(chunks)))
        did = cur.lastrowid
    if chunks:
        vecs = embed_texts(chunks)
        for i, (txt, vec) in enumerate(zip(chunks, vecs)):
            cur.execute("INSERT INTO chunks(doc_id,ord,text) VALUES(?,?,?)",
                        (did, i, txt))
            cid = cur.lastrowid
            cur.execute("INSERT INTO chunk_vec(rowid,embedding) VALUES(?,?)",
                        (cid, sv.serialize_float32(vec)))
            cur.execute("INSERT INTO chunks_fts(rowid,text) VALUES(?,?)",
                        (cid, txt))
    conn.commit()
    return len(chunks), True

def iter_vault_docs():
    """Yield (url, path, title, meta) for every top-level vault markdown."""
    for p in sorted(VAULT.glob("*.md")):
        raw = p.read_text(encoding="utf-8", errors="ignore")
        fm, _ = parse_front_matter(raw)
        url = fm.get("url", p.stem)
        yield url, p, fm.get("title", ""), fm

# ---------------------------------------------------------------- search

def _dense(conn, sv, qvec, k):
    rows = conn.execute(
        "SELECT rowid, distance FROM chunk_vec "
        "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
        (sv.serialize_float32(qvec), k)).fetchall()
    return [(r["rowid"], 1.0 - float(r["distance"])) for r in rows]

def _sparse(conn, query, k):
    """FTS5 BM25. Query is sanitised to a safe OR-of-terms."""
    import re as _re
    terms = [t for t in _re.findall(r"\w+", query, _re.UNICODE) if len(t) > 1]
    if not terms:
        return []
    match = " OR ".join('"' + t.replace('"', '') + '"' for t in terms)
    try:
        rows = conn.execute(
            "SELECT rowid, bm25(chunks_fts) AS s FROM chunks_fts "
            "WHERE chunks_fts MATCH ? ORDER BY s LIMIT ?",
            (match, k)).fetchall()
    except sqlite3.OperationalError:
        return []
    # bm25() is negative-is-better; map to positive
    return [(r["rowid"], -float(r["s"])) for r in rows]

def _rrf(rank_lists, k=RRF_K):
    """Reciprocal Rank Fusion over several ranked [(id,score)] lists."""
    agg = {}
    for lst in rank_lists:
        for rank, (cid, _s) in enumerate(lst):
            agg[cid] = agg.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(agg.items(), key=lambda x: x[1], reverse=True)

def search(conn, sv, query, top=8, pool=40, alpha=0.5):
    """Hybrid retrieval. Returns list of dicts with chunk text + doc meta."""
    qvec = embed_texts([query])[0]
    dense = _dense(conn, sv, qvec, pool)
    sparse = _sparse(conn, query, pool)
    fused = _rrf([dense, sparse])
    if not fused:
        return []
    ids = [cid for cid, _ in fused[:pool]]
    qmarks = ",".join("?" * len(ids))
    rows = conn.execute(
        f"""SELECT c.id, c.text, c.ord, d.url, d.title, d.sitename, d.date
            FROM chunks c JOIN docs d ON d.id=c.doc_id
            WHERE c.id IN ({qmarks})""", ids).fetchall()
    by_id = {r["id"]: r for r in rows}
    dmap = dict(dense)
    smap = dict(sparse)
    out = []
    for cid, rrf_score in fused[:top]:
        r = by_id.get(cid)
        if not r:
            continue
        out.append({
            "chunk_id": cid,
            "url": r["url"], "title": r["title"], "sitename": r["sitename"],
            "date": r["date"], "ord": r["ord"], "text": r["text"],
            "rrf": round(rrf_score, 6),
            "dense": round(dmap.get(cid, 0.0), 4),
            "sparse": round(smap.get(cid, 0.0), 4),
        })
    return out

def doc_context(conn, url, max_chars=6000):
    """Return the best contiguous body for a URL (all its chunks joined)."""
    rows = conn.execute(
        """SELECT c.text FROM chunks c JOIN docs d ON d.id=c.doc_id
           WHERE d.url=? ORDER BY c.ord""", (url,)).fetchall()
    out = "\n\n".join(r["text"] for r in rows)
    return out[:max_chars]

# ---------------------------------------------------------------- context

def build_context(conn, sv, queries, budget_chars=12000, per_doc=4000,
                  top=10, compress_fn=None):
    """Assemble an AI-facing context block under a character budget.

    Deduplicates by document, ranks chunks across all queries, packs
    until the budget is hit. compress_fn(text)->text is applied per
    document when supplied (e.g. src/text/compress.compress).
    """
    seen_docs, picked, total = {}, [], 0
    for q in queries:
        for hit in search(conn, sv, q, top=top):
            url = hit["url"]
            if url in seen_docs:
                continue
            body = doc_context(conn, url, max_chars=per_doc)
            if compress_fn:
                try:
                    body = compress_fn(body)
                except Exception:
                    pass
            block = (f"## {hit['title'] or url}\n"
                     f"URL: {url}\n"
                     f"Relevance: {hit['rrf']:.4f} "
                     f"(dense {hit['dense']:.3f} / sparse {hit['sparse']:.3f})\n\n"
                     f"{body}\n")
            if total + len(block) > budget_chars:
                return picked, total
            picked.append(block)
            seen_docs[url] = True
            total += len(block)
            if len(picked) >= top:
                return picked, total
    return picked, total

# ---------------------------------------------------------------- stats

def stats(conn):
    d = conn.execute("SELECT COUNT(*) n FROM docs").fetchone()["n"]
    c = conn.execute("SELECT COUNT(*) n FROM chunks").fetchone()["n"]
    v = conn.execute("SELECT COUNT(*) n FROM chunk_vec").fetchone()["n"]
    size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    return {"docs": d, "chunks": c, "vectors": v, "db_bytes": size,
            "db": str(DB_PATH), "embed_model": EMBED_MODEL}
