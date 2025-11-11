import os
import hashlib
import secrets
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import User, Product, Order, OrderItem

app = FastAPI(title="Mini E-Commerce API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def user_from_token(token: Optional[str]):
    if not token:
        return None
    user = db["user"].find_one({"token": token})
    if user:
        user["_id"] = str(user["_id"])
    return user


class SignupPayload(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginPayload(BaseModel):
    email: EmailStr
    password: str


class ProductPayload(BaseModel):
    title: str
    description: Optional[str] = None
    price: float
    category: str
    image: Optional[str] = None
    in_stock: bool = True


class CheckoutPayload(BaseModel):
    name: str
    address: str
    payment_method: str
    items: List[OrderItem]


@app.get("/")
def read_root():
    return {"message": "Mini E-Commerce Backend running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_name"] = db.name
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


# Auth endpoints
@app.post("/api/auth/signup")
def signup(payload: SignupPayload):
    existing = db["user"].find_one({"email": payload.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        is_admin=False,
        address=None,
        token=None,
    )
    user_id = create_document("user", new_user)
    return {"message": "Signup successful", "user_id": user_id}


@app.post("/api/auth/login")
def login(payload: LoginPayload):
    user = db["user"].find_one({"email": payload.email})
    if not user or user.get("password_hash") != hash_password(payload.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = secrets.token_hex(16)
    db["user"].update_one({"_id": user["_id"]}, {"$set": {"token": token}})
    return {"token": token, "name": user.get("name"), "is_admin": bool(user.get("is_admin", False))}


@app.get("/api/me")
def me(authorization: Optional[str] = Header(default=None, alias="Authorization")):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    user = user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"name": user.get("name"), "email": user.get("email"), "is_admin": bool(user.get("is_admin", False))}


# Product endpoints
@app.get("/api/products")
def list_products(search: Optional[str] = None):
    query = {}
    if search:
        query = {"$or": [
            {"title": {"$regex": search, "$options": "i"}},
            {"category": {"$regex": search, "$options": "i"}},
        ]}
    products = list(db["product"].find(query))
    for p in products:
        p["_id"] = str(p["_id"])
    return {"products": products}


@app.post("/api/products")
def create_product(payload: ProductPayload, authorization: Optional[str] = Header(default=None, alias="Authorization")):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    user = user_from_token(token)
    if not user or not user.get("is_admin", False):
        raise HTTPException(status_code=403, detail="Admin only")

    product = Product(**payload.model_dump())
    product_id = create_document("product", product)
    return {"product_id": product_id}


@app.put("/api/products/{product_id}")
def update_product(product_id: str, payload: ProductPayload, authorization: Optional[str] = Header(default=None, alias="Authorization")):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    user = user_from_token(token)
    if not user or not user.get("is_admin", False):
        raise HTTPException(status_code=403, detail="Admin only")

    try:
        oid = ObjectId(product_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product id")

    update = {k: v for k, v in payload.model_dump().items()}
    res = db["product"].update_one({"_id": oid}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"updated": True}


@app.delete("/api/products/{product_id}")
def delete_product(product_id: str, authorization: Optional[str] = Header(default=None, alias="Authorization")):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    user = user_from_token(token)
    if not user or not user.get("is_admin", False):
        raise HTTPException(status_code=403, detail="Admin only")

    try:
        oid = ObjectId(product_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product id")

    res = db["product"].delete_one({"_id": oid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"deleted": True}


# Orders
@app.post("/api/orders")
def create_order(payload: CheckoutPayload, authorization: Optional[str] = Header(default=None, alias="Authorization")):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    user = user_from_token(token)
    total = sum(item.price * item.quantity for item in payload.items)
    order = Order(
        user_id=user.get("_id") if user else None,
        name=payload.name,
        address=payload.address,
        payment_method=payload.payment_method,
        items=payload.items,
        total=total,
    )
    order_id = create_document("order", order)
    return {"order_id": order_id, "total": total}


@app.get("/api/orders")
def list_orders(authorization: Optional[str] = Header(default=None, alias="Authorization")):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    user = user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    query = {}
    if not user.get("is_admin", False):
        query = {"user_id": user.get("_id")}
    orders = list(db["order"].find(query).sort("created_at", -1))
    for o in orders:
        o["_id"] = str(o["_id"])
    return {"orders": orders}


# Seed sample products if empty
@app.on_event("startup")
def seed_products():
    if db is None:
        return
    count = db["product"].count_documents({})
    if count == 0:
        samples = [
            {
                "title": "Aurora Card Wallet",
                "description": "Slim RFID wallet with glassmorphic sheen.",
                "price": 29.99,
                "category": "accessories",
                "image": "https://images.unsplash.com/photo-1592417817030-2f1b1c86a8e7?q=80&w=1200&auto=format&fit=crop",
                "in_stock": True,
            },
            {
                "title": "Nebula Headphones",
                "description": "Wireless noise-cancelling over-ears.",
                "price": 129.0,
                "category": "audio",
                "image": "https://images.unsplash.com/photo-1518445145672-c8cfc6a2d6b1?q=80&w=1200&auto=format&fit=crop",
                "in_stock": True,
            },
            {
                "title": "Lumos Desk Lamp",
                "description": "Minimal, touch dimmer, USB-C powered.",
                "price": 49.5,
                "category": "home",
                "image": "https://images.unsplash.com/photo-1555041469-a586c61ea9bc?q=80&w=1200&auto=format&fit=crop",
                "in_stock": True,
            },
            {
                "title": "Flux Water Bottle",
                "description": "Insulated steel, matte gradient.",
                "price": 24.0,
                "category": "outdoors",
                "image": "https://images.unsplash.com/photo-1541506610-6913f8f24e5d?q=80&w=1200&auto=format&fit=crop",
                "in_stock": True,
            },
        ]
        for s in samples:
            create_document("product", Product(**s))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
