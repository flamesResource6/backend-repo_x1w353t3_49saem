"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- Order -> "order" collection
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List


class User(BaseModel):
    """
    Users collection schema
    Collection name: "user" (lowercase of class name)
    """
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Email address")
    password_hash: str = Field(..., description="SHA256 password hash")
    address: Optional[str] = Field(None, description="Address")
    is_admin: bool = Field(False, description="Admin privileges")
    token: Optional[str] = Field(None, description="Session token for simple auth")


class Product(BaseModel):
    """
    Products collection schema
    Collection name: "product" (lowercase of class name)
    """
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field(..., description="Product category")
    image: Optional[str] = Field(None, description="Image URL")
    in_stock: bool = Field(True, description="Whether product is in stock")


class OrderItem(BaseModel):
    product_id: str = Field(..., description="Referenced product _id as string")
    title: str
    price: float
    quantity: int = Field(..., ge=1)
    image: Optional[str] = None


class Order(BaseModel):
    """
    Orders collection schema
    Collection name: "order" (lowercase of class name)
    """
    user_id: Optional[str] = Field(None, description="User placing the order")
    name: str
    address: str
    payment_method: str
    items: List[OrderItem]
    total: float = Field(..., ge=0)
    status: str = Field("pending", description="Order status")
