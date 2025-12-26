import re
from typing import List, Dict
from app.utils.text import ensure_prefix, is_valid_cloze, normalize_basic_answer, normalize_cloze_answer


def parse_flashcards_qa(text: str) -> List[Dict[str, str]]:
    """
    Parseia saída do modelo no formato:

    Q: ...
    A: ...
    SRC: "..."

    (uma linha em branco separando cards)

    Aceita também aliases de SRC: FONTE:/REF: (case-insensitive).
    """
    if not text:
        return []

    t = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.strip() for ln in t.split("\n")]

    cards: List[Dict[str, str]] = []
    cur_q, cur_a, cur_src = "", "", ""
    mode = None  # "q" | "a" | "src"

    def flush():
        nonlocal cur_q, cur_a, cur_src, mode
        q = re.sub(r"\s+", " ", cur_q).strip()
        a = re.sub(r"\s+", " ", cur_a).strip()
        s = re.sub(r"\s+", " ", cur_src).strip().strip('"').strip()

        if q and a:
            out = {"front": q, "back": a}
            if s:
                out["src"] = s
            cards.append(out)

        cur_q, cur_a, cur_src, mode = "", "", "", None

    for ln in lines:
        if not ln:
            # card boundary
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

        if re.match(r"(?i)^(src|fonte|ref)\s*:\s*", ln):
            mode = "src"
            cur_src = re.sub(r"(?i)^(src|fonte|ref)\s*:\s*", "", ln).strip()
            continue

        # continuação de linha (quando o modelo quebra)
        if mode == "q":
            cur_q = (cur_q + " " + ln).strip()
        elif mode == "a":
            cur_a = (cur_a + " " + ln).strip()
        elif mode == "src":
            cur_src = (cur_src + " " + ln).strip()
        else:
            # Linha solta fora de Q/A/SRC: ignora pra não "sujar" o parse
            continue

    if cur_q and cur_a:
        flush()

    # dedup por front (mantendo o primeiro)
    seen = set()
    out = []
    for c in cards:
        k = re.sub(r"\s+", " ", c["front"]).strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(c)
    return out


def normalize_cards(cards: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Normaliza:
    - prefixo [BASIC]/[CLOZE]
    - valida/ajusta cloze inválido
    - limpa resposta
    - preserva `src` (quando existir)
    """
    normalized: List[Dict[str, str]] = []
    for c in cards or []:
        q = ensure_prefix(c.get("front", ""))
        a = (c.get("back", "") or "").strip()
        src = (c.get("src", "") or "").strip().strip('"').strip()

        if q.startswith("[CLOZE]"):
            if not is_valid_cloze(q):
                # Se cloze inválido, converte pra BASIC removendo {{c1::...}}
                q = "[BASIC] " + re.sub(r"\{\{c1::([^}]+)\}\}", r"\1", q.replace("[CLOZE]", "")).strip()
                a = normalize_basic_answer(a)
            else:
                a = normalize_cloze_answer(a)
        else:
            a = normalize_basic_answer(a)

        # limpeza extra
        a = re.sub(r"(^|\s)(-|\d+\))\s+", " ", a).strip()

        out = {"front": q, "back": a}
        if src:
            out["src"] = src
        normalized.append(out)

    return normalized


def pick_default_deck(deck_options: str) -> str:
    s = (deck_options or "General").strip()
    return s or "General"
