import pytest
from fastapi.testclient import TestClient
from app.web import app

client = TestClient(app)

def test_web_routes():
    res1 = client.get("/")
    assert res1.status_code == 200
    assert res1.json() == {"status": "ok", "service": "telegram-docker-deploy-manager"}

    res2 = client.get("/health")
    assert res2.status_code == 200
    assert res2.json() == {"status": "healthy"}
