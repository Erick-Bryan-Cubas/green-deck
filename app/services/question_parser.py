# app/services/question_parser.py
"""
Parser para formato de questões AllInOne (kprim, mc, sc) do LLM.

Formato esperado do LLM:
QUESTION: <texto da pergunta>
TYPE: kprim|mc|sc
OPT_1: <texto da opção> [CORRECT]
OPT_2: <texto da opção>
OPT_3: <texto da opção> [CORRECT]
OPT_4: <texto da opção>
OPT_5: <texto da opção>
COMMENT: <explicação>
SOURCE: "<trecho literal>"
DOMAIN: <categoria>

(linha em branco entre questões)
"""

import json
import re
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Literal


QuestionType = Literal["kprim", "mc", "sc"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_id() -> str:
    return str(uuid.uuid4())


def parse_question_type(s: str) -> int:
    """Converte string de tipo para inteiro (0=kprim, 1=mc, 2=sc)."""
    s = (s or "").strip().lower()
    if s == "kprim" or s == "0":
        return 0
    if s == "mc" or s == "1":
        return 1
    if s == "sc" or s == "2":
        return 2
    # Default para sc se não reconhecido
    return 2


def qtype_to_str(qtype: int) -> str:
    """Converte inteiro de tipo para string."""
    if qtype == 0:
        return "kprim"
    if qtype == 1:
        return "mc"
    return "sc"


def compute_answers_field(qtype: int, options: List[Dict[str, Any]]) -> str:
    """
    Calcula o campo Answers baseado no tipo de questão.

    - kprim: "1100" (4 dígitos binários, 1=correto, 0=incorreto)
    - mc: "123" (índices das corretas, base 1)
    - sc: "2" (único índice correto, base 1)
    """
    if qtype == 0:
        # kprim: exatamente 4 opções, formato binário
        result = ""
        for i in range(4):
            if i < len(options) and options[i].get("isCorrect", False):
                result += "1"
            else:
                result += "0"
        return result

    elif qtype == 1:
        # mc: índices das corretas (1-indexed)
        correct_indices = []
        for i, opt in enumerate(options):
            if opt.get("isCorrect", False):
                correct_indices.append(str(i + 1))
        return "".join(correct_indices) if correct_indices else "1"

    else:
        # sc: único índice correto (1-indexed)
        for i, opt in enumerate(options):
            if opt.get("isCorrect", False):
                return str(i + 1)
        return "1"


def parse_questions_qa(text: str) -> List[Dict[str, Any]]:
    """
    Parseia saída do modelo no formato Q/A para questões.

    Aceita formatos:
    - QUESTION: / TYPE: / OPT_1: / COMMENT: / SOURCE: / DOMAIN:
    - Aliases: PERGUNTA, TIPO, OPCAO_1, COMENTARIO, FONTE, DOMINIO
    """
    if not text:
        return []

    t = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.strip() for ln in t.split("\n")]

    questions: List[Dict[str, Any]] = []

    # Estado atual
    cur_question = ""
    cur_type = "sc"
    cur_options: List[Dict[str, Any]] = []
    cur_comment = ""
    cur_source = ""
    cur_domain = ""
    mode = None  # "question" | "type" | "opt" | "comment" | "source" | "domain"
    cur_opt_idx = 0

    def flush():
        nonlocal cur_question, cur_type, cur_options, cur_comment, cur_source, cur_domain, mode, cur_opt_idx

        q = re.sub(r"\s+", " ", cur_question).strip()

        if q and len(cur_options) >= 2:
            qtype = parse_question_type(cur_type)

            # Para kprim, garantir exatamente 4 opções
            if qtype == 0:
                while len(cur_options) < 4:
                    cur_options.append({"text": "", "isCorrect": False})
                cur_options = cur_options[:4]

            # Garantir pelo menos uma opção correta
            has_correct = any(opt.get("isCorrect", False) for opt in cur_options)
            if not has_correct and cur_options:
                cur_options[0]["isCorrect"] = True

            questions.append({
                "id": _gen_id(),
                "question": q,
                "qtype": qtype,
                "options": cur_options,
                "answers": compute_answers_field(qtype, cur_options),
                "comment": re.sub(r"\s+", " ", cur_comment).strip(),
                "sources": re.sub(r"\s+", " ", cur_source).strip().strip('"').strip(),
                "domain": re.sub(r"\s+", " ", cur_domain).strip(),
                "deck": "General",
                "generatedAt": _now_iso()
            })

        # Reset
        cur_question = ""
        cur_type = "sc"
        cur_options = []
        cur_comment = ""
        cur_source = ""
        cur_domain = ""
        mode = None
        cur_opt_idx = 0

    for ln in lines:
        if not ln:
            # Linha em branco = possível boundary
            if cur_question and len(cur_options) >= 2:
                flush()
            continue

        # QUESTION: ou PERGUNTA:
        if re.match(r"(?i)^(question|pergunta|q)\s*:\s*", ln):
            if cur_question and len(cur_options) >= 2:
                flush()
            mode = "question"
            cur_question = re.sub(r"(?i)^(question|pergunta|q)\s*:\s*", "", ln).strip()
            continue

        # TYPE: ou TIPO:
        if re.match(r"(?i)^(type|tipo)\s*:\s*", ln):
            mode = "type"
            cur_type = re.sub(r"(?i)^(type|tipo)\s*:\s*", "", ln).strip()
            continue

        # OPT_N: ou OPCAO_N: ou Q_N:
        opt_match = re.match(r"(?i)^(opt|opcao|option|q)[\s_]*(\d+)\s*:\s*", ln)
        if opt_match:
            mode = "opt"
            cur_opt_idx = int(opt_match.group(2)) - 1
            opt_text = re.sub(r"(?i)^(opt|opcao|option|q)[\s_]*\d+\s*:\s*", "", ln).strip()

            # Verificar [CORRECT] ou [CORRETA]
            is_correct = bool(re.search(r"\[CORRECT\]|\[CORRETA\]|\[CERTO\]|\[V\]", opt_text, re.IGNORECASE))
            opt_text = re.sub(r"\s*\[CORRECT\]|\[CORRETA\]|\[CERTO\]|\[V\]\s*", "", opt_text, flags=re.IGNORECASE).strip()

            # Expandir lista se necessário
            while len(cur_options) <= cur_opt_idx:
                cur_options.append({"text": "", "isCorrect": False})

            cur_options[cur_opt_idx] = {"text": opt_text, "isCorrect": is_correct}
            continue

        # COMMENT: ou COMENTARIO: ou EXPLANATION:
        if re.match(r"(?i)^(comment|comentario|explanation|explicacao|feedback)\s*:\s*", ln):
            mode = "comment"
            cur_comment = re.sub(r"(?i)^(comment|comentario|explanation|explicacao|feedback)\s*:\s*", "", ln).strip()
            continue

        # SOURCE: ou FONTE:
        if re.match(r"(?i)^(source|fonte|src|ref)\s*:\s*", ln):
            mode = "source"
            cur_source = re.sub(r"(?i)^(source|fonte|src|ref)\s*:\s*", "", ln).strip()
            continue

        # DOMAIN: ou DOMINIO:
        if re.match(r"(?i)^(domain|dominio|categoria|area)\s*:\s*", ln):
            mode = "domain"
            cur_domain = re.sub(r"(?i)^(domain|dominio|categoria|area)\s*:\s*", "", ln).strip()
            continue

        # Continuação de linha
        if mode == "question":
            cur_question = (cur_question + " " + ln).strip()
        elif mode == "comment":
            cur_comment = (cur_comment + " " + ln).strip()
        elif mode == "source":
            cur_source = (cur_source + " " + ln).strip()
        elif mode == "domain":
            cur_domain = (cur_domain + " " + ln).strip()
        elif mode == "opt" and cur_opt_idx < len(cur_options):
            cur_options[cur_opt_idx]["text"] = (cur_options[cur_opt_idx]["text"] + " " + ln).strip()

    # Flush final
    if cur_question and len(cur_options) >= 2:
        flush()

    return questions


