"""
Tests for the health API endpoints.
"""
import pytest
from fastapi.testclient import TestClient


def test_health_endpoint_exists():
    """Test that health module can be imported."""
    from app.api.health import router
    assert router is not None


def test_health_endpoint_basic():
    """Test the /api/health endpoint returns expected structure."""
    from app.main import app
    
    client = TestClient(app)
    response = client.get("/api/health")
    
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "ok"
