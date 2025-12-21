from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import json
from app.config import OLLAMA_MODEL, OLLAMA_ANALYSIS_MODEL, MAX_CTX_CHARS
from app.services.ollama import ollama_generate_stream
from app.services.parser import parse_flashcards_qa, normalize_cards, pick_default_deck
from app.utils.text import truncate_source, looks_english
from app.services.storage import save_analysis, save_cards

router = APIRouter(prefix="/api", tags=["flashcards"])

class TextRequest(BaseModel):
    text: str

class CardsRequest(BaseModel):
    text: str
    textContext: Optional[str] = ""
    deckOptions: Optional[str] = "General"
    useRAG: Optional[bool] = False
    topK: Optional[int] = 0

@router.post("/analyze-text-stream")
async def analyze_text_stream(request: TextRequest):
    async def generate():
        try:
            from app.services.ollama import ollama_embed, chunk_text, cosine_similarity
            
            yield f"event: progress\ndata: {json.dumps({'percent': 10, 'stage': 'preparing'})}\n\n"

            src = truncate_source(request.text or "")
            chunks = chunk_text(src, chunk_size=400)
            
            yield f"event: progress\ndata: {json.dumps({'percent': 30, 'stage': 'embedding'})}\n\n"
            
            # Gerar embeddings para cada chunk
            chunk_embeddings = []
            for chunk in chunks:
                emb = await ollama_embed(OLLAMA_ANALYSIS_MODEL, chunk)
                chunk_embeddings.append((chunk, emb))
            
            # Query para extrair informações relevantes
            query = "conceitos importantes, definições técnicas, contrastes e distinções"
            query_emb = await ollama_embed(OLLAMA_ANALYSIS_MODEL, query)
            
            yield f"event: progress\ndata: {json.dumps({'percent': 60, 'stage': 'ranking'})}\n\n"
            
            # Ranquear chunks por relevância
            scored = [(chunk, cosine_similarity(emb, query_emb)) for chunk, emb in chunk_embeddings]
            scored.sort(key=lambda x: x[1], reverse=True)
            
            # Pegar top 3 chunks mais relevantes
            top_chunks = [chunk for chunk, _ in scored[:3]]
            summary = "\n\n".join(top_chunks)
            
            result = {"content": [{"type": "text", "text": summary}]}
            
            # Salvar análise
            analysis_id = save_analysis(src, summary, {"chunks": len(chunks), "top_chunks": len(top_chunks)})
            result["analysis_id"] = analysis_id
            
            yield f"event: progress\ndata: {json.dumps({'percent': 100, 'stage': 'done'})}\n\n"
            yield f"event: result\ndata: {json.dumps(result)}\n\n"

        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

