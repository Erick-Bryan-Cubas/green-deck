"""Script temporário para limpar o banco de dados DuckDB"""
from app.services.storage import _get_connection

def clean_database():
    conn = _get_connection()
    
    print("Limpando tabelas...")
    
    # Limpa todas as tabelas
    conn.execute('DELETE FROM analyses')
    print("✓ Tabela analyses limpa")
    
    conn.execute('DELETE FROM cards')
    print("✓ Tabela cards limpa")
    
    conn.execute('DELETE FROM llm_responses')
    print("✓ Tabela llm_responses limpa")
    
    conn.execute('DELETE FROM filter_results')
    print("✓ Tabela filter_results limpa")
    
    # Verifica contagens
    analyses_count = conn.execute('SELECT COUNT(*) FROM analyses').fetchone()[0]
    cards_count = conn.execute('SELECT COUNT(*) FROM cards').fetchone()[0]
    llm_responses_count = conn.execute('SELECT COUNT(*) FROM llm_responses').fetchone()[0]
    filter_results_count = conn.execute('SELECT COUNT(*) FROM filter_results').fetchone()[0]
    
    print("\nContagens finais:")
    print(f"  - analyses: {analyses_count}")
    print(f"  - cards: {cards_count}")
    print(f"  - llm_responses: {llm_responses_count}")
    print(f"  - filter_results: {filter_results_count}")
    
    conn.close()
    print("\n✓ Banco de dados limpo com sucesso!")

if __name__ == "__main__":
    clean_database()
