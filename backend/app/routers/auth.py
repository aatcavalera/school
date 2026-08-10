from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import User
from app.security import create_access_token, get_current_username, hash_password, verify_password
from app.login_limiter import login_limiter
from app.config import settings
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/auth", tags=["auth"])


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=10, max_length=128)


@router.post("/login")
async def login(request: Request, response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    client_key = request.client.host if request.client else "unknown"
    if not login_limiter.allowed(client_key):
        raise HTTPException(status_code=429, detail="Terlalu banyak percobaan login. Coba kembali beberapa menit lagi")
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form_data.password, user.password_hash):
        login_limiter.fail(client_key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Username atau password salah")
    login_limiter.success(client_key)
    token = create_access_token(subject=user.username)
    response.set_cookie(
        "token", token, max_age=settings.jwt_expire_minutes * 60, httponly=True,
        secure=settings.environment == "production", samesite="lax", path="/",
    )
    return {"ok": True, "username": user.username, "role": user.role}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("token", path="/")
    return {"ok": True}


@router.get("/me")
async def me(username: str = Depends(get_current_username), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    return {"username": user.username, "role": user.role}


@router.post("/change-password")
async def change_password(
    payload: PasswordChange,
    username: str = Depends(get_current_username),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Password lama salah")
    user.password_hash = hash_password(payload.new_password)
    await db.commit()
    return {"ok": True}
