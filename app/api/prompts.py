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
        "Voce gera flashcards CLOZE para Anki.\n"
        "REGRA: cada CLOZE pode ter uma ou multiplas lacunas: {{c1::termo}}, {{c2::termo}}, etc.\n"
        "Fora do SRC: pt-BR. No SRC: citacao literal de <SOURCE>.\n"
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
        "Gere APENAS cards cloze: frase afirmativa com uma ou mais lacunas {{c1::termo}}, {{c2::termo}}, etc.\n"
        "Use prefixo CLOZE: (nao Q:). Numere as lacunas sequencialmente."
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
CLOZE: <frase afirmativa em pt-BR com uma ou mais lacunas {{c1::termo}}, {{c2::termo}}, etc.>
EXTRA: <1 frase curta de contexto>
SRC: "<trecho literal de <SOURCE>>"

REGRAS:
- CLOZE pode ter multiplas lacunas numeradas sequencialmente: {{c1::}}, {{c2::}}, etc.
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
    # Flashcards: prompt principal de geracao (com delimitadores XML)
    # =========================
    "FLASHCARDS_GENERATION": """${guidelines}

<SOURCE>
${src}
</SOURCE>

<CONTEXT purpose="understanding_only">
${ctx_block}
</CONTEXT>

<CHECKLIST>
${checklist_block}
</CHECKLIST>

<INSTRUCTIONS>
- Gere entre ${target_min} e ${target_max} cards.
- APENAS use informacoes presentes em <SOURCE>.
- <CONTEXT> serve APENAS para compreensao do assunto - NAO crie cards baseados apenas em <CONTEXT>.
- Se a fonte estiver em ingles: traduza o card para pt-BR sem adicionar fatos.
- SRC deve ser citacao literal de <SOURCE>.
</INSTRUCTIONS>

<TYPE>
${type_instruction}
</TYPE>

<OUTPUT_FORMAT>
${format_block}
</OUTPUT_FORMAT>

<OUTPUT_RULES>
- Sem markdown/listas/numeracao.
- Uma linha em branco entre cards.
</OUTPUT_RULES>

COMECE:
""",

    # =========================
    # Flashcards: prompt de repair (com delimitadores XML)
    # =========================
    "FLASHCARDS_REPAIR": """${guidelines}

<SOURCE>
${src}
</SOURCE>

<CONTEXT purpose="understanding_only">
${ctx_block}
</CONTEXT>

<CHECKLIST>
${checklist_block}
</CHECKLIST>

<INSTRUCTIONS>
REFACA os cards obedecendo 100% ao FORMATO e as REGRAS:
- Cada card deve ser derivavel de <SOURCE>.
- SRC deve ser citacao literal de <SOURCE>.
- Entre ${target_min} e ${target_max} cards.
- <CONTEXT> serve APENAS para compreensao - NAO crie cards baseados apenas em <CONTEXT>.
</INSTRUCTIONS>

<OUTPUT_FORMAT>
${format_block}
</OUTPUT_FORMAT>

<OUTPUT_RULES>
- Apenas pt-BR fora do SRC.
- Sem markdown/listas/numeracao.
- Uma linha em branco entre cards.
</OUTPUT_RULES>

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

    "TEXT_ANALYSIS_SYSTEM": "Voce e um assistente de analise de texto educacional.",

    # =========================
    # Topic segmentation — marcação automática por tópico
    # =========================
    "TOPIC_SEGMENTATION_SYSTEM": (
        "Você segmenta texto educacional por tipo de conteúdo.\n"
        "Responda APENAS em JSON válido, sem explicações.\n"
        "Extraia trechos LITERAIS do texto fornecido.\n"
    ),

    "TOPIC_SEGMENTATION_PROMPT": """Identifique os tópicos educacionais mais importantes no texto abaixo.

CATEGORIAS (use estes IDs exatos):
- DEFINICAO: conceitos sendo definidos ou explicados
- EXEMPLO: casos práticos, ilustrações, cenários
- CONCEITO: ideias-chave, princípios fundamentais, teorias
- FORMULA: expressões matemáticas, equações, fórmulas
- PROCEDIMENTO: passos, processos, algoritmos, métodos
- COMPARACAO: contrastes, similaridades, diferenças

REGRAS IMPORTANTES:
1. Extraia TRECHOS LITERAIS do texto (50-200 caracteres cada)
2. Copie o texto EXATAMENTE como aparece - NÃO resuma nem modifique
3. Máximo 15 segmentos por texto
4. Cada trecho deve ser único e educacionalmente relevante
5. Use a categoria mais apropriada para cada trecho

TEXTO PARA SEGMENTAR:
${text}

RESPONDA apenas em JSON válido (sem markdown, sem explicações):
{
  "segments": [
    {"excerpt": "trecho literal copiado do texto", "category": "DEFINICAO", "custom_name": null},
    {"excerpt": "outro trecho literal do texto", "category": "CONCEITO", "custom_name": null}
  ]
}""",

    # =========================
    # Prompts de reescrita de cards com LLM
    # =========================
    "CARD_REWRITE_DENSIFY": """Reescreva este flashcard adicionando mais cloze deletions para tornar o aprendizado mais ativo.

<ORIGINAL_CARD>
Front: ${front}
Back: ${back}
</ORIGINAL_CARD>

<RULES>
- Identifique 2-4 termos-chave adicionais que podem virar cloze
- Use {{c1::...}}, {{c2::...}}, {{c3::...}} etc. para os termos
- Se ja existe {{c1::...}}, mantenha e adicione {{c2::...}}, {{c3::...}}
- Preserve o significado e a estrutura da frase
- NAO adicione informacoes que nao estao no card original
</RULES>

<OUTPUT_FORMAT>
Front: [frase com multiplos cloze]
Back: [contexto expandido se necessario]
</OUTPUT_FORMAT>

Responda APENAS no formato acima, sem explicacoes:
""",

    "CARD_REWRITE_SPLIT": """Divida este flashcard em multiplas lacunas cloze independentes na mesma frase.

<ORIGINAL_CARD>
Front: ${front}
Back: ${back}
</ORIGINAL_CARD>

<RULES>
- Cada conceito importante deve virar um cloze separado: {{c1::...}}, {{c2::...}}, {{c3::...}}
- Mantenha tudo na mesma frase
- Maximo 4 cloze por card
- Se o card original tem apenas 1 cloze, adicione mais 1-3 lacunas
- Numere sequencialmente: c1, c2, c3, c4
</RULES>

<OUTPUT_FORMAT>
Front: [frase com cloze separados]
Back: [breve contexto]
</OUTPUT_FORMAT>

Responda APENAS no formato acima, sem explicacoes:
""",

    "CARD_REWRITE_SIMPLIFY": """Simplifique este flashcard para focar no essencial.

<ORIGINAL_CARD>
Front: ${front}
Back: ${back}
</ORIGINAL_CARD>

<RULES>
- Reduza a complexidade da pergunta/resposta
- Mantenha apenas a informacao essencial
- Se for cloze com multiplas lacunas, reduza para apenas 1 ou 2
- Use linguagem clara e direta
</RULES>

<OUTPUT_FORMAT>
Front: [versao simplificada]
Back: [resposta curta]
</OUTPUT_FORMAT>

Responda APENAS no formato acima, sem explicacoes:
""",

    "CARD_REWRITE_SYSTEM": (
        "Voce e um assistente especializado em reescrever flashcards.\n"
        "Siga EXATAMENTE o formato de saida pedido.\n"
        "Responda em pt-BR.\n"
        "NAO adicione explicacoes ou comentarios.\n"
    ),

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
