import asyncio

from app.db import SessionLocal
from app.routers.dashboard_synced import build_synced_dashboard, synced_filters


async def main() -> None:
    async with SessionLocal() as db:
        filters = await synced_filters(db)
        dashboard = await build_synced_dashboard(db, None, "Semua", "Semua", "Semua", "Semua")
    print({
        "tanggal": dashboard["tanggal"], "total_siswa": dashboard["kartu"]["total_siswa"],
        "observed": sum(dashboard["kartu"][key] for key in ("hadir", "terlambat", "izin", "sakit", "alpha")),
        "kelas": len(filters["kelas"]), "jenjang": len(filters["jenjang"]),
        "trend_days": len(dashboard["trend_30_hari"]),
    })


if __name__ == "__main__":
    asyncio.run(main())