def parse_questions_json(text: str) -> List[Dict[str, Any]]:
    """
    Fallback: parseia questões quando o modelo devolve JSON.

    Aceita formatos:
    - [{"question":"...", "type":"sc", "options":[...], ...}, ...]
    - {"questions":[...]}
    """
    if not text:
        return []

    t = text.strip()
    if not t:
        return []

    data: Any = None

    # 1) Tenta extrair array JSON
    lb = t.find("[")
    rb = t.rfind("]")
    if lb != -1 and rb != -1 and rb > lb:
        candidate = t[lb : rb + 1]
        try:
            data = json.loads(candidate)
        except Exception:
            data = None

    # 2) Tenta objeto JSON
    if data is None:
        lc = t.find("{")
        rc = t.rfind("}")
        if lc != -1 and rc != -1 and rc > lc:
            candidate = t[lc : rc + 1]
            try:
                data = json.loads(candidate)
            except Exception:
                data = None

    if data is None:
        return []

    # Normaliza para lista
    if isinstance(data, dict):
        for k in ("questions", "items", "data", "resultado", "questoes"):
            if isinstance(data.get(k), list):
                data = data[k]
                break

    if not isinstance(data, list):
        return []

    questions: List[Dict[str, Any]] = []

    for item in data:
        if not isinstance(item, dict):
            continue

        # Extrair campos com aliases
        question = item.get("question") or item.get("pergunta") or item.get("q") or ""
        qtype_raw = item.get("type") or item.get("tipo") or item.get("qtype") or "sc"
        comment = item.get("comment") or item.get("comentario") or item.get("explanation") or item.get("feedback") or ""
        source = item.get("source") or item.get("fonte") or item.get("src") or ""
        domain = item.get("domain") or item.get("dominio") or item.get("categoria") or ""

        # Extrair opções
        options_raw = item.get("options") or item.get("opcoes") or item.get("alternatives") or []
        options: List[Dict[str, Any]] = []

        # Também aceitar Q_1, Q_2 etc diretamente
        if not options_raw:
            for i in range(1, 6):
                for key in [f"Q_{i}", f"q_{i}", f"opt_{i}", f"opcao_{i}"]:
                    if key in item:
                        opt_text = str(item[key])
                        is_correct = False
                        # Verificar answers field
                        answers = str(item.get("answers") or item.get("gabarito") or "")
                        if str(i) in answers:
                            is_correct = True
                        options.append({"text": opt_text, "isCorrect": is_correct})
                        break
        else:
            for opt in options_raw:
                if isinstance(opt, str):
                    options.append({"text": opt, "isCorrect": False})
                elif isinstance(opt, dict):
                    opt_text = opt.get("text") or opt.get("texto") or opt.get("label") or ""
                    is_correct = opt.get("isCorrect") or opt.get("correct") or opt.get("correta") or False
                    options.append({"text": str(opt_text), "isCorrect": bool(is_correct)})

        if not question or len(options) < 2:
            continue

        qtype = parse_question_type(str(qtype_raw))

        # Para kprim, garantir exatamente 4 opções
        if qtype == 0:
            while len(options) < 4:
                options.append({"text": "", "isCorrect": False})
            options = options[:4]

        # Garantir pelo menos uma opção correta
        has_correct = any(opt.get("isCorrect", False) for opt in options)
        if not has_correct and options:
            options[0]["isCorrect"] = True

        questions.append({
            "id": _gen_id(),
            "question": question,
            "qtype": qtype,
            "options": options,
            "answers": compute_answers_field(qtype, options),
            "comment": str(comment),
            "sources": str(source).strip('"'),
            "domain": str(domain),
            "deck": "General",
            "generatedAt": _now_iso()
        })

    return questions


