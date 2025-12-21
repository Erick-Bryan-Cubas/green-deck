import re
from typing import List
from app.config import MAX_SOURCE_CHARS

def truncate_source(text: str, limit: int = MAX_SOURCE_CHARS) -> str:
    return (text or "").strip()

def looks_english(s: str) -> bool:
    if not s:
        return False
    s_low = s.lower()
    pt_hits = sum(w in s_low for w in [" que ", " por que ", " qual ", " quais ", " é ", " são ", " custo ", " consulta "])
    return pt_hits >= 2

def split_sentences(s: str) -> List[str]:
    s = re.sub(r"\s+", " ", (s or "")).strip()
    if not s:
        return []
    parts = re.split(r"(?<=[\.\!\?])\s+", s)
    return [p.strip() for p in parts if p.strip()]

def limit_words(s: str, n: int) -> str:
    words = (s or "").split()
    if len(words) <= n:
        return s
    return " ".join(words[:n]).rstrip(" ,;:") + "."

def normalize_basic_answer(a: str) -> str:
    sents = split_sentences(a)
    out = " ".join(sents[:2]) if sents else (a or "")
    out = limit_words(out, 28)
    return out.strip()

def normalize_cloze_answer(a: str) -> str:
    sents = split_sentences(a)
    out = sents[0] if sents else (a or "")
    out = limit_words(out, 22)
    out = out.strip()
    if not out.lower().startswith("extra:"):
        out = "Extra: " + out
    return out

def ensure_prefix(q: str) -> str:
    q = (q or "").strip()
    if not q:
        return q
    if q.startswith("[BASIC]") or q.startswith("[CLOZE]"):
        return q
    if "{{c1::" in q:
        return "[CLOZE] " + q
    return "[BASIC] " + q

def is_valid_cloze(q: str) -> bool:
    return q.count("{{c1::") == 1
