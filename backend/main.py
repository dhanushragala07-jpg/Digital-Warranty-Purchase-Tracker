import os, uuid, hashlib, smtplib, html, logging, json, urllib.request, urllib.error
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from email.message import EmailMessage
from typing import Literal

import jwt
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pwdlib import PasswordHash
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./warrantyhub.db")
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET or len(JWT_SECRET) < 32:
    if os.getenv("APP_ENV", "development") == "production":
        raise RuntimeError("Set JWT_SECRET to a random secret of at least 32 characters")
    JWT_SECRET = "dev-only-change-this-secret-before-deployment-0123456789"
JWT_ALGORITHM = "HS256"
TOKEN_HOURS = int(os.getenv("TOKEN_HOURS", "12"))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./private_uploads")).resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
ALLOWED_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}

# Aiven requires TLS. PyMySQL expects SSL settings as connect arguments,
# not URL query parameters such as "ssl-mode=REQUIRED".
if DATABASE_URL.startswith(("mysql://", "mariadb://")):
    DATABASE_URL = DATABASE_URL.replace("mysql://", "mysql+pymysql://", 1).replace("mariadb://", "mysql+pymysql://", 1)
if DATABASE_URL.startswith("mysql"):
    DATABASE_URL = DATABASE_URL.split("?", 1)[0]
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args={"ssl": {}})
elif DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)

class Base(DeclarativeBase): pass
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="customer")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
class Purchase(Base):
    __tablename__ = "purchases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_name: Mapped[str] = mapped_column(String(160))
    brand: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(40))
    serial_number: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    purchase_date: Mapped[date] = mapped_column(Date)
    warranty_end: Mapped[date] = mapped_column(Date)
    price_minor: Mapped[int] = mapped_column(Integer)
    invoice_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    invoice_status: Mapped[str] = mapped_column(String(30), default="not_uploaded")
    verification_status: Mapped[str] = mapped_column(String(30), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class PendingAdminPurchase(Base):
    __tablename__ = "pending_admin_purchases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_email: Mapped[str] = mapped_column(String(320), index=True)
    product_name: Mapped[str] = mapped_column(String(160))
    brand: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(40))
    serial_number: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    purchase_date: Mapped[date] = mapped_column(Date)
    warranty_end: Mapped[date] = mapped_column(Date)
    price_minor: Mapped[int] = mapped_column(Integer)
    evidence_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Claim(Base):
    __tablename__ = "claims"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    purchase_id: Mapped[int] = mapped_column(ForeignKey("purchases.id"), index=True)
    issue: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="submitted")
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
class AdminProductRecord(Base):
    __tablename__ = "admin_product_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_email: Mapped[str] = mapped_column(String(320), index=True)
    product_name: Mapped[str] = mapped_column(String(160))
    brand: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(40))
    serial_number: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    purchase_date: Mapped[date] = mapped_column(Date)
    warranty_end: Mapped[date] = mapped_column(Date)
    price_minor: Mapped[int] = mapped_column(Integer)
    evidence_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(engine)

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()
class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
class LoginIn(BaseModel): email: EmailStr; password: str = Field(min_length=1, max_length=128)
class PurchaseIn(BaseModel):
    product_name: str = Field(min_length=1, max_length=160)
    brand: str = Field(min_length=1, max_length=120)
    category: Literal["phone", "laptop", "watch", "audio", "camera", "other"] = "other"
    serial_number: str | None = Field(default=None, max_length=180)
    purchase_date: date
    warranty_end: date
    price_minor: int = Field(ge=0, le=100_000_000_00)
class AdminRecordIn(BaseModel):
    customer_email: EmailStr
    product_name: str = Field(min_length=1, max_length=160)
    brand: str = Field(min_length=1, max_length=120)
    category: Literal["phone", "laptop", "watch", "audio", "camera", "other"] = "other"
    serial_number: str | None = Field(default=None, max_length=180)
    purchase_date: date
    warranty_end: date
    price_minor: int = Field(ge=0, le=100_000_000_00)
    evidence_note: str | None = Field(default=None, max_length=2000)

