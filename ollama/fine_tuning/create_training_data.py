# ollama/fine_tuning/create_training_data.py
import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Literal, Optional


# Mantém alinhado com o comportamento do app:
# - Fora do SRC: pt-BR
# - No SRC: cópia literal do texto-fonte (pode estar em inglês)
SYSTEM_PTBR = (
    "Você é um gerador de flashcards.\n"
    "Fora do campo SRC, escreva SEMPRE em Português do Brasil (pt-BR).\n"
    "No campo SRC, COPIE literalmente do texto-fonte (pode estar em inglês).\n"
    "NUNCA responda em espanhol.\n"
)

CHATML_TEMPLATE = """<|im_start|>system
{system}
<|im_end|>
<|im_start|>user
{user}
<|im_end|>
<|im_start|>assistant
{assistant}
<|im_end|>
"""


@dataclass
class TrainingExample:
    source_text: str
    assistant_output: str  # pode ser QA/SRC ou JSON (dependendo do --format)
    context: str = ""


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _extract_src_lines_from_qa(assistant_text: str) -> List[str]:
    # aceita SRC:/FONTE:/REF:
    refs = []
    for ln in assistant_text.splitlines():
        m = re.match(r"(?i)^(src|fonte|ref)\s*:\s*(.+)$", ln.strip())
        if m:
            ref = m.group(2).strip().strip('"').strip()
            refs.append(ref)
    return refs


def _is_src_valid(ref: str, src_text: str) -> bool:
    ref = (ref or "").strip().strip('"').strip()
    if not ref:
        return False
    wc = len(ref.split())
    if wc < 5 or wc > 25:
        return False
    return _norm_ws(ref) in _norm_ws(src_text)


def _validate_src_in_example(example: TrainingExample, fmt: Literal["qa", "json"]) -> None:
    if fmt == "qa":
        refs = _extract_src_lines_from_qa(example.assistant_output)
        # Se não houver SRC, não falha (mas fica menos alinhado com o app).
        for r in refs:
            if not _is_src_valid(r, example.source_text):
                raise ValueError(
                    f"SRC inválido ou não encontrado no texto-fonte.\n"
                    f"SRC: {r}\n"
                    f"Texto-fonte (início): {example.source_text[:220]}..."
                )
    else:
        # JSON: tenta pegar src nos itens, se existir
        t = example.assistant_output.strip()
        data = json.loads(t)
        if isinstance(data, dict) and isinstance(data.get("cards"), list):
            data = data["cards"]
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and isinstance(item.get("src"), str):
                    r = item["src"].strip().strip('"').strip()
                    if r and not _is_src_valid(r, example.source_text):
                        raise ValueError(
                            f"SRC inválido ou não encontrado no texto-fonte.\n"
                            f"SRC: {r}\n"
                            f"Texto-fonte (início): {example.source_text[:220]}..."
                        )