def parse_questions(text: str) -> List[Dict[str, Any]]:
    """
    Tenta parsear questões primeiro como Q/A, depois como JSON.
    """
    # Tenta Q/A primeiro
    questions = parse_questions_qa(text)
    if questions:
        return questions

    # Fallback para JSON
    return parse_questions_json(text)


def normalize_questions(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Valida e normaliza estrutura de questões.
    Remove questões inválidas e corrige campos.
    """
    normalized: List[Dict[str, Any]] = []

    for q in questions:
        if not isinstance(q, dict):
            continue

        question_text = str(q.get("question", "")).strip()
        if not question_text:
            continue

        options = q.get("options", [])
        if not isinstance(options, list) or len(options) < 2:
            continue

        qtype = q.get("qtype", 2)
        if not isinstance(qtype, int) or qtype not in (0, 1, 2):
            qtype = 2

        # Normalizar opções
        norm_options = []
        for opt in options:
            if isinstance(opt, dict):
                text = str(opt.get("text", "")).strip()
                is_correct = bool(opt.get("isCorrect", False))
                norm_options.append({"text": text, "isCorrect": is_correct})
            elif isinstance(opt, str):
                norm_options.append({"text": opt.strip(), "isCorrect": False})

        if len(norm_options) < 2:
            continue

        # Para kprim, garantir exatamente 4 opções
        if qtype == 0:
            while len(norm_options) < 4:
                norm_options.append({"text": "", "isCorrect": False})
            norm_options = norm_options[:4]

        # Garantir pelo menos uma opção correta
        has_correct = any(opt.get("isCorrect", False) for opt in norm_options)
        if not has_correct:
            norm_options[0]["isCorrect"] = True

        normalized.append({
            "id": q.get("id") or _gen_id(),
            "question": question_text,
            "qtype": qtype,
            "options": norm_options,
            "answers": compute_answers_field(qtype, norm_options),
            "comment": str(q.get("comment", "")).strip(),
            "sources": str(q.get("sources", "")).strip().strip('"'),
            "domain": str(q.get("domain", "")).strip(),
            "deck": str(q.get("deck", "General")).strip() or "General",
            "generatedAt": q.get("generatedAt") or _now_iso()
        })

    return normalized


def validate_question(question: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Valida uma questão individual.
    Retorna (is_valid, error_message).
    """
    if not question.get("question"):
        return False, "Questão sem texto"

    options = question.get("options", [])
    if len(options) < 2:
        return False, "Questão precisa de pelo menos 2 opções"

    qtype = question.get("qtype", 2)

    if qtype == 0 and len(options) != 4:
        return False, "Questão Kprim precisa de exatamente 4 opções"

    has_correct = any(opt.get("isCorrect", False) for opt in options)
    if not has_correct:
        return False, "Questão precisa de pelo menos uma opção correta"

    # Para sc, verificar que há exatamente uma correta
    if qtype == 2:
        correct_count = sum(1 for opt in options if opt.get("isCorrect", False))
        if correct_count != 1:
            return False, "Questão de escolha única deve ter exatamente uma opção correta"

    return True, None
