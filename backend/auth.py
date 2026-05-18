from datetime import datetime, timedelta, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel
from backend.settings import settings

router = APIRouter(prefix="/auth", tags=["auth"])
_bearer = HTTPBearer()

DEMO_USERS = {
    "alice@salesforge.demo": {"password": "demo1234", "role": "sales_rep",     "name": "Alice"},
    "bob@salesforge.demo":   {"password": "demo1234", "role": "sales_manager",  "name": "Bob"},
    "carol@salesforge.demo": {"password": "demo1234", "role": "billing_admin",  "name": "Carol"},
    "dave@salesforge.demo":  {"password": "demo1234", "role": "support_agent",  "name": "Dave"},
    "admin@salesforge.demo": {"password": "demo1234", "role": "admin",          "name": "Admin"},
}

class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    token: str
    user: dict

@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest):
    user = DEMO_USERS.get(req.email)
    if not user or user["password"] != req.password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid credentials")
    payload = {
        "sub": req.email,
        "email": req.email,
        "role": user["role"],
        "name": user["name"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=8),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return LoginResponse(token=token, user={"email": req.email,
                                             "role": user["role"],
                                             "name": user["name"]})

def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=f"Invalid token: {e}")

def current_user(creds: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)]) -> dict:
    return verify_token(creds.credentials)
