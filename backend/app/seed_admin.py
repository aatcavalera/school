import asyncio
import os
import secrets
import string

from sqlalchemy import select

from app.db import Base, SessionLocal, engine
from app.models import User
from app.security import hash_password


def _generate_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    username = os.environ.get("ADMIN_USERNAME", "admin")
    password = os.environ.get("ADMIN_PASSWORD") or _generate_password()

    async with SessionLocal() as db:
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if user:
            print(f"User '{username}' sudah ada, tidak dibuat ulang.")
            return
        user = User(username=username, password_hash=hash_password(password), role="admin")
        db.add(user)
        await db.commit()

    print("=== ADMIN CREDENTIALS ===")
    print(f"username: {username}")
    print(f"password: {password}")
    print("=========================")


if __name__ == "__main__":
    asyncio.run(main())
