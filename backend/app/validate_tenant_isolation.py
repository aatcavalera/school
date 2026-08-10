import asyncio

from fastapi import HTTPException
from sqlalchemy import select

from app.access import CurrentUser, accessible_school_ids, require_school_access
from app.db import SessionLocal
from app.models import User
from app.models_multitenant import School, UserSchoolAccess
from app.routers.analytics import school_analytics


async def main() -> None:
    async with SessionLocal() as db:
        transaction = await db.begin()
        pilot = (await db.execute(select(School).order_by(School.created_at))).scalars().first()
        synthetic = School(code="tenant-isolation-check", name="Tenant Isolation Check")
        viewer = User(username="tenant_isolation_check", password_hash="not-used", role="viewer")
        db.add_all([synthetic, viewer]); await db.flush()
        db.add(UserSchoolAccess(user_id=viewer.id, school_id=synthetic.id, role="viewer")); await db.flush()
        current = CurrentUser(viewer.id, viewer.username, viewer.role)
        assert await accessible_school_ids(db, current) == [synthetic.id]
        await require_school_access(db, current, synthetic.id)
        try:
            await require_school_access(db, current, pilot.id)
        except HTTPException as exc:
            assert exc.status_code == 403
        else:
            raise AssertionError("Cross-tenant access was not rejected")
        try:
            await school_analytics(school_id=pilot.id, user=current, db=db)
        except HTTPException as exc:
            assert exc.status_code == 403
        else:
            raise AssertionError("Analytics API allowed cross-tenant access")
        await transaction.rollback()
    print("Tenant isolation: OK")


if __name__ == "__main__":
    asyncio.run(main())
