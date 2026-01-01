"""
Módulo de persistência unificado usando apenas DuckDB.

Todas as operações de armazenamento (analyses, cards, llm_responses, filter_results)
são feitas exclusivamente no DuckDB para simplicidade e performance.
"""
import json
import duckdb
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

DATA_DIR = Path("data/generator")
DB_PATH = Path("data/storage.duckdb")


def _ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _get_connection():
    """
    Retorna conexão DuckDB com todas as tabelas criadas.
    Esta é a única fonte de persistência do sistema.
    """
    _ensure_data_dir()
    conn = duckdb.connect(str(DB_PATH))
    
    # Tabela de análises de texto
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analyses (
            id VARCHAR PRIMARY KEY,
            timestamp TIMESTAMP,
            text TEXT,
            summary TEXT,
            metadata TEXT
        )
    """)
    
    # Tabela de cards finais (após todos os filtros)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            id VARCHAR PRIMARY KEY,
            timestamp TIMESTAMP,
            analysis_id VARCHAR,
            source_text TEXT,
            cards_count INTEGER,
            cards TEXT
        )
    """)
    
    # Tabela de respostas brutas do LLM (com campos expandidos para debug)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS llm_responses (
            id VARCHAR PRIMARY KEY,
            timestamp TIMESTAMP,
            provider VARCHAR,
            model VARCHAR,
            prompt TEXT,
            response TEXT,
            cards_id VARCHAR,
            analysis_id VARCHAR,
            system_prompt TEXT,
            card_type VARCHAR,
            prompt_length INTEGER,
            response_length INTEGER,
            source_text_length INTEGER,
            options TEXT
        )
    """)
    
    # Adiciona novas colunas se não existirem (para DBs existentes)
    try:
        conn.execute("ALTER TABLE llm_responses ADD COLUMN IF NOT EXISTS system_prompt TEXT")
        conn.execute("ALTER TABLE llm_responses ADD COLUMN IF NOT EXISTS card_type VARCHAR")
        conn.execute("ALTER TABLE llm_responses ADD COLUMN IF NOT EXISTS prompt_length INTEGER")
        conn.execute("ALTER TABLE llm_responses ADD COLUMN IF NOT EXISTS response_length INTEGER")
        conn.execute("ALTER TABLE llm_responses ADD COLUMN IF NOT EXISTS source_text_length INTEGER")
        conn.execute("ALTER TABLE llm_responses ADD COLUMN IF NOT EXISTS options TEXT")
    except:
        pass  # Colunas já existem
    
    # Tabela de requests de geração (entrada do usuário)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS generation_requests (
            id VARCHAR PRIMARY KEY,
            timestamp TIMESTAMP,
            analysis_id VARCHAR,
            source_text TEXT,
            context_text TEXT,
            card_type VARCHAR,
            model VARCHAR,
            provider VARCHAR,
            source_type VARCHAR,
            word_count INTEGER,
            target_min INTEGER,
            target_max INTEGER
        )
    """)
    
    # Tabela de pipeline de geração (rastreia cada etapa)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS generation_pipeline (
            id VARCHAR PRIMARY KEY,
            timestamp TIMESTAMP,
            request_id VARCHAR,
            analysis_id VARCHAR,
            stage VARCHAR,
            cards_in INTEGER,
            cards_out INTEGER,
            duration_ms INTEGER,
            details TEXT
        )
    """)
    
    # Tabela de resultados de filtragem (cards mantidos/removidos)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS filter_results (
            id VARCHAR PRIMARY KEY,
            timestamp TIMESTAMP,
            cards_id VARCHAR,
            analysis_id VARCHAR,
            filter_type VARCHAR,
            cards_before INTEGER,
            cards_after INTEGER,
            kept_cards TEXT,
            removed_cards TEXT,
            filter_metadata TEXT
        )
    """)
    
    return conn

def save_analysis(text: str, summary: str, metadata: Optional[Dict] = None) -> str:
    """Salva análise de texto no DuckDB."""
    analysis_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    timestamp = datetime.now()
    
    conn = _get_connection()
    conn.execute("""
        INSERT INTO analyses (id, timestamp, text, summary, metadata)
        VALUES (?, ?, ?, ?, ?)
    """, [analysis_id, timestamp, text, summary, json.dumps(metadata or {})])
    conn.close()
    
    return analysis_id