@router.post("/generate-cards-stream")
async def generate_cards_stream(request: CardsRequest):
    async def generate():
        try:
            yield f"event: stage\ndata: {json.dumps({'stage': 'generation_started'})}\n\n"

            src = truncate_source(request.text or "")
            ctx = (request.textContext or "").strip()

            prompt = f"""
CONTEÚDO-FONTE:
{src}

{("CONTEXTO (opcional):\n" + ctx) if ctx else ""}

TAREFA CRÍTICA:
Você DEVE gerar NO MÍNIMO 20-40 flashcards (ou mais se o texto for longo) cobrindo EXAUSTIVAMENTE:

1. TODOS os contrastes mencionados (ex: "X vs Y", "diferença entre A e B")
2. TODAS as definições de termos técnicos
3. TODAS as armadilhas, trade-offs e exceções
4. TODOS os exemplos e casos práticos
5. TODAS as nuances e detalhes técnicos

Para CADA conceito importante, crie MÚLTIPLOS cards (1 BASIC + 1-2 CLOZE).

FORMATO OBRIGATÓRIO:
Q: [BASIC] <pergunta específica em PT-BR>
A: <resposta curta em PT-BR, 1-2 frases>

Q: [CLOZE] <frase com {{{{c1::termo}}}} em PT-BR>
A: Extra: <contexto adicional em PT-BR>

EXEMPLOS CORRETOS:

Q: [BASIC] Qual a diferença fundamental entre data leakage e training-serving skew?
A: Data leakage ocorre quando o treino vê informação do futuro; training-serving skew é quando features são calculadas diferentemente entre treino e produção.

Q: [CLOZE] {{{{c1::Calibração}}}} significa que quando o modelo diz 0.2, cerca de 20% dos casos são positivos.
A: Extra: Calibração não garante bom ranking; um modelo pode ser bem calibrado mas ordenar mal os itens.

Q: [BASIC] Por que melhorar CTR pode piorar a margem líquida?
A: Porque aumentar CTR pode gerar mais cliques mas também aumentar devoluções, frete e custos de incentivo sem retorno real.

Q: [CLOZE] {{{{c1::Selection bias}}}} ocorre quando só observamos labels para itens que foram expostos pela política anterior.
A: Extra: Diferente de confounding, onde observamos alternativas mas a comparação é injusta devido a variável de confusão.

REGRAS CRÍTICAS:
- SEMPRE em PT-BR (nunca inglês)
- SEMPRE prefixe [BASIC] ou [CLOZE]
- Cloze: exatamente UMA lacuna {{{{c1::...}}}}
- Respostas curtas (10-25 palavras)
- NÃO PARE até cobrir TODO o conteúdo (mínimo 20 cards)
- Sem listas, sem markdown, sem numeração
- Uma linha em branco entre cards

IMPORTANTE: Gere cards até ESGOTAR o conteúdo. Não economize!

COMECE AGORA (lembre-se: mínimo 20 cards):
""".strip()

            raw = ""
            # Forçar geração mais longa
            options = {"num_predict": 4096, "temperature": 0.2}
            async for piece in ollama_generate_stream(OLLAMA_MODEL, prompt, system=None, options=options):
                raw += piece

            cards = parse_flashcards_qa(raw)
            cards = normalize_cards(cards)

            # Validar quantidade mínima de cards
            min_expected = max(10, len(src.split()) // 100)  # ~1 card por 100 palavras
            
            if not cards or looks_english(raw) or len(cards) < min_expected:
                yield f"event: stage\ndata: {json.dumps({'stage': 'repair_pass', 'reason': f'cards={len(cards)}, min={min_expected}'})}\n\n"
                repair_prompt = f"""
A saída abaixo está INCOMPLETA ou INCORRETA (gerou apenas {len(cards)} cards, esperado mínimo {min_expected}).

Reescreva em PT-BR seguindo RIGOROSAMENTE e gerando MUITO MAIS cards:

FORMATO:
Q: [BASIC] <pergunta em PT-BR>
A: <resposta em PT-BR>

Q: [CLOZE] <frase com {{{{c1::termo}}}} em PT-BR>
A: Extra: <contexto em PT-BR>

PROIBIDO:
- Inglês
- Listas (bullets, números)
- Markdown
- "Question:", "Answer:"
- Múltiplas lacunas cloze

SAÍDA INCORRETA:
{raw}

REESCREVA CORRETAMENTE EM PT-BR:
""".strip()

                raw2 = ""
                async for piece in ollama_generate_stream(OLLAMA_MODEL, repair_prompt, system=None, options=None):
                    raw2 += piece

                cards2 = normalize_cards(parse_flashcards_qa(raw2))
                if cards2:
                    cards = cards2

            deck = pick_default_deck(request.deckOptions or "General")
            result_cards = [{"front": c["front"], "back": c["back"], "deck": deck} for c in cards]

            # Salvar cards
            cards_id = save_cards(result_cards, source_text=src)
            
            yield f"event: stage\ndata: {json.dumps({'stage': 'done', 'total_cards': len(result_cards), 'cards_id': cards_id})}\n\n"
            yield f"event: result\ndata: {json.dumps({'success': True, 'cards': result_cards})}\n\n"

        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