class ClaimIn(BaseModel): purchase_id: int; issue: str = Field(min_length=5, max_length=4000)
class ReviewIn(BaseModel): status: Literal["verified", "rejected"]; note: str | None = Field(default=None, max_length=2000)
class UserOut(BaseModel): id: int; email: str; name: str; role: str
class TokenOut(BaseModel): access_token: str; token_type: str = "bearer"; user: UserOut
class PurchaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; owner_id: int; product_name: str; brand: str; category: str; serial_number: str | None; purchase_date: date; warranty_end: date; price_minor: int; invoice_status: str; verification_status: str; created_at: datetime
class ClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; owner_id: int; purchase_id: int; issue: str; status: str; admin_note: str | None; created_at: datetime
app = FastAPI(title="Digital Warranty & Purchase Tracker API", version="0.1.0", description="Initial API for customer accounts, purchases, private invoice evidence and claims.")
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "https://dhanushragala07-jpg.github.io,http://localhost:5500,http://127.0.0.1:5500,http://localhost:8000").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"], allow_headers=["Authorization", "Content-Type"])
def token_for(user: User) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user.id), "role": user.role, "iat": now, "exp": now + timedelta(hours=TOKEN_HOURS)}, JWT_SECRET, algorithm=JWT_ALGORITHM)
def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not credentials: raise HTTPException(status_code=401, detail="Sign in required")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        uid = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError): raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.get(User, uid)
    if not user: raise HTTPException(status_code=401, detail="Account not found")
    return user
def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != "admin": raise HTTPException(status_code=403, detail="Administrator access required")
    return user
def to_user(user: User): return UserOut(id=user.id, email=user.email, name=user.name, role=user.role)
def sign_in(user: User): return TokenOut(access_token=token_for(user), user=to_user(user))

