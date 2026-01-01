"""Script temporário para limpar o banco de dados DuckDB"""
import sys
from pathlib import Path

# Adiciona o diretório raiz ao path se executado diretamente
if __name__ == "__main__":
    root_dir = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(root_dir))

from app.services.storage import _get_connection

def clean_database():
    conn = _get_connection()
    
    print("Limpando tabelas...")
    
    # Limpa todas as tabelas
    conn.execute('DELETE FROM analyses')
    print("[OK] Tabela analyses limpa")
    
    conn.execute('DELETE FROM cards')
    print("[OK] Tabela cards limpa")
    
    conn.execute('DELETE FROM llm_responses')
    print("[OK] Tabela llm_responses limpa")
    
    conn.execute('DELETE FROM filter_results')
    print("[OK] Tabela filter_results limpa")
    
    conn.execute('DELETE FROM generation_pipeline')
    print("[OK] Tabela generation_pipeline limpa")
    
    conn.execute('DELETE FROM generation_requests')
    print("[OK] Tabela generation_requests limpa")
    
    # Verifica contagens
    analyses_count = conn.execute('SELECT COUNT(*) FROM analyses').fetchone()[0]
    cards_count = conn.execute('SELECT COUNT(*) FROM cards').fetchone()[0]
    llm_responses_count = conn.execute('SELECT COUNT(*) FROM llm_responses').fetchone()[0]
    filter_results_count = conn.execute('SELECT COUNT(*) FROM filter_results').fetchone()[0]
    generation_pipeline_count = conn.execute('SELECT COUNT(*) FROM generation_pipeline').fetchone()[0]
    generation_requests_count = conn.execute('SELECT COUNT(*) FROM generation_requests').fetchone()[0]
    
    print("\nContagens finais:")
    print(f"  - analyses: {analyses_count}")
    print(f"  - cards: {cards_count}")
    print(f"  - llm_responses: {llm_responses_count}")
    print(f"  - filter_results: {filter_results_count}")
    print(f"  - generation_pipeline: {generation_pipeline_count}")
    print(f"  - generation_requests: {generation_requests_count}")
    
    conn.close()
    print("\n[OK] Banco de dados limpo com sucesso!")

if __name__ == "__main__":
    clean_database()
