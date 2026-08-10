"""Create or update the initial encrypted multi-school connection."""

import asyncio
import os

from sqlalchemy import select

from app.credential_cipher import CredentialCipher
from app.db import SessionLocal
from app.models_multitenant import School, SchoolConnection
from app.integrations.school_id.client import SchoolIdClient


async def main() -> None:
    slot = os.environ.get("SCHOOL_SLOT", "").strip()
    prefix = f"SCHOOL_{slot}_" if slot else ""
    url = os.environ.get(f"{prefix}URL_SCHOOL_ID") or os.environ.get("URL_SCHOOL_ID")
    username = os.environ.get(f"{prefix}USERNAME_SCHOOL_ID")
    password = os.environ.get(f"{prefix}PASSWORD_SCHOOL_ID")
    missing = [key for key, value in (("URL_SCHOOL_ID", url), (f"{prefix}USERNAME_SCHOOL_ID", username), (f"{prefix}PASSWORD_SCHOOL_ID", password)) if not value]
    if missing:
        raise SystemExit(f"Environment belum lengkap: {', '.join(missing)}")

    code = os.environ.get(f"{prefix}CODE") or os.environ.get("SCHOOL_CODE", "pilot-001")
    with SchoolIdClient(url, username, password) as client:
        client.login()
        name = client.school_name()
    cipher = CredentialCipher()
    async with SessionLocal() as db:
        school = (await db.execute(select(School).where(School.code == code))).scalar_one_or_none()
        if school is None:
            school = School(code=code, name=name)
            db.add(school)
            await db.flush()
        else:
            school.name = name

        connection = await db.get(SchoolConnection, school.id)
        values = {
            "base_url": url,
            "username_ciphertext": cipher.encrypt(username),
            "password_ciphertext": cipher.encrypt(password),
            "enabled": True,
        }
        if connection is None:
            db.add(SchoolConnection(school_id=school.id, **values))
        else:
            for key, value in values.items():
                setattr(connection, key, value)
        await db.commit()
        print(f"School connection registered: code={code}")


if __name__ == "__main__":
    asyncio.run(main())
