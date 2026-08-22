import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import CurrentUser, get_current_user, require_school_access, resolve_school_id
from app.db import get_db
from app.models import Parameter
from app.models_multitenant import School
from app.security import get_current_username

router = APIRouter(prefix="/api/settings", tags=["settings"])
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ParameterIn(BaseModel):
    key: str
    value: str
    keterangan: str | None = None


@router.get("/parameters")
async def list_parameters(username: str = Depends(get_current_username), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Parameter))
    return [{"key": p.key, "value": p.value, "keterangan": p.keterangan} for p in result.scalars().all()]


@router.put("/parameters")
async def upsert_parameter(
    payload: ParameterIn, username: str = Depends(get_current_username), db: AsyncSession = Depends(get_db)
):
    stmt = pg_insert(Parameter).values(key=payload.key, value=payload.value, keterangan=payload.keterangan)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Parameter.key], set_={"value": stmt.excluded.value, "keterangan": stmt.excluded.keterangan}
    )
    await db.execute(stmt)
    await db.commit()
    return {"ok": True}


class SchoolHoursIn(BaseModel):
    school_start_time: str
    late_cutoff_time: str

    @field_validator("school_start_time", "late_cutoff_time")
    @classmethod
    def _validate_time(cls, value: str) -> str:
        if not _TIME_RE.match(value):
            raise ValueError("Format jam harus HH:MM (00:00 - 23:59)")
        return value


@router.get("/school-hours")
async def get_school_hours(
    school_id: str | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    selected = await resolve_school_id(db, user, school_id)
    school = await db.get(School, selected)
    return {
        "school_id": selected,
        "school_start_time": school.school_start_time,
        "late_cutoff_time": school.late_cutoff_time,
    }


@router.put("/school-hours")
async def set_school_hours(
    payload: SchoolHoursIn,
    school_id: str | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    selected = await resolve_school_id(db, user, school_id)
    await require_school_access(db, user, selected)
    school = await db.get(School, selected)
    school.school_start_time = payload.school_start_time
    school.late_cutoff_time = payload.late_cutoff_time
    await db.commit()
    return {"ok": True}
