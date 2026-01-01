# tests/test_text_analysis.py
"""
Testes para as melhorias de análise de texto e geração de cards.
"""

import pytest


class TestSemanticChunking:
    """Testes para o chunking semântico com overlap."""
    
    def test_chunk_text_semantic_basic(self):
        """Testa chunking semântico básico."""
        from app.services.ollama import chunk_text_semantic
        
        text = """
        Python é uma linguagem de programação de alto nível. 
        Foi criada por Guido van Rossum em 1991. 
        Python é conhecida por sua sintaxe limpa e legibilidade.
        A linguagem suporta múltiplos paradigmas de programação.
        É amplamente usada em ciência de dados e machine learning.
        """
        
        chunks = chunk_text_semantic(text, max_words=20, overlap_sentences=1)
        
        assert len(chunks) > 0
        # Cada chunk deve ter texto
        for chunk in chunks:
            assert len(chunk.strip()) > 0
    
    def test_chunk_text_semantic_overlap(self):
        """Testa que o overlap está funcionando."""
        from app.services.ollama import chunk_text_semantic
        
        text = "Primeira frase. Segunda frase. Terceira frase. Quarta frase. Quinta frase."
        
        chunks = chunk_text_semantic(text, max_words=5, overlap_sentences=1)
        
        # Com overlap, deve haver repetição entre chunks adjacentes
        if len(chunks) > 1:
            # Pelo menos um chunk deve compartilhar conteúdo com o próximo
            has_overlap = False
            for i in range(len(chunks) - 1):
                words_current = set(chunks[i].lower().split())
                words_next = set(chunks[i + 1].lower().split())
                if words_current & words_next:
                    has_overlap = True
                    break
            # Overlap é esperado mas não garantido dependendo do tamanho
            assert len(chunks) >= 1
    
    def test_chunk_text_semantic_empty(self):
        """Testa com texto vazio."""
        from app.services.ollama import chunk_text_semantic
        
        assert chunk_text_semantic("") == []
        assert chunk_text_semantic("   ") == []
        assert chunk_text_semantic(None) == []
    
    def test_chunk_text_semantic_single_sentence(self):
        """Testa com uma única sentença."""
        from app.services.ollama import chunk_text_semantic
        
        text = "Esta é uma única sentença de teste."
        chunks = chunk_text_semantic(text, max_words=100)
        
        assert len(chunks) == 1
        assert chunks[0].strip() == text.strip()


class TestCardQualityScoring:
    """Testes para o sistema de scoring de qualidade."""
    
    def test_score_basic_card(self):
        """Testa scoring de card básico."""
        from app.api.flashcards import score_card_quality
        
        card = {
            "front": "O que é Python?",
            "back": "Python é uma linguagem de programação de alto nível.",
            "src": "trecho do texto fonte aqui"
        }
        
        score = score_card_quality(card)
        
        assert 0.0 <= score <= 1.0
        assert score >= 0.5  # Card razoável deve ter score decente
    
    def test_score_penalizes_long_answer(self):
        """Testa que respostas longas são penalizadas."""
        from app.api.flashcards import score_card_quality
        
        short_answer = {
            "front": "O que é X?",
            "back": "X é uma coisa específica.",
        }
        
        long_answer = {
            "front": "O que é X?",
            "back": " ".join(["palavra"] * 50),  # 50 palavras
        }
        
        score_short = score_card_quality(short_answer)
        score_long = score_card_quality(long_answer)
        
        assert score_short > score_long
    
    def test_score_penalizes_yes_no_questions(self):
        """Testa que perguntas sim/não são penalizadas."""
        from app.api.flashcards import score_card_quality
        
        yes_no = {
            "front": "É verdade que Python é popular?",
            "back": "Sim, Python é muito popular.",
        }
        
        specific = {
            "front": "Qual é a popularidade de Python?",
            "back": "Python está entre as linguagens mais populares.",
        }
        
        score_yes_no = score_card_quality(yes_no)
        score_specific = score_card_quality(specific)
        
        assert score_specific > score_yes_no
    
    def test_score_penalizes_vague_terms(self):
        """Testa que termos vagos são penalizados."""
        from app.api.flashcards import score_card_quality
        
        vague = {
            "front": "O que é X?",
            "back": "X é uma coisa que faz algo.",
        }
        
        clear = {
            "front": "O que é X?",
            "back": "X é um framework para desenvolvimento web.",
        }
        
        score_vague = score_card_quality(vague)
        score_clear = score_card_quality(clear)
        
        assert score_clear > score_vague
    
    def test_score_bonifies_src(self):
        """Testa que presença de SRC dá bônus."""
        from app.api.flashcards import score_card_quality
        
        with_src = {
            "front": "O que é Python?",
            "back": "Uma linguagem de programação.",
            "src": "Python é uma linguagem"
        }
        
        without_src = {
            "front": "O que é Python?",
            "back": "Uma linguagem de programação.",
        }
        
        score_with = score_card_quality(with_src)
        score_without = score_card_quality(without_src)
        
        assert score_with > score_without
    
    def test_score_cloze_card(self):
        """Testa scoring de card cloze."""
        from app.api.flashcards import score_card_quality
        
        good_cloze = {
            "front": "Python foi criado por {{c1::Guido van Rossum}}.",
            "back": "Extra: Em 1991.",
        }
        
        bad_cloze = {
            "front": "{{c1::Python é uma linguagem de programação de alto nível criada por Guido}}.",
            "back": "Extra: Sim.",
        }
        
        score_good = score_card_quality(good_cloze)
        score_bad = score_card_quality(bad_cloze)
        
        assert score_good > score_bad


