# app/api/prompts.py

PROMPTS = {
    # =========================
    # Flashcards: system prompts (curtos e “duros”)
    # =========================
    "FLASHCARDS_SYSTEM_PTBR": (
        "Você gera flashcards para Anki.\n"
        "Fora do campo SRC: escreva SEMPRE em pt-BR.\n"
        "No campo SRC: COPIE literalmente do texto-fonte.\n"
        "NUNCA responda em espanhol.\n"
    ),

    "FLASHCARDS_SYSTEM_CLOZE": (
        "Você gera flashcards CLOZE para Anki.\n"
        "REGRA: toda linha CLOZE deve ter EXATAMENTE uma ocorrência de {{c1::termo}}.\n"
        "Fora do SRC: pt-BR. No SRC: citação literal.\n"
        "Cloze usa apenas CLOZE:/EXTRA:/SRC: (sem Q:/A:).\n"
        "NUNCA responda em espanhol.\n"
    ),

    # =========================
    # Flashcards: diretrizes essenciais (SuperMemo + Justin Sung, bem compacto)
    # =========================
    "FLASHCARDS_GUIDELINES": """Crie flashcards de alta retenção (SuperMemo) e que ajudem a formar rede de conhecimento (Justin Sung).

QUALIDADE:
- 1 ideia por card (mínimo de informação). Quebre conceitos grandes.
- Alta utilidade: definições, mecanismos, condições/limites, causa-efeito, comparações/contrastes, relações entre conceitos.
- Pergunta precisa (sem ambiguidade). Evite sim/não.
- Resposta mínima e completa (curta, direta).
- Evite listas longas: transforme em múltiplos cards.

ANCORAGEM:
- Crie cards SOMENTE do CONTEÚDO-FONTE.
- CONTEXTO GERAL é só para entendimento: NÃO vire card.
- SRC deve ser citação literal do CONTEÚDO-FONTE (pode estar em inglês). Fora do SRC: pt-BR.
""",

    # =========================
    # Flashcards: instruções por tipo
    # =========================
    "FLASHCARDS_TYPE_BASIC": "Gere APENAS cards básicos (Q/A). NÃO gere cloze.",
    "FLASHCARDS_TYPE_CLOZE": (
        "Gere APENAS cards cloze: frase afirmativa + UMA lacuna {{c1::termo}}.\n"
        "Use prefixo CLOZE: (não Q:)."
    ),
    "FLASHCARDS_TYPE_BOTH": "Para cada conceito importante: 1 básico (Q/A) + 1 cloze (CLOZE/EXTRA).",

    # =========================
    # Flashcards: blocos de formato (minimizados)
    # =========================
    "FLASHCARDS_FORMAT_BASIC": """FORMATO:
Q: <pergunta específica em pt-BR>
A: <resposta curta em pt-BR>
SRC: "<trecho literal do CONTEÚDO-FONTE>"

REGRAS:
- Sem {{c1::...}}.
- Não crie cloze.
""",

    "FLASHCARDS_FORMAT_CLOZE": """FORMATO:
CLOZE: <frase afirmativa em pt-BR com UMA lacuna {{c1::termo}}>
EXTRA: <1 frase curta de contexto>
SRC: "<trecho literal do CONTEÚDO-FONTE>"

REGRAS:
- CLOZE deve conter EXATAMENTE uma ocorrência de {{c1::}}.
- Nunca use Q:/A:.
""",

    "FLASHCARDS_FORMAT_BOTH": """FORMATO:

BÁSICO:
Q: <pt-BR>
A: <pt-BR curto>
SRC: "<literal do CONTEÚDO-FONTE>"

CLOZE:
CLOZE: <pt-BR afirmativo com UMA lacuna {{c1::termo}}>
EXTRA: <pt-BR curto>
SRC: "<literal do CONTEÚDO-FONTE>"
""",

    # =========================
    # Flashcards: prompt principal de geração (curto, sem redundância)
    # =========================
    "FLASHCARDS_GENERATION": """${guidelines}

FONTE (única base válida):
${src}

${ctx_block}

${checklist_block}

TAREFA:
- Gere entre ${target_min} e ${target_max} cards.
- Se a fonte estiver em inglês: traduza o card para pt-BR sem adicionar fatos.
- SRC sempre literal da fonte.

TIPO:
${type_instruction}

${format_block}

SAÍDA:
- Sem markdown/listas/numeração.
- Uma linha em branco entre cards.

COMECE:
""",

    # =========================
    # Flashcards: prompt de repair (curto e assertivo)
    # =========================
    "FLASHCARDS_REPAIR": """${guidelines}

FONTE (única base válida):
${src}

${ctx_block}

${checklist_block}

REFAÇA os cards obedecendo 100% ao FORMATO e às REGRAS:
- Cada card deve ser derivável da FONTE.
- SRC literal copiado da FONTE.
- Entre ${target_min} e ${target_max} cards.

${format_block}

SAÍDA:
- Apenas pt-BR fora do SRC.
- Sem markdown/listas/numeração.
- Uma linha em branco entre cards.

COMECE (sem explicar):
""",

    # =========================
    # Validação SRC (LLM) — valida ancoragem no texto selecionado
    # =========================
    "SRC_VALIDATION_PROMPT": """Valide se cada card está ancorado no TEXTO SELECIONADO.

TEXTO SELECIONADO (fonte única):
---BEGIN_SELECTED_TEXT---
${src_text}
---END_SELECTED_TEXT---

CARDS:
${cards_text}

REGRAS DE APROVAÇÃO (SIM):
- SRC não-vazio e corresponde a trecho do texto (aceite variações de pontuação/espaços/caixa).
- O conceito principal do FRONT está presente ou é claramente derivável do texto.
- Reformulações e sinônimos são aceitos se o significado está no texto.

REGRAS DE REJEIÇÃO (NÃO):
- SRC vazio ou não encontrado no texto.
- Card introduz conceito/termo técnico que NÃO aparece no texto (ex: menciona "SGBD" mas texto não menciona).
- Card faz afirmação factual não suportada pelo texto.

RESPONDA 1 linha por card:
CARD_N: SIM|NÃO | motivo (máx 10 palavras)

INICIE:
""",

    "SRC_VALIDATION_SYSTEM": (
        "Você é um validador de flashcards.\n"
        "Aprove cards bem ancorados no texto.\n"
        "Rejeite apenas se o conceito claramente não está no texto.\n"
        "Responda APENAS no formato pedido.\n"
    ),

    # =========================
    # Relevance filter (LLM) — valida se informação está no texto
    # =========================
    "RELEVANCE_FILTER_PROMPT": """Verifique se cada card contém informação presente no TEXTO-FONTE.

TEXTO-FONTE:
${src_text}

CARDS:
${cards_text}

APROVAR (SIM): informação do card está explícita ou claramente implícita no texto.
REJEITAR (NÃO): card adiciona fatos externos, faz extrapolação ou menciona conceitos não presentes.

Responda 1 linha por card:
N: SIM|NÃO | motivo breve (se NÃO)

RESPONDA:
""",

    "RELEVANCE_FILTER_SYSTEM": (
        "Você valida a relevância de flashcards.\n"
        "Aprove cards com informação presente no texto.\n"
        "Responda no formato: N: SIM|NÃO | motivo\n"
    ),

    # =========================
    # Text analysis — compacto
    # =========================
    "TEXT_ANALYSIS_PT": """Extraia os conceitos mais importantes do texto para criar flashcards (definições, mecanismos, relações, contrastes).

TEXTO:
${text}

Retorne um resumo estruturado e curto (3–7 bullets).
""",

    "TEXT_ANALYSIS_EN": """Extract the most important concepts for flashcards (definitions, mechanisms, relations, contrasts).

TEXT:
${text}

Return a short structured summary (3–7 bullets).
""",

    "TEXT_ANALYSIS_SYSTEM": "Você é um assistente de análise de texto educacional.",

}