def _build_user_prompt(source_text: str, context: str, card_type: str, fmt: str) -> str:
    card_type = (card_type or "both").strip().lower()
    if card_type not in ("basic", "cloze", "both"):
        card_type = "both"

    type_instruction = {
        "basic": "Gere APENAS cards [BASIC].",
        "cloze": "Gere APENAS cards [CLOZE].",
        "both": "Para cada conceito importante, gere 1 [BASIC] + 1 [CLOZE].",
    }[card_type]

    if fmt == "qa":
        return f"""
CONTEÚDO-FONTE (use SOMENTE isso como base):
{source_text}

{("CONTEXTO (opcional):\n" + context) if context else ""}

TAREFA:
- Crie flashcards em PT-BR BASEADOS APENAS no CONTEÚDO-FONTE.
- Se algo não estiver no texto, NÃO invente.
- Se o texto estiver em inglês, traduza os conceitos para PT-BR (sem adicionar fatos).
- IMPORTANTE: O campo SRC é uma CITAÇÃO LITERAL do texto-fonte; se o texto-fonte estiver em inglês, o SRC ficará em inglês (isso é permitido).
- Fora do campo SRC, NUNCA use inglês.

QUANTIDADE:
- Gere entre 6 e 12 cards.

TIPOS:
{type_instruction}

FORMATO OBRIGATÓRIO:
Q: [BASIC] <pergunta específica em PT-BR>
A: <resposta curta em PT-BR (1-2 frases)>
SRC: "<trecho COPIADO do CONTEÚDO-FONTE (5-25 palavras), sem alterar>"

Q: [CLOZE] <frase em PT-BR com UMA lacuna {{c1::termo}}>
A: Extra: <1 frase de contexto adicional em PT-BR>
SRC: "<trecho COPIADO do CONTEÚDO-FONTE (5-25 palavras), sem alterar>"

REGRAS CRÍTICAS:
- SEM markdown, SEM listas, SEM numeração.
- Uma linha em branco entre cards.
- O campo SRC PRECISA ser um trecho literal do texto-fonte (5–25 palavras).

COMECE:
""".strip()
    else:
        # JSON (compatível com a ideia original do script antigo)
        return f"""
Crie flashcards de repetição espaçada em Português do Brasil (pt-BR) baseados SOMENTE no texto abaixo.
Se o texto estiver em inglês, traduza os conceitos para PT-BR (sem adicionar fatos).

TIPOS:
{type_instruction}

FORMATO:
- Responda SOMENTE com uma lista JSON (array) de objetos.
- Cada objeto DEVE conter:
  - "front": string (comece com "[BASIC]" ou "[CLOZE]")
  - "back": string (para CLOZE, comece com "Extra:")
  - "deck": string
  - "src": string (trecho literal do texto-fonte; 5-25 palavras)

Texto:
{source_text}
""".strip()