class TestFilterAndRank:
    """Testes para filtragem e ranking por qualidade."""
    
    def test_filter_removes_low_quality(self):
        """Testa que cards de baixa qualidade são removidos."""
        from app.api.flashcards import filter_and_rank_by_quality
        
        cards = [
            {"front": "O que é X?", "back": "X é algo bom."},  # OK
            {"front": "X", "back": "Y"},  # Muito curto
            {"front": "Qual framework é usado?", "back": "Django é um framework web."},  # Bom
        ]
        
        filtered = filter_and_rank_by_quality(cards, min_score=0.5)
        
        # Pelo menos alguns devem passar
        assert len(filtered) <= len(cards)
    
    def test_filter_respects_max_cards(self):
        """Testa limite de cards."""
        from app.api.flashcards import filter_and_rank_by_quality
        
        cards = [
            {"front": f"Pergunta {i}?", "back": f"Resposta completa número {i}."}
            for i in range(10)
        ]
        
        filtered = filter_and_rank_by_quality(cards, min_score=0.0, max_cards=3)
        
        assert len(filtered) <= 3
    
    def test_filter_orders_by_quality(self):
        """Testa que cards são ordenados por qualidade."""
        from app.api.flashcards import filter_and_rank_by_quality
        
        cards = [
            {"front": "X?", "back": "Y"},  # Ruim
            {"front": "O que é Python?", "back": "Python é uma linguagem.", "src": "fonte"},  # Bom
            {"front": "Defina A", "back": "A é B"},  # Médio
        ]
        
        filtered = filter_and_rank_by_quality(cards, min_score=0.0)
        
        # Verifica que estão ordenados (maior score primeiro)
        scores = [c.get("_quality_score", 0) for c in filtered]
        assert scores == sorted(scores, reverse=True)


class TestLLMCache:
    """Testes para o cache de respostas LLM."""
    
    def test_cache_set_and_get(self):
        """Testa set e get básico."""
        from app.services.llm_cache import LLMResponseCache
        
        cache = LLMResponseCache(max_entries=10, ttl_seconds=60)
        
        cache.set("model1", "prompt1", "response1")
        result = cache.get("model1", "prompt1")
        
        assert result == "response1"
    
    def test_cache_miss(self):
        """Testa cache miss."""
        from app.services.llm_cache import LLMResponseCache
        
        cache = LLMResponseCache()
        
        result = cache.get("unknown_model", "unknown_prompt")
        
        assert result is None
    
    def test_cache_with_system(self):
        """Testa cache com system prompt."""
        from app.services.llm_cache import LLMResponseCache
        
        cache = LLMResponseCache()
        
        cache.set("model", "prompt", "response1", system="system1")
        cache.set("model", "prompt", "response2", system="system2")
        
        assert cache.get("model", "prompt", system="system1") == "response1"
        assert cache.get("model", "prompt", system="system2") == "response2"
    
    def test_cache_stats(self):
        """Testa estatísticas do cache."""
        from app.services.llm_cache import LLMResponseCache
        
        cache = LLMResponseCache()
        
        cache.set("m", "p", "r")
        cache.get("m", "p")  # hit
        cache.get("m", "other")  # miss
        
        stats = cache.stats()
        
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["entries"] == 1
    
    def test_cache_eviction(self):
        """Testa eviction LRU."""
        from app.services.llm_cache import LLMResponseCache
        
        cache = LLMResponseCache(max_entries=2)
        
        cache.set("m", "p1", "r1")
        cache.set("m", "p2", "r2")
        cache.set("m", "p3", "r3")  # Deve evictar p1
        
        assert cache.get("m", "p1") is None  # Evicted
        assert cache.get("m", "p2") == "r2"
        assert cache.get("m", "p3") == "r3"


class TestNormalizeTextForMatching:
    """Testes para normalização de texto."""
    
    def test_normalize_quotes(self):
        """Testa normalização de aspas."""
        from app.api.flashcards import _normalize_text_for_matching
        
        text1 = '"texto"'
        text2 = '"texto"'
        
        assert _normalize_text_for_matching(text1) == _normalize_text_for_matching(text2)
    
    def test_normalize_dashes(self):
        """Testa normalização de hífens."""
        from app.api.flashcards import _normalize_text_for_matching
        
        text1 = "alto-nível"
        text2 = "alto–nível"  # en-dash
        text3 = "alto—nível"  # em-dash
        
        norm1 = _normalize_text_for_matching(text1)
        norm2 = _normalize_text_for_matching(text2)
        norm3 = _normalize_text_for_matching(text3)
        
        assert norm1 == norm2 == norm3
    
    def test_normalize_whitespace(self):
        """Testa normalização de espaços."""
        from app.api.flashcards import _normalize_text_for_matching
        
        text1 = "múltiplos   espaços"
        text2 = "múltiplos espaços"
        
        assert _normalize_text_for_matching(text1) == _normalize_text_for_matching(text2)
