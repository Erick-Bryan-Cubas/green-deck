import re
from typing import List, Dict
from app.utils.text import ensure_prefix, is_valid_cloze, normalize_basic_answer, normalize_cloze_answer

def parse_flashcards_qa(text: str) -> List[Dict[str, str]]:
    if not text:
        return []
    t = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = [ln.strip() for ln in t.split("\n")]
    cards = []
    cur_q, cur_a = "", ""
    mode = None

    def flush():
        nonlocal cur_q, cur_a, mode
        q = re.sub(r"\s+", " ", cur_q).strip()
        a = re.sub(r"\s+", " ", cur_a).strip()
        if q and a:
            cards.append({"front": q, "back": a})
        cur_q, cur_a, mode = "", "", None

    for ln in lines:
        if not ln:
            if cur_q and cur_a:
                flush()
            continue

        if re.match(r"(?i)^q\s*:\s*", ln):
            if cur_q and cur_a:
                flush()
            mode = "q"
            cur_q = re.sub(r"(?i)^q\s*:\s*", "", ln).strip()
            continue

        if re.match(r"(?i)^a\s*:\s*", ln):
            mode = "a"
            cur_a = re.sub(r"(?i)^a\s*:\s*", "", ln).strip()
            continue

        if mode == "q":
            cur_q = (cur_q + " " + ln).strip()
        elif mode == "a":
            cur_a = (cur_a + " " + ln).strip()

    if cur_q and cur_a:
        flush()

    # dedup por front
    seen = set()
    out = []
    for c in cards:
        k = re.sub(r"\s+", " ", c["front"]).strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(c)
    return out

def normalize_cards(cards: List[Dict[str, str]]) -> List[Dict[str, str]]:
    normalized = []
    for c in cards:
        q = ensure_prefix(c.get("front", ""))
        a = (c.get("back", "") or "").strip()

        if q.startswith("[CLOZE]"):
            if not is_valid_cloze(q):
                q = "[BASIC] " + re.sub(r"\{\{c1::([^}]+)\}\}", r"\1", q.replace("[CLOZE]", "")).strip()
                a = normalize_basic_answer(a)
            else:
                a = normalize_cloze_answer(a)
        else:
            a = normalize_basic_answer(a)

        a = re.sub(r"(^|\s)(-|\d+\))\s+", " ", a).strip()
        normalized.append({"front": q, "back": a})
    return normalized

def pick_default_deck(deck_options: str) -> str:
    s = (deck_options or "General").strip()
    return s or "General"