def save_cards(cards: List[Dict], analysis_id: Optional[str] = None, source_text: Optional[str] = None) -> str:
    """Salva cards finais (após todos os filtros) no DuckDB."""
    cards_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    timestamp = datetime.now()
    
    conn = _get_connection()
    conn.execute("""
        INSERT INTO cards (id, timestamp, analysis_id, source_text, cards_count, cards)
        VALUES (?, ?, ?, ?, ?, ?)
    """, [cards_id, timestamp, analysis_id or "", source_text or "", len(cards), json.dumps(cards)])
    conn.close()
    
    return cards_id

def get_recent_analyses(limit: int = 10) -> List[Dict]:
    conn = _get_connection()
    result = conn.execute("""
        SELECT id, timestamp, text, summary, metadata
        FROM analyses
        ORDER BY timestamp DESC
        LIMIT ?
    """, [limit]).fetchall()
    conn.close()
    
    return [{"id": r[0], "timestamp": r[1].isoformat(), "text": r[2], "summary": r[3], "metadata": json.loads(r[4])} for r in result]

def get_recent_cards(limit: int = 10) -> List[Dict]:
    conn = _get_connection()
    result = conn.execute("""
        SELECT id, timestamp, analysis_id, source_text, cards_count, cards
        FROM cards
        ORDER BY timestamp DESC
        LIMIT ?
    """, [limit]).fetchall()
    conn.close()
    
    return [{"id": r[0], "timestamp": r[1].isoformat(), "analysis_id": r[2], "source_text": r[3], "cards_count": str(r[4]), "cards": json.loads(r[5])} for r in result]

def get_stats() -> Dict:
    """Retorna estatísticas gerais do sistema."""
    conn = _get_connection()
    analyses_count = conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
    cards_count = conn.execute("SELECT SUM(cards_count) FROM cards").fetchone()[0] or 0
    filter_count = conn.execute("SELECT COUNT(*) FROM filter_results").fetchone()[0]
    llm_responses_count = conn.execute("SELECT COUNT(*) FROM llm_responses").fetchone()[0]
    conn.close()
    
    return {
        "total_analyses": analyses_count,
        "total_cards": cards_count,
        "total_filter_operations": filter_count,
        "total_llm_responses": llm_responses_count,
        "db_path": str(DB_PATH.absolute())
    }


def save_llm_response(
    provider: str, 
    model: str, 
    prompt: str, 
    response: str, 
    cards_id: Optional[str] = None, 
    analysis_id: Optional[str] = None,
    system_prompt: Optional[str] = None,
    card_type: Optional[str] = None,
    source_text_length: Optional[int] = None,
    options: Optional[Dict] = None
) -> str:
    """Salva resposta bruta do LLM no DuckDB com campos expandidos para debug."""
    response_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    timestamp = datetime.now()
    
    conn = _get_connection()
    conn.execute("""
        INSERT INTO llm_responses (
            id, timestamp, provider, model, prompt, response, cards_id, analysis_id,
            system_prompt, card_type, prompt_length, response_length, source_text_length, options
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        response_id, timestamp, provider, model, prompt, response, 
        cards_id or "", analysis_id or "",
        system_prompt or "", card_type or "",
        len(prompt), len(response), source_text_length or 0,
        json.dumps(options or {})
    ])
    conn.close()
    
    return response_id


def save_generation_request(
    source_text: str,
    context_text: str,
    card_type: str,
    model: str,
    provider: str,
    source_type: str,
    word_count: int,
    target_min: int,
    target_max: int,
    analysis_id: Optional[str] = None
) -> str:
    """Salva request de geração de cards (entrada do usuário)."""
    request_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    timestamp = datetime.now()
    
    conn = _get_connection()
    conn.execute("""
        INSERT INTO generation_requests (
            id, timestamp, analysis_id, source_text, context_text, card_type,
            model, provider, source_type, word_count, target_min, target_max
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        request_id, timestamp, analysis_id or "", source_text, context_text,
        card_type, model, provider, source_type, word_count, target_min, target_max
    ])
    conn.close()
    
    return request_id