def send_purchase_confirmation(recipient: str, product_name: str, token: str):
    # Use Resend's HTTPS API because this hosting environment cannot reach SMTP.
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    sender = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="Email is not configured. Set RESEND_API_KEY on Render.")
    base = os.getenv("API_PUBLIC_URL", "https://digital-warranty-purchase-tracker.onrender.com").rstrip("/")
    accept_url = f"{base}/api/v1/purchase-confirmation?token={token}&decision=accept"
    reject_url = f"{base}/api/v1/purchase-confirmation?token={token}&decision=reject"
    safe_product = html.escape(product_name)
    text_body = (
        f"An administrator entered a purchase record for {product_name}. "
        "Accept only if these details are correct.\\n\\n"
        f"Accept: {accept_url}\\nReject: {reject_url}"
    )
    html_body = (
        f"<p>An administrator entered a purchase record for <b>{safe_product}</b>.</p>"
        "<p>Accept only if these details are correct.</p>"
        f"<p><a href=\"{html.escape(accept_url, quote=True)}\">Accept and save purchase</a></p>"
        f"<p><a href=\"{html.escape(reject_url, quote=True)}\">Reject purchase</a></p>"
    )
    payload = json.dumps({
        "from": sender,
        "to": [recipient],
        "subject": f"Confirm purchase record: {product_name}",
        "text": text_body,
        "html": html_body,
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Digital-Warranty-Purchase-Tracker/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"Resend returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        # Do not log request headers or API keys.
        try:
            detail = exc.read(1000).decode("utf-8", errors="replace")
        except Exception:
            detail = "No response body"
        logging.error("Resend email failed (HTTP %s): %s", exc.code, detail)
        raise HTTPException(status_code=502, detail="Confirmation email could not be sent. Check Resend settings on Render.") from exc
    except Exception as exc:
        logging.error("Resend email failed (%s): %s", type(exc).__name__, exc)
        raise HTTPException(status_code=502, detail="Confirmation email could not be sent. Check Resend settings on Render.") from exc

@app.get("/health")
def health(): return {"status": "ok", "service": "warrantyhub-api"}
@app.get("/api/v1/health")
def api_health(): return {"status": "ok", "version": "0.1.0"}
@app.post("/api/v1/auth/register", response_model=TokenOut, status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    email = str(data.email).lower().strip()
    if db.scalar(select(User).where(User.email == email)): raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(name=data.name.strip(), email=email, password_hash=password_hash.hash(data.password), role="customer")
    db.add(user); db.commit(); db.refresh(user)
    return sign_in(user)
@app.post("/api/v1/auth/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(data.email).lower().strip()))
    if not user or not password_hash.verify(data.password, user.password_hash): raise HTTPException(status_code=401, detail="Email or password is incorrect")
    return sign_in(user)
@app.get("/api/v1/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)): return to_user(user)
def duplicate_flag(db: Session, serial: str | None, exclude_id: int | None = None) -> bool:
    if not serial or not serial.strip(): return False
    stmt = select(Purchase.id).where(Purchase.serial_number == serial.strip())
    if exclude_id is not None: stmt = stmt.where(Purchase.id != exclude_id)
    return db.scalar(stmt.limit(1)) is not None
@app.get("/api/v1/purchases")
def list_purchases(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Purchase).where(Purchase.owner_id == user.id).order_by(Purchase.created_at.desc())).all()
    today = date.today()
    return [{**PurchaseOut.model_validate(p).model_dump(mode="json"), "warranty_state": "expired" if p.warranty_end < today else "expiring" if (p.warranty_end-today).days <= 45 else "active", "possible_duplicate": duplicate_flag(db,p.serial_number,p.id)} for p in rows]
@app.post("/api/v1/purchases", response_model=PurchaseOut, status_code=201)
def match_approved_admin_record(db: Session, user: User, *, product_name: str, brand: str, category: str, serial_number: str | None, purchase_date: date, warranty_end: date, price_minor: int) -> bool:
    # Only an already-approved record for this customer's account can validate a purchase.
    if not serial_number:
        return False
    approved = db.scalar(select(AdminProductRecord).where(
        AdminProductRecord.customer_email == str(user.email).lower().strip(),
        AdminProductRecord.serial_number == serial_number.strip()
    ).limit(1))
    return bool(
        approved
        and approved.product_name.strip().casefold() == product_name.strip().casefold()
        and approved.brand.strip().casefold() == brand.strip().casefold()
        and approved.category == category
        and approved.purchase_date == purchase_date
        and approved.warranty_end == warranty_end
        and approved.price_minor == price_minor
    )

def create_purchase(data: PurchaseIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if data.warranty_end < data.purchase_date: raise HTTPException(status_code=422, detail="Warranty end must not precede purchase date")
    serial = data.serial_number.strip() if data.serial_number else None
    product_name, brand = data.product_name.strip(), data.brand.strip()
    duplicate_query = select(Purchase).where(
        Purchase.owner_id == user.id,
        Purchase.product_name == product_name,
        Purchase.brand == brand,
        Purchase.purchase_date == data.purchase_date,
        Purchase.warranty_end == data.warranty_end,
        Purchase.price_minor == data.price_minor
    )
    if serial:
        duplicate_query = duplicate_query.where(Purchase.serial_number == serial)
    else:
        duplicate_query = duplicate_query.where(Purchase.serial_number.is_(None))
    if db.scalar(duplicate_query.limit(1)):
        raise HTTPException(status_code=409, detail="This purchase was already submitted. Duplicate creation blocked.")
    matches_admin = match_approved_admin_record(
        db, user, product_name=product_name, brand=brand, category=data.category,
        serial_number=serial, purchase_date=data.purchase_date,
        warranty_end=data.warranty_end, price_minor=data.price_minor
    )
    p = Purchase(owner_id=user.id, product_name=product_name, brand=brand, category=data.category, serial_number=serial, purchase_date=data.purchase_date, warranty_end=data.warranty_end, price_minor=data.price_minor, verification_status="verified" if matches_admin else "rejected")
    db.add(p); db.commit(); db.refresh(p)
    return p
@app.patch("/api/v1/purchases/{purchase_id}", response_model=PurchaseOut)
def update_purchase(purchase_id: int, data: PurchaseIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.scalar(select(Purchase).where(Purchase.id == purchase_id, Purchase.owner_id == user.id))
    if not p: raise HTTPException(status_code=404, detail="Purchase not found")
    if data.warranty_end < data.purchase_date: raise HTTPException(status_code=422, detail="Warranty end date must not precede purchase date")
    p.product_name=data.product_name.strip(); p.brand=data.brand.strip(); p.category=data.category; p.serial_number=data.serial_number.strip() if data.serial_number else None; p.purchase_date=data.purchase_date; p.warranty_end=data.warranty_end; p.price_minor=data.price_minor
    p.verification_status = "verified" if match_approved_admin_record(
        db, user, product_name=p.product_name, brand=p.brand, category=p.category,
        serial_number=p.serial_number, purchase_date=p.purchase_date,
        warranty_end=p.warranty_end, price_minor=p.price_minor
    ) else "rejected"
    db.commit(); db.refresh(p)
    return p

@app.post("/api/v1/purchases/{purchase_id}/invoice", status_code=201)
async def upload_invoice(purchase_id: int, file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.scalar(select(Purchase).where(Purchase.id == purchase_id, Purchase.owner_id == user.id))
    if not p: raise HTTPException(status_code=404, detail="Purchase not found")
    if file.content_type not in ALLOWED_TYPES: raise HTTPException(status_code=415, detail="Only PDF, JPEG, PNG and WebP invoices are accepted")
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if not raw: raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(raw) > MAX_UPLOAD_BYTES: raise HTTPException(status_code=413, detail="Maximum invoice size is 8 MB")
    ext = {"application/pdf":".pdf","image/jpeg":".jpg","image/png":".png","image/webp":".webp"}[file.content_type]
    name = f"{uuid.uuid4().hex}{ext}"
    target = UPLOAD_DIR / name
    target.write_bytes(raw)
    p.invoice_path = name; p.invoice_status = "uploaded"; p.verification_status = "pending"
    db.commit()
    return {"message":"Invoice uploaded to private storage", "invoice_status":p.invoice_status, "verification_status":p.verification_status, "sha256":hashlib.sha256(raw).hexdigest(), "ocr_status":"not_implemented"}
@app.get("/api/v1/claims", response_model=list[ClaimOut])
def list_claims(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Claim).where(Claim.owner_id == user.id).order_by(Claim.created_at.desc())).all()
@app.post("/api/v1/claims", response_model=ClaimOut, status_code=201)
def create_claim(data: ClaimIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.scalar(select(Purchase).where(Purchase.id == data.purchase_id, Purchase.owner_id == user.id))
    if not p: raise HTTPException(status_code=404, detail="Purchase not found")
    if p.warranty_end < date.today(): raise HTTPException(status_code=422, detail="The recorded warranty has expired; confirm seller policy before opening a claim")
    c = Claim(owner_id=user.id, purchase_id=p.id, issue=data.issue.strip(), status="submitted")
    db.add(c); db.commit(); db.refresh(c); return c
@app.get("/api/v1/admin/product-records")
def list_admin_product_records(user: User = Depends(admin_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AdminProductRecord).order_by(AdminProductRecord.created_at.desc())).all()
    return [{ "id": r.id, "customer_email": r.customer_email, "product_name": r.product_name, "brand": r.brand, "category": r.category, "serial_number": r.serial_number, "purchase_date": r.purchase_date, "warranty_end": r.warranty_end, "price_minor": r.price_minor, "evidence_note": r.evidence_note, "created_at": r.created_at } for r in rows]

@app.post("/api/v1/admin/product-records", status_code=202)
def create_admin_product_record(data: AdminRecordIn, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    if data.warranty_end < data.purchase_date:
        raise HTTPException(status_code=422, detail="Warranty end date must not precede purchase date")
    pending = PendingAdminPurchase(customer_email=str(data.customer_email).lower().strip(), product_name=data.product_name.strip(), brand=data.brand.strip(), category=data.category, serial_number=data.serial_number.strip() if data.serial_number else None, purchase_date=data.purchase_date, warranty_end=data.warranty_end, price_minor=data.price_minor, evidence_note=data.evidence_note, created_by=user.id, status="pending")
    db.add(pending)
    db.commit()
    db.refresh(pending)
    token = jwt.encode({"pending_id": pending.id, "exp": datetime.now(timezone.utc) + timedelta(days=3)}, JWT_SECRET, algorithm=JWT_ALGORITHM)
    try:
        send_purchase_confirmation(pending.customer_email, pending.product_name, token)
    except Exception:
        db.delete(pending)
        db.commit()
        raise
    return {"message": "Confirmation email sent. The admin purchase record will only be saved after the customer accepts.", "status": "pending_confirmation"}

@app.get("/api/v1/purchase-confirmation")
def confirm_admin_purchase(token: str, decision: Literal["accept", "reject"], db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        pending_id = int(payload["pending_id"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(status_code=400, detail="Confirmation link is invalid or expired.")
    pending = db.get(PendingAdminPurchase, pending_id)
    if not pending or pending.status != "pending":
        return {"message": "This confirmation has already been handled or is unavailable."}
    if decision == "reject":
        pending.status = "rejected"
        db.commit()
        return {"message": "Purchase rejected. It was not saved to the approved admin purchase list."}
    existing = None
    if pending.serial_number:
        existing = db.scalar(select(AdminProductRecord).where(AdminProductRecord.customer_email == pending.customer_email, AdminProductRecord.serial_number == pending.serial_number).limit(1))
    if not existing:
        db.add(AdminProductRecord(customer_email=pending.customer_email, product_name=pending.product_name, brand=pending.brand, category=pending.category, serial_number=pending.serial_number, purchase_date=pending.purchase_date, warranty_end=pending.warranty_end, price_minor=pending.price_minor, evidence_note=pending.evidence_note, created_by=pending.created_by))
    pending.status = "accepted"
    db.commit()
    return {"message": "Purchase accepted and saved to the approved admin purchase list. The customer can now register it."}

@app.get("/api/v1/admin/purchases", response_model=list[PurchaseOut])
def admin_purchases(user: User = Depends(admin_user), db: Session = Depends(get_db)):
    return db.scalars(select(Purchase).order_by(Purchase.created_at.desc())).all()
@app.patch("/api/v1/admin/purchases/{purchase_id}/verification", response_model=PurchaseOut)
def review_purchase(purchase_id: int, data: ReviewIn, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    p = db.get(Purchase, purchase_id)
    if not p: raise HTTPException(status_code=404, detail="Purchase not found")
    if not p.invoice_path: raise HTTPException(status_code=422, detail="Upload invoice evidence before reviewing")
    p.verification_status = data.status
    db.commit(); db.refresh(p); return p
@app.get("/api/v1/admin/claims", response_model=list[ClaimOut])
def admin_claims(user: User = Depends(admin_user), db: Session = Depends(get_db)):
    return db.scalars(select(Claim).order_by(Claim.created_at.desc())).all()
@app.patch("/api/v1/admin/claims/{claim_id}/status", response_model=ClaimOut)
def update_claim(claim_id: int, status_value: Literal["in_review", "approved", "rejected", "resolved"], note: str | None = None, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    c = db.get(Claim, claim_id)
    if not c: raise HTTPException(status_code=404, detail="Claim not found")
    c.status = status_value; c.admin_note = note; db.commit(); db.refresh(c); return c
