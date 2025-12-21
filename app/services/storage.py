import os
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

DATA_DIR = Path("data")

def _ensure_data_dir():
    DATA_DIR.mkdir(exist_ok=True)

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

def _from_toon(content: str) -> Dict:
    """Converte TOON para dict"""
    data = {}
    current_key = None
    current_list = []
    current_dict = {}
    
    for line in content.split("\n"):
        if line.startswith("@"):
            if current_key and current_list:
                data[current_key] = current_list
            current_key = line[1:]
            current_list = []
            current_dict = {}
        elif line.startswith("  :"):
            parts = line[3:].split(" ", 1)
            current_dict[parts[0]] = parts[1] if len(parts) > 1 else ""
        elif line.startswith(":"):
            parts = line[1:].split(" ", 1)
            data[parts[0]] = parts[1] if len(parts) > 1 else ""
        elif line.strip() == "" and current_dict:
            current_list.append(current_dict.copy())
            current_dict = {}
    
    if current_key and current_list:
        data[current_key] = current_list
    elif current_key and current_dict:
        data[current_key] = current_dict
    
    return data

def save_analysis(text: str, summary: str, metadata: Optional[Dict] = None) -> str:
    _ensure_data_dir()
    
    analysis_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    record = {
        "id": analysis_id,
        "timestamp": datetime.now().isoformat(),
        "text": text,
        "summary": summary,
        "metadata": metadata or {}
    }
    
    filepath = DATA_DIR / f"analysis_{analysis_id}.toon"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(_to_toon(record))
    
    return analysis_id

def save_cards(cards: List[Dict], analysis_id: Optional[str] = None, source_text: Optional[str] = None) -> str:
    _ensure_data_dir()
    
    cards_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    record = {
        "id": cards_id,
        "timestamp": datetime.now().isoformat(),
        "analysis_id": analysis_id or "",
        "source_text": source_text or "",
        "cards_count": str(len(cards)),
        "cards": cards
    }
    
    filepath = DATA_DIR / f"cards_{cards_id}.toon"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(_to_toon(record))
    
    return cards_id

def get_recent_analyses(limit: int = 10) -> List[Dict]:
    _ensure_data_dir()
    files = sorted(DATA_DIR.glob("analysis_*.toon"), reverse=True)[:limit]
    return [_from_toon(open(f, encoding="utf-8").read()) for f in files]

def get_recent_cards(limit: int = 10) -> List[Dict]:
    _ensure_data_dir()
    files = sorted(DATA_DIR.glob("cards_*.toon"), reverse=True)[:limit]
    return [_from_toon(open(f, encoding="utf-8").read()) for f in files]

def get_stats() -> Dict:
    _ensure_data_dir()
    analyses = list(DATA_DIR.glob("analysis_*.toon"))
    cards_files = list(DATA_DIR.glob("cards_*.toon"))
    
    total_cards = sum(int(_from_toon(open(f, encoding="utf-8").read()).get("cards_count", 0)) for f in cards_files)
    
    return {
        "total_analyses": len(analyses),
        "total_cards": total_cards,
        "data_dir": str(DATA_DIR.absolute())
    }