def save_pipeline_stage(
    request_id: str,
    stage: str,
    cards_in: int,
    cards_out: int,
    duration_ms: int = 0,
    details: Optional[Dict] = None,
    analysis_id: Optional[str] = None
) -> str:
    """Salva uma etapa do pipeline de geração para rastreamento."""
    stage_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    timestamp = datetime.now()
    
    conn = _get_connection()
    conn.execute("""
        INSERT INTO generation_pipeline (
            id, timestamp, request_id, analysis_id, stage, cards_in, cards_out, duration_ms, details
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        stage_id, timestamp, request_id, analysis_id or "", stage,
        cards_in, cards_out, duration_ms, json.dumps(details or {})
    ])
    conn.close()
    
    return stage_id


def save_filter_result(
    filter_type: str,
    cards_before: List[Dict],
    cards_after: List[Dict],
    cards_id: Optional[str] = None,
    analysis_id: Optional[str] = None,
    metadata: Optional[Dict] = None,
    removed_cards_with_reasons: Optional[List[Dict]] = None
) -> str:
    """
    Salva resultado de uma operação de filtragem no DuckDB.
    
    Args:
        filter_type: Tipo do filtro aplicado (ex: 'src_validation', 'llm_relevance', 'quality_score', 'type_filter')
        cards_before: Lista de cards ANTES do filtro
        cards_after: Lista de cards APÓS o filtro (mantidos)
        cards_id: ID do registro de cards final (opcional)
        analysis_id: ID da análise associada (opcional)
        metadata: Metadados adicionais (ex: threshold usado, scores, etc.)
        removed_cards_with_reasons: Lista de cards removidos com motivos de rejeição (opcional)
    
    Returns:
        ID do registro de filter_result
    """
    filter_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    timestamp = datetime.now()
    
    # Usa cards removidos com motivos se fornecido, senão calcula a diferença
    if removed_cards_with_reasons is not None:
        removed_cards = removed_cards_with_reasons
    else:
        kept_keys = {_card_key(c) for c in cards_after}
        removed_cards = [c for c in cards_before if _card_key(c) not in kept_keys]
    
    conn = _get_connection()
    conn.execute("""
        INSERT INTO filter_results (
            id, timestamp, cards_id, analysis_id, filter_type, 
            cards_before, cards_after, kept_cards, removed_cards, filter_metadata
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        filter_id, 
        timestamp, 
        cards_id or "", 
        analysis_id or "", 
        filter_type,
        len(cards_before),
        len(cards_after),
        json.dumps(cards_after),
        json.dumps(removed_cards),
        json.dumps(metadata or {})
    ])
    conn.close()
    
    return filter_id


def _card_key(card: Dict) -> str:
    """Gera chave única para identificar um card."""
    front = (card.get("front") or "").strip()
    back = (card.get("back") or "").strip()
    return f"{front}||{back}"


def get_filter_results(
    analysis_id: Optional[str] = None, 
    cards_id: Optional[str] = None,
    filter_type: Optional[str] = None,
    limit: int = 50
) -> List[Dict]:
    """
    Retorna histórico de operações de filtragem.
    
    Args:
        analysis_id: Filtra por ID de análise
        cards_id: Filtra por ID de cards
        filter_type: Filtra por tipo de filtro
        limit: Máximo de resultados
    
    Returns:
        Lista de registros de filter_results
    """
    conn = _get_connection()
    
    query = "SELECT * FROM filter_results WHERE 1=1"
    params = []
    
    if analysis_id:
        query += " AND analysis_id = ?"
        params.append(analysis_id)
    if cards_id:
        query += " AND cards_id = ?"
        params.append(cards_id)
    if filter_type:
        query += " AND filter_type = ?"
        params.append(filter_type)
    
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    
    result = conn.execute(query, params).fetchall()
    conn.close()
    
    columns = ['id', 'timestamp', 'cards_id', 'analysis_id', 'filter_type', 
               'cards_before', 'cards_after', 'kept_cards', 'removed_cards', 'filter_metadata']
    
    return [
        {
            **dict(zip(columns, r)),
            'timestamp': r[1].isoformat() if hasattr(r[1], 'isoformat') else str(r[1]),
            'kept_cards': json.loads(r[7]) if r[7] else [],
            'removed_cards': json.loads(r[8]) if r[8] else [],
            'filter_metadata': json.loads(r[9]) if r[9] else {}
        }
        for r in result
    ]


def get_llm_responses(
    analysis_id: Optional[str] = None,
    cards_id: Optional[str] = None,
    limit: int = 20
) -> List[Dict]:
    """Retorna respostas do LLM armazenadas."""
    conn = _get_connection()
    
    query = "SELECT * FROM llm_responses WHERE 1=1"
    params = []
    
    if analysis_id:
        query += " AND analysis_id = ?"
        params.append(analysis_id)
    if cards_id:
        query += " AND cards_id = ?"
        params.append(cards_id)
    
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    
    result = conn.execute(query, params).fetchall()
    conn.close()
    
    columns = ['id', 'timestamp', 'provider', 'model', 'prompt', 'response', 'cards_id', 'analysis_id']
    
    return [
        {
            **dict(zip(columns, r)),
            'timestamp': r[1].isoformat() if hasattr(r[1], 'isoformat') else str(r[1])
        }
        for r in result
    ]
