"""Finding the right knowledge for a customer's question.

Hybrid search:
  * meaning: embeddings (OpenRouter /embeddings, works across Nepali, Romanized Nepali and English), and
  * keywords: BM25 with a small Nepali / Romanized Nepali / English synonym list (always available, no API).
If embeddings aren't configured or fail, keyword search alone is used, so the bot never stops answering.
"""
import hashlib
import logging
import math
import re
import threading
from array import array
from collections import Counter

import requests
from django.conf import settings
from django.core.cache import cache

from . import llm
from .models import KnowledgeItem

logger = logging.getLogger(__name__)

EMBED_BATCH = 64

# Words customers use for the same thing. Each group is matched as one concept.
SYNONYMS = [
    "fee fees price prices cost costs charge charges rate rates kati katiho paisa rakam shulka dam daam शुल्क मूल्य दाम पैसा रकम कति",
    "admission admissions enroll enrol enrollment enrolment bharna bharnaa apply application भर्ना आवेदन",
    "course courses program programs programme programmes class classes subject subjects padhai कक्षा कोर्स पढाइ विषय",
    "visa visas bhisa भिसा",
    "location address where kaha kahan kata branch office thegana ठेगाना कहाँ कहा शाखा",
    "time timing timings hours open opening khulcha khulne samaya baje schedule समय बजे खुल्छ",
    "delivery deliver shipping ship dispatch courier pathaunu pathaidinu पठाउनु डेलिभरी",
    "payment pay esewa khalti bank tirne bhuktani installment instalment भुक्तानी तिर्ने किस्ता",
    "scholarship scholarships discount discounts chhut chhatrabritti छुट छात्रवृत्ति",
    "document documents papers paper kagaj kagajpatra requirement requirements required checklist कागजात कागजपत्र",
    "duration years year months month mahina barsa barsha वर्ष महिना अवधि",
    "contact phone number call mobile sampark सम्पर्क फोन नम्बर",
    "return exchange refund firta फिर्ता",
    "university universities college colleges campus school vidyalaya विश्वविद्यालय कलेज क्याम्पस विद्यालय",
    "australia australian astrelia अस्ट्रेलिया",
    "japan japanese जापान",
    "canada canadian क्यानडा",
    "stock available availability pauncha paincha उपलब्ध स्टक",
]
_GROUP = {}
for _i, _g in enumerate(SYNONYMS):
    for _w in _g.split():
        _GROUP.setdefault(_w, f"§{_i}")


def tokens(text):
    words = re.findall(r"[a-z0-9]+|[ऀ-ॿ]+", (text or "").lower())
    out = [w for w in words if len(w) > 1]
    out += [_GROUP[w] for w in words if w in _GROUP]
    return out


# ------------------------------------------------------------------ embeddings
def model_name():
    return getattr(settings, "EMBEDDING_MODEL", "openai/text-embedding-3-small")


def enabled():
    return getattr(settings, "EMBEDDINGS_ENABLED", True) and llm.configured()


def _normalize(vec):
    n = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / n for x in vec]


def embed_texts(texts):
    """Vectors for texts (unit length). Raises llm.AIError on failure."""
    out = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = [t[:8000] for t in texts[i:i + EMBED_BATCH]]
        try:
            resp = requests.post(f"{settings.OPENROUTER_BASE_URL}/embeddings", timeout=60, json={"model": model_name(), "input": batch},
                                 headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}", "X-Title": "OmniInbox"})
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise llm.AIError("Couldn't reach the embeddings service.") from exc
        if resp.status_code >= 400 or "data" not in data:
            raise llm.AIError(f"Embeddings failed ({resp.status_code}): {str(data.get('error', data))[:200]}")
        rows = sorted(data["data"], key=lambda r: r.get("index", 0))
        out += [_normalize(r["embedding"]) for r in rows]
    return out


def pack(vec):
    return array("f", vec).tobytes()


def unpack(blob):
    a = array("f")
    a.frombytes(bytes(blob))
    return a


