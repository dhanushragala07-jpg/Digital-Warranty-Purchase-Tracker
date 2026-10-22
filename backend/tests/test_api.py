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

def test_unmatched_purchase_is_rejected_and_not_saved():
    token = register()
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"product_name":"Laptop","brand":"Example","category":"laptop","serial_number":"SERIAL-123","purchase_date":"2026-01-01","warranty_end":"2027-01-01","price_minor":1250000}
    response = client.post("/api/v1/purchases", headers=headers, json=payload)
    assert response.status_code == 422, response.text
    assert "INVALID PURCHASE" in response.json()["detail"]
    assert client.get("/api/v1/purchases", headers=headers).json() == []

def test_only_exact_approved_admin_match_can_be_saved():
    from main import AdminProductRecord, SessionLocal, User
    token = register("one@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    me = client.get("/api/v1/auth/me", headers=headers).json()
    with SessionLocal() as db:
        customer = db.get(User, me["id"])
        db.add(AdminProductRecord(
            customer_email="one@example.com",
            product_name="Laptop",
            brand="Example",
            category="laptop",
            serial_number="SERIAL-123",
            purchase_date=__import__("datetime").date(2026, 1, 1),
            warranty_end=__import__("datetime").date(2027, 1, 1),
            price_minor=1250000,
            evidence_note="Test approved record",
            created_by=customer.id,
        ))
        db.commit()
    payload = {"product_name":"Laptop","brand":"Example","category":"laptop","serial_number":"SERIAL-123","purchase_date":"2026-01-01","warranty_end":"2027-01-01","price_minor":1250000}
    response = client.post("/api/v1/purchases", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    assert response.json()["verification_status"] == "verified"
    mismatch = {**payload, "brand":"Different brand", "serial_number":"SERIAL-123"}
    rejected = client.post("/api/v1/purchases", headers=headers, json=mismatch)
    assert rejected.status_code == 422
    assert len(client.get("/api/v1/purchases", headers=headers).json()) == 1
