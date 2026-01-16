"""
Test fixtures for the green-deck application.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client for the FastAPI application."""
    from app.main import app
    return TestClient(app)


@pytest.fixture
def mock_anki_response():
    """Mock response from AnkiConnect."""
    return {
        "result": 6,
        "error": None
    }


@pytest.fixture
def mock_ollama_response():
    """Mock response from Ollama API."""
    return {
        "models": [
            {"name": "qwen-flashcard:latest"},
            {"name": "llama3.2:latest"}
        ]
    }


@pytest.fixture
def sample_flashcard():
    """Sample flashcard data for testing."""
    return {
        "front": "What is spaced repetition?",
        "back": "A learning technique that involves reviewing material at increasing intervals.",
        "deck": "Test Deck",
        "tags": ["learning", "memory"]
    }


@pytest.fixture
def sample_text():
    """Sample text for flashcard generation."""
    return """
    Spaced repetition is a learning technique where the review of previously learned 
    material is spaced over increasing intervals of time. This method leverages the 
    psychological spacing effect, which demonstrates that learning is more effective 
    when study sessions are spaced out rather than massed together.
    
    The technique was popularized by German psychologist Hermann Ebbinghaus, who 
    discovered the "forgetting curve" - a mathematical model of how information is 
    lost over time when there is no attempt to retain it.
    """