def embed_items(ids):
    """Compute and store embeddings for these knowledge entries (no-op when embeddings are off)."""
    if not enabled() or not ids:
        return 0
    items = list(KnowledgeItem.objects.filter(id__in=ids))
    vectors = embed_texts([f"{i.title}\n{i.content}" for i in items])
    model = model_name()
    for item, vec in zip(items, vectors):
        item.embedding, item.embedding_model = pack(vec), model
    KnowledgeItem.objects.bulk_update(items, ["embedding", "embedding_model"])
    return len(items)


def embed_items_async(ids):
    if getattr(settings, "KNOWLEDGE_IMPORT_SYNC", False):
        _safe_embed(ids)
        return
    threading.Thread(target=_safe_embed, args=(list(ids),), daemon=True).start()


def _safe_embed(ids):
    from django.db import close_old_connections
    close_old_connections()
    try:
        embed_items(ids)
    except Exception:  # noqa: BLE001
        logger.warning("Embedding knowledge entries failed; keyword search will be used for them", exc_info=True)
    finally:
        close_old_connections()


def query_vector(text):
    if not enabled() or not text.strip():
        return None
    key = "qvec:" + hashlib.sha1(f"{model_name()}|{text}".encode()).hexdigest()
    hit = cache.get(key)
    if hit is not None:
        return hit
    try:
        vec = embed_texts([text])[0]
    except llm.AIError:
        logger.warning("Query embedding failed; using keyword search", exc_info=True)
        return None
    cache.set(key, vec, 86400)
    return vec


# ------------------------------------------------------------------ search
def _docs(ws):
    """Everything the AI may use: knowledge entries and the team's saved replies."""
    from inbox.models import CannedReply
    docs = []
    for k in KnowledgeItem.objects.filter(workspace=ws).select_related("source"):
        docs.append({"id": k.id, "kind": "knowledge", "title": k.title, "content": k.content,
                     "source": k.source.name if k.source_id else "", "source_kind": k.source.kind if k.source_id else "manual",
                     "vec": unpack(k.embedding) if k.embedding and k.embedding_model == model_name() else None})
    for c in CannedReply.objects.filter(workspace=ws):
        docs.append({"id": c.id, "kind": "saved_reply", "title": f"Saved reply: {c.title}", "content": c.body,
                     "source": "Saved replies", "source_kind": "saved_reply", "vec": None})
    return docs


def _bm25(docs, query_tokens, k1=1.4, b=0.75):
    if not query_tokens:
        return [0.0] * len(docs)
    toks = [tokens(f"{d['title']} {d['title']} {d['content']}") for d in docs]  # title counts double
    n = len(docs)
    avg = sum(len(t) for t in toks) / n if n else 1
    df = Counter(w for t in toks for w in set(t))
    scores = []
    for t in toks:
        tf = Counter(t)
        s = 0.0
        for w in set(query_tokens):
            if w not in tf:
                continue
            idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
            s += idf * tf[w] * (k1 + 1) / (tf[w] + k1 * (1 - b + b * len(t) / avg))
        scores.append(s)
    return scores


def search(ws, query, limit=8):
    """Best matching entries for a question: [{id, kind, title, content, source, source_kind, score, match}]."""
    docs = _docs(ws)
    if not docs:
        return []
    lex = _bm25(docs, tokens(query))
    top = max(lex) or 1.0
    qv = query_vector(query) if any(d["vec"] is not None for d in docs) else None
    results = []
    for d, ls in zip(docs, lex):
        lex_n = ls / top
        if qv is not None and d["vec"] is not None:
            cos = sum(a * b for a, b in zip(qv, d["vec"]))
            score, match = 0.7 * max(0.0, cos) + 0.3 * lex_n, "meaning"
        else:
            score, match = 0.6 * lex_n, "keywords"
        results.append({**{k: v for k, v in d.items() if k != "vec"}, "score": round(score, 4), "match": match})
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]


def context_for(ws, query, budget):
    """Entries to give the AI for this question, best first, within the character budget.
    Small knowledge bases are sent whole (ranked), big ones are cut to the best matches."""
    docs = search(ws, query, limit=1000)
    picked, used = [], 0
    for d in docs:
        size = len(d["title"]) + len(d["content"]) + 20
        if used + size > budget:
            continue
        picked.append(d)
        used += size
    return picked
