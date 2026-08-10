from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Parameter
from app.security import get_current_username

router = APIRouter(prefix="/api/settings", tags=["settings"])


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