def _default_examples(fmt: Literal["qa", "json"]) -> List[TrainingExample]:
    # Exemplos PT-BR (com SRC validável) + 1 exemplo com texto-fonte em inglês
    ex: List[TrainingExample] = []

    src1 = (
        "HTTP (Hypertext Transfer Protocol) é um protocolo de aplicação usado para transferir dados na web. "
        "Ele segue o modelo cliente-servidor e usa métodos como GET e POST. "
        "O método GET recupera recursos, enquanto POST envia dados ao servidor."
    )

    if fmt == "qa":
        out1 = """Q: [BASIC] O que é HTTP?
A: HTTP é um protocolo de aplicação usado para transferir dados na web no modelo cliente-servidor.
SRC: "HTTP (Hypertext Transfer Protocol) é um protocolo de aplicação usado"

Q: [BASIC] Para que serve o método GET em HTTP?
A: Serve para recuperar recursos em uma requisição HTTP.
SRC: "O método GET recupera recursos, enquanto POST envia dados"

Q: [CLOZE] Em HTTP, o método {{c1::POST}} é usado para enviar dados ao servidor.
A: Extra: Ele é comum em formulários e APIs que recebem payload.
SRC: "enquanto POST envia dados ao servidor"
"""
    else:
        out1 = json.dumps(
            [
                {
                    "front": "[BASIC] O que é HTTP?",
                    "back": "HTTP é um protocolo de aplicação usado para transferir dados na web no modelo cliente-servidor.",
                    "deck": "Redes::HTTP",
                    "src": "HTTP (Hypertext Transfer Protocol) é um protocolo de aplicação usado",
                },
                {
                    "front": "[BASIC] Para que serve o método GET em HTTP?",
                    "back": "Serve para recuperar recursos em uma requisição HTTP.",
                    "deck": "Redes::HTTP",
                    "src": "O método GET recupera recursos, enquanto POST envia dados",
                },
                {
                    "front": "[CLOZE] Em HTTP, o método {{c1::POST}} é usado para enviar dados ao servidor.",
                    "back": "Extra: Ele é comum em formulários e APIs que recebem payload.",
                    "deck": "Redes::HTTP",
                    "src": "enquanto POST envia dados ao servidor",
                },
            ],
            ensure_ascii=False,
            indent=2,
        )

    ex.append(TrainingExample(source_text=src1, assistant_output=out1))

    src2 = (
        "Gradiente descendente é um algoritmo de otimização que ajusta parâmetros para minimizar uma função de custo. "
        "Ele atualiza os parâmetros na direção oposta ao gradiente, com um passo controlado pela taxa de aprendizado."
    )

    if fmt == "qa":
        out2 = """Q: [BASIC] O que é gradiente descendente?
A: É um algoritmo de otimização que ajusta parâmetros para minimizar uma função de custo.
SRC: "Gradiente descendente é um algoritmo de otimização que ajusta parâmetros"

Q: [CLOZE] No gradiente descendente, os parâmetros são atualizados na direção {{c1::oposta}} ao gradiente.
A: Extra: A taxa de aprendizado controla o tamanho do passo da atualização.
SRC: "na direção oposta ao gradiente, com um passo controlado"
"""
    else:
        out2 = json.dumps(
            [
                {
                    "front": "[BASIC] O que é gradiente descendente?",
                    "back": "É um algoritmo de otimização que ajusta parâmetros para minimizar uma função de custo.",
                    "deck": "ML::Otimização",
                    "src": "Gradiente descendente é um algoritmo de otimização que ajusta parâmetros",
                },
                {
                    "front": "[CLOZE] No gradiente descendente, os parâmetros são atualizados na direção {{c1::oposta}} ao gradiente.",
                    "back": "Extra: A taxa de aprendizado controla o tamanho do passo da atualização.",
                    "deck": "ML::Otimização",
                    "src": "na direção oposta ao gradiente, com um passo controlado",
                },
            ],
            ensure_ascii=False,
            indent=2,
        )

    ex.append(TrainingExample(source_text=src2, assistant_output=out2))

    # Texto-fonte em inglês (SRC em inglês, resto em pt-BR), como permitido pelo app :contentReference[oaicite:4]{index=4}
    src3 = (
        "Backpropagation computes gradients efficiently using the chain rule. "
        "It is the standard method for training neural networks with gradient-based optimization."
    )

    if fmt == "qa":
        out3 = """Q: [BASIC] O que a retropropagação (backpropagation) calcula de forma eficiente?
A: Ela calcula gradientes de forma eficiente usando a regra da cadeia.
SRC: "computes gradients efficiently using the chain rule"

Q: [CLOZE] A retropropagação é o método padrão para treinar redes neurais com otimização {{c1::baseada em gradiente}}.
A: Extra: Ela viabiliza atualizar pesos a partir do erro de saída.
SRC: "training neural networks with gradient-based optimization"
"""
    else:
        out3 = json.dumps(
            [
                {
                    "front": "[BASIC] O que a retropropagação (backpropagation) calcula de forma eficiente?",
                    "back": "Ela calcula gradientes de forma eficiente usando a regra da cadeia.",
                    "deck": "DL::Treinamento",
                    "src": "computes gradients efficiently using the chain rule",
                },
                {
                    "front": "[CLOZE] A retropropagação é o método padrão para treinar redes neurais com otimização {{c1::baseada em gradiente}}.",
                    "back": "Extra: Ela viabiliza atualizar pesos a partir do erro de saída.",
                    "deck": "DL::Treinamento",
                    "src": "training neural networks with gradient-based optimization",
                },
            ],
            ensure_ascii=False,
            indent=2,
        )

    ex.append(TrainingExample(source_text=src3, assistant_output=out3))
    return ex


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="training_data_formatted.jsonl",
        help="Arquivo JSONL de saída (campo 'text' com ChatML).",
    )
    parser.add_argument(
        "--format",
        choices=["qa", "json"],
        default="qa",
        help="Formato do assistant_output nos exemplos.",
    )
    parser.add_argument(
        "--card-type",
        choices=["basic", "cloze", "both"],
        default="both",
        help="Instrução de tipos colocada no prompt do usuário.",
    )
    parser.add_argument(
        "--no-validate-src",
        action="store_true",
        help="Desliga validação de SRC (não recomendado).",
    )
    args = parser.parse_args()

    examples = _default_examples(args.format)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as f:
        for ex in examples:
            user_prompt = _build_user_prompt(
                source_text=ex.source_text,
                context=ex.context,
                card_type=args.card_type,
                fmt=args.format,
            )

            if not args.no_validate_src:
                _validate_src_in_example(ex, args.format)

            formatted = CHATML_TEMPLATE.format(
                system=SYSTEM_PTBR.strip(),
                user=user_prompt.strip(),
                assistant=ex.assistant_output.strip(),
            )
            f.write(json.dumps({"text": formatted}, ensure_ascii=False) + "\n")

    print(f"✅ {len(examples)} exemplos gerados em: {out_path.resolve()}")


if __name__ == "__main__":
    main()