def get_default_prompts_for_ui() -> dict:
    """
    Retorna os prompts padrão formatados para exibição no frontend.
    O usuário pode editar esses prompts antes de enviar a requisição.
    
    Returns:
        Dict com os prompts padrão organizados por categoria
    """
    return {
        "system": {
            "basic": PROMPTS["FLASHCARDS_SYSTEM_PTBR"],
            "cloze": PROMPTS["FLASHCARDS_SYSTEM_CLOZE"],
            "description": "Prompt de sistema que define o comportamento base do modelo",
        },
        "guidelines": {
            "default": PROMPTS["FLASHCARDS_GUIDELINES"],
            "description": "Diretrizes de qualidade para criação de flashcards (SuperMemo + Justin Sung)",
        },
        "generation": {
            "default": PROMPTS["FLASHCARDS_GENERATION"],
            "description": "Template principal de geração. Variáveis: ${src}, ${ctx_block}, ${guidelines}, ${target_min}, ${target_max}, ${type_instruction}, ${format_block}, ${checklist_block}",
        },
        "format": {
            "basic": PROMPTS["FLASHCARDS_FORMAT_BASIC"],
            "cloze": PROMPTS["FLASHCARDS_FORMAT_CLOZE"],
            "both": PROMPTS["FLASHCARDS_FORMAT_BOTH"],
            "description": "Formatos de saída esperados por tipo de card",
        },
        "type_instruction": {
            "basic": PROMPTS["FLASHCARDS_TYPE_BASIC"],
            "cloze": PROMPTS["FLASHCARDS_TYPE_CLOZE"],
            "both": PROMPTS["FLASHCARDS_TYPE_BOTH"],
            "description": "Instruções específicas por tipo de card",
        },
    }
