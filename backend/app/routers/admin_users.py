from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import CurrentUser, get_current_user
from app.db import get_db
from app.models import User
from app.models_multitenant import AuditLog, School, UserSchoolAccess
from app.security import hash_password

router = APIRouter(prefix="/api/admin/users", tags=["admin"])
ALLOWED_ROLES = {"super_admin", "operator", "school_admin", "viewer"}


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=10, max_length=128)
    role: str = "viewer"


class AccessGrant(BaseModel):
    school_id: str
    role: str = "viewer"


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role not in {"admin", "super_admin"}:
        raise HTTPException(status_code=403, detail="Akses administrator diperlukan")
    return user


@router.get("")
async def list_users(_admin: CurrentUser = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    users = (await db.execute(select(User).order_by(User.username))).scalars().all()
    access_rows = (await db.execute(select(UserSchoolAccess))).scalars().all()
    access_by_user: dict[int, list[dict]] = {}
    for row in access_rows:
        access_by_user.setdefault(row.user_id, []).append({"school_id": row.school_id, "role": row.role})
    return [{"id": user.id, "username": user.username, "role": user.role, "schools": access_by_user.get(user.id, [])} for user in users]


@router.post("")
async def create_user(payload: UserCreate, admin: CurrentUser = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    if payload.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="Role tidak valid")
    if (await db.execute(select(User.id).where(User.username == payload.username))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username sudah digunakan")
    user = User(username=payload.username, password_hash=hash_password(payload.password), role=payload.role)
    db.add(user); await db.flush()
    db.add(AuditLog(user_id=admin.id, action="user.create", details={"target_user_id": user.id, "role": payload.role}))
    await db.commit()
    return {"id": user.id, "username": user.username, "role": user.role}


@router.put("/{user_id}/schools")
async def grant_school(
    user_id: int, payload: AccessGrant, admin: CurrentUser = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    if payload.role not in {"school_admin", "viewer"}:
        raise HTTPException(status_code=400, detail="Role sekolah tidak valid")
    if await db.get(User, user_id) is None or await db.get(School, payload.school_id) is None:
        raise HTTPException(status_code=404, detail="User atau sekolah tidak ditemukan")
    stmt = pg_insert(UserSchoolAccess).values(user_id=user_id, school_id=payload.school_id, role=payload.role)
    stmt = stmt.on_conflict_do_update(constraint="uq_user_school_access", set_={"role": payload.role})
    await db.execute(stmt)
    db.add(AuditLog(user_id=admin.id, school_id=payload.school_id, action="user.school.grant", details={"target_user_id": user_id, "role": payload.role}))
    await db.commit()
    return {"ok": True}
