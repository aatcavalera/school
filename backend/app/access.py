from dataclasses import dataclass

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import User
from app.models_multitenant import School, UserSchoolAccess
from app.security import get_current_username


GLOBAL_ROLES = {"admin", "super_admin", "operator"}


@dataclass(frozen=True)
class CurrentUser:
    id: int
    username: str
    role: str


async def get_current_user(
    username: str = Depends(get_current_username), db: AsyncSession = Depends(get_db)
) -> CurrentUser:
    user = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User tidak ditemukan")
    return CurrentUser(id=user.id, username=user.username, role=user.role)


async def accessible_school_ids(db: AsyncSession, user: CurrentUser) -> list[str]:
    if user.role in GLOBAL_ROLES:
        return list((await db.execute(select(School.id).where(School.is_active.is_(True)))).scalars())
    return list((await db.execute(select(UserSchoolAccess.school_id).where(
        UserSchoolAccess.user_id == user.id
    ))).scalars())


async def require_school_access(db: AsyncSession, user: CurrentUser, school_id: str) -> None:
    if school_id not in await accessible_school_ids(db, user):
        raise HTTPException(status_code=403, detail="Tidak memiliki akses ke sekolah ini")


async def resolve_school_id(db: AsyncSession, user: CurrentUser, requested: str | None) -> str:
    allowed = await accessible_school_ids(db, user)
    if requested:
        if requested not in allowed:
            raise HTTPException(status_code=403, detail="Tidak memiliki akses ke sekolah ini")
        return requested
    if not allowed:
        raise HTTPException(status_code=403, detail="User belum memiliki akses sekolah")
    return allowed[0]
