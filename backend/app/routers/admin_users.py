from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import CurrentUser, get_current_user
from app.db import get_db
from app.models import User
from app.models_multitenant import SCHOOL_CATEGORIES, AuditLog, School, UserDiknasScope, UserSchoolAccess
from app.security import hash_password

router = APIRouter(prefix="/api/admin/users", tags=["admin"])
# school_admin/viewer: akses ke sekolah tertentu (UserSchoolAccess).
# diknas: akses ke semua sekolah aktif dalam kategori yang di-assign (UserDiknasScope).
# cluster: akses ke semua sekolah aktif terdaftar di skul.id, tanpa batas kategori.
ALLOWED_ROLES = {"super_admin", "operator", "cluster", "diknas", "school_admin", "viewer"}


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=10, max_length=128)
    role: str = "viewer"


class AccessGrant(BaseModel):
    school_id: str
    role: str = "viewer"


class DiknasScopeSet(BaseModel):
    categories: list[str]


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
    diknas_rows = (await db.execute(select(UserDiknasScope))).scalars().all()
    diknas_by_user: dict[int, list[str]] = {}
    for row in diknas_rows:
        diknas_by_user.setdefault(row.user_id, []).append(row.category)
    return [{
        "id": user.id, "username": user.username, "role": user.role,
        "schools": access_by_user.get(user.id, []),
        "diknas_categories": diknas_by_user.get(user.id, []),
    } for user in users]


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


@router.put("/{user_id}/diknas-scope")
async def set_diknas_scope(
    user_id: int, payload: DiknasScopeSet, admin: CurrentUser = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """Replace the full set of categories a diknas user oversees."""
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    invalid = [c for c in payload.categories if c not in SCHOOL_CATEGORIES]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Kategori tidak valid: {', '.join(invalid)}")
    await db.execute(UserDiknasScope.__table__.delete().where(UserDiknasScope.user_id == user_id))
    for category in set(payload.categories):
        db.add(UserDiknasScope(user_id=user_id, category=category))
    db.add(AuditLog(
        user_id=admin.id, action="user.diknas_scope.set",
        details={"target_user_id": user_id, "categories": payload.categories},
    ))
    await db.commit()
    return {"ok": True, "categories": sorted(set(payload.categories))}


@router.get("/schools")
async def list_schools_for_admin(_admin: CurrentUser = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    schools = (await db.execute(select(School).order_by(School.name))).scalars().all()
    return [{
        "id": s.id, "code": s.code, "name": s.name, "category": s.category, "is_active": s.is_active,
        "school_start_time": s.school_start_time, "late_cutoff_time": s.late_cutoff_time,
    } for s in schools]


class SchoolCategoryUpdate(BaseModel):
    category: str


@router.put("/schools/{school_id}/category")
async def set_school_category(
    school_id: str, payload: SchoolCategoryUpdate, admin: CurrentUser = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    if payload.category not in SCHOOL_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Kategori harus salah satu dari: {', '.join(SCHOOL_CATEGORIES)}")
    school = await db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="Sekolah tidak ditemukan")
    school.category = payload.category
    db.add(AuditLog(user_id=admin.id, school_id=school_id, action="school.category.set", details={"category": payload.category}))
    await db.commit()
    return {"ok": True}
