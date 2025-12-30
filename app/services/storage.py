import os
import json
import duckdb
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

DATA_DIR = Path("data/generator")
DB_PATH = Path("data/storage.duckdb")
SQLITE_PATH = Path("data/storage.sqlite3")

def _ensure_data_dir():
    DATA_DIR.mkdir(exist_ok=True)

def _get_connection():
    _ensure_data_dir()
    conn = duckdb.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analyses (
            id VARCHAR PRIMARY KEY,
            timestamp TIMESTAMP,
            text TEXT,
            summary TEXT,
            metadata TEXT
        )
    """)
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS llm_responses (
            id VARCHAR PRIMARY KEY,
            timestamp TIMESTAMP,
            provider VARCHAR,
            model VARCHAR,
            prompt TEXT,
            response TEXT,
            cards_id VARCHAR,
            analysis_id VARCHAR
        )
    """)
    return conn

def _get_sqlite_connection():
    _ensure_data_dir()
    conn = sqlite3.connect(str(SQLITE_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analyses (
            id TEXT PRIMARY KEY,
            timestamp TEXT,
            text TEXT,
            summary TEXT,
            metadata TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            id TEXT PRIMARY KEY,
            timestamp TEXT,
            analysis_id TEXT,
            source_text TEXT,
            cards_count INTEGER,
            cards TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS llm_responses (
            id TEXT PRIMARY KEY,
            timestamp TEXT,
            provider TEXT,
            model TEXT,
            prompt TEXT,
            response TEXT,
            cards_id TEXT,
            analysis_id TEXT
        )
    """)
    conn.commit()
    return conn

def _to_toon(data: Dict) -> str:
    """Converte dict para formato TOON"""
    lines = []
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f"@{key}")
            for item in value:
                if isinstance(item, dict):
                    for k, v in item.items():
                        lines.append(f"  :{k} {v}")
                    lines.append("")
                else:
                    lines.append(f"  {item}")
        elif isinstance(value, dict):
            lines.append(f"@{key}")
            for k, v in value.items():
                lines.append(f"  :{k} {v}")
        else:
            lines.append(f":{key} {value}")
    return "\n".join(lines)

def save_analysis(text: str, summary: str, metadata: Optional[Dict] = None) -> str:
    analysis_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    timestamp = datetime.now()
    
    conn = _get_connection()
    conn.execute("""
        INSERT INTO analyses (id, timestamp, text, summary, metadata)
        VALUES (?, ?, ?, ?, ?)
    """, [analysis_id, timestamp, text, summary, json.dumps(metadata or {})])
    conn.close()
    
    sqlite_conn = _get_sqlite_connection()
    sqlite_conn.execute("""
        INSERT INTO analyses (id, timestamp, text, summary, metadata)
        VALUES (?, ?, ?, ?, ?)
    """, [analysis_id, timestamp.isoformat(), text, summary, json.dumps(metadata or {})])
    sqlite_conn.commit()
    sqlite_conn.close()
    
    # Salvar arquivo TOON para compatibilidade
    record = {"id": analysis_id, "timestamp": timestamp.isoformat(), "text": text, "summary": summary, "metadata": metadata or {}}
    filepath = DATA_DIR / f"analysis_{analysis_id}.toon"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(_to_toon(record))
    
    return analysis_id

def save_cards(cards: List[Dict], analysis_id: Optional[str] = None, source_text: Optional[str] = None) -> str:
    cards_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    timestamp = datetime.now()
    
    conn = _get_connection()
    conn.execute("""
        INSERT INTO cards (id, timestamp, analysis_id, source_text, cards_count, cards)
        VALUES (?, ?, ?, ?, ?, ?)
    """, [cards_id, timestamp, analysis_id or "", source_text or "", len(cards), json.dumps(cards)])
    conn.close()
    
    sqlite_conn = _get_sqlite_connection()
    sqlite_conn.execute("""
        INSERT INTO cards (id, timestamp, analysis_id, source_text, cards_count, cards)
        VALUES (?, ?, ?, ?, ?, ?)
    """, [cards_id, timestamp.isoformat(), analysis_id or "", source_text or "", len(cards), json.dumps(cards)])
    sqlite_conn.commit()
    sqlite_conn.close()
    
    # Salvar arquivo TOON para compatibilidade
    record = {"id": cards_id, "timestamp": timestamp.isoformat(), "analysis_id": analysis_id or "", "source_text": source_text or "", "cards_count": str(len(cards)), "cards": cards}
    filepath = DATA_DIR / f"cards_{cards_id}.toon"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(_to_toon(record))
    
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
    conn = _get_connection()
    analyses_count = conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
    cards_count = conn.execute("SELECT SUM(cards_count) FROM cards").fetchone()[0] or 0
    conn.close()
    
    return {
        "total_analyses": analyses_count,
        "total_cards": cards_count,
        "data_dir": str(DATA_DIR.absolute())
    }

def save_llm_response(provider: str, model: str, prompt: str, response: str, cards_id: Optional[str] = None, analysis_id: Optional[str] = None) -> str:
    response_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    timestamp = datetime.now()
    
    conn = _get_connection()
    conn.execute("""
        INSERT INTO llm_responses (id, timestamp, provider, model, prompt, response, cards_id, analysis_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, [response_id, timestamp, provider, model, prompt, response, cards_id or "", analysis_id or ""])
    conn.close()
    
    sqlite_conn = _get_sqlite_connection()
    sqlite_conn.execute("""
        INSERT INTO llm_responses (id, timestamp, provider, model, prompt, response, cards_id, analysis_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, [response_id, timestamp.isoformat(), provider, model, prompt, response, cards_id or "", analysis_id or ""])
    sqlite_conn.commit()
    sqlite_conn.close()
    
    return response_id
