import os
from pathlib import Path
from fastapi.testclient import TestClient

# Test database and secret are isolated from any local/production database.
os.environ["DATABASE_URL"] = "sqlite:///./test_warrantyhub.db"
os.environ["JWT_SECRET"] = "test-only-secret-that-is-long-enough-123456"
os.environ["UPLOAD_DIR"] = "./test_private_uploads"
from main import app, Base, engine  # noqa: E402

client = TestClient(app)

def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

def teardown_module():
    Base.metadata.drop_all(bind=engine)
    Path("test_warrantyhub.db").unlink(missing_ok=True)

def register(email="customer@example.com"):
    response = client.post("/api/v1/auth/register", json={"name":"Test Customer","email":email,"password":"A-strong-test-password-123"})
    assert response.status_code == 201, response.text
    return response.json()["access_token"]

def test_health():
    assert client.get("/health").json()["status"] == "ok"

def test_register_login_and_duplicate_email():
    token = register()
    assert client.get("/api/v1/auth/me", headers={"Authorization":f"Bearer {token}"}).json()["email"] == "customer@example.com"
    assert client.post("/api/v1/auth/register", json={"name":"Again","email":"customer@example.com","password":"A-strong-test-password-123"}).status_code == 409
    assert client.post("/api/v1/auth/login", json={"email":"customer@example.com","password":"A-strong-test-password-123"}).status_code == 200

def test_customer_cannot_access_admin_routes():
    token = register()
    response = client.get("/api/v1/admin/purchases", headers={"Authorization":f"Bearer {token}"})
    assert response.status_code == 403

def test_purchase_is_owner_scoped_and_claim_created():
    token1 = register("one@example.com")
    token2 = register("two@example.com")
    headers1 = {"Authorization":f"Bearer {token1}"}
    headers2 = {"Authorization":f"Bearer {token2}"}
    response = client.post("/api/v1/purchases", headers=headers1, json={"product_name":"Laptop","brand":"Example","category":"laptop","serial_number":"SERIAL-123","purchase_date":"2026-01-01","warranty_end":"2027-01-01","price_minor":1250000})
    assert response.status_code == 201, response.text
    purchase_id = response.json()["id"]
    assert len(client.get("/api/v1/purchases", headers=headers1).json()) == 1
    assert client.get("/api/v1/purchases", headers=headers2).json() == []
    claim = client.post("/api/v1/claims", headers=headers1, json={"purchase_id":purchase_id,"issue":"Battery no longer charges"})
    assert claim.status_code == 201, claim.text
    assert client.post("/api/v1/claims", headers=headers2, json={"purchase_id":purchase_id,"issue":"Battery no longer charges"}).status_code == 404
