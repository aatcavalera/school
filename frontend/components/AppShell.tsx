"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [role, setRole] = useState<string | null>(null);

  useEffect(() => {
    apiFetch("/api/auth/me").then((me) => setRole(me.role)).catch(() => {});
  }, []);

  async function logout() {
    await apiFetch("/api/auth/logout", { method: "POST" }).catch(() => {});
    router.push("/login");
  }

  const navItem = (href: string, label: string) => (
    <Link
      href={href}
      className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
        pathname?.startsWith(href)
          ? "bg-white/15 text-white"
          : "text-blue-100/80 hover:bg-white/10 hover:text-white"
      }`}
    >
      {label}
    </Link>
  );

  return (
    <div className="min-h-screen bg-white dark:bg-slate-950">
      <header className="sticky top-0 z-20 bg-[#0d1f4d] shadow-md">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between px-6 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/10">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
                <path d="M12 3L2 8l10 5 10-5-10-5z" />
                <path d="M2 12l10 5 10-5" />
                <path d="M2 16l10 5 10-5" />
              </svg>
            </div>
            <span className="text-sm font-semibold text-white">School Intelligence</span>
          </div>
          <nav className="flex items-center gap-2">
            {navItem("/analytics", "Ringkasan Sekolah")}
            {navItem("/dashboard", "Absensi")}
            {navItem("/operations", "Operasional")}
            {navItem("/settings", "Settings")}
            {role && ["admin", "super_admin"].includes(role) && navItem("/admin/users", "Kelola User")}
            <button
              onClick={logout}
              className="ml-2 rounded-lg px-3 py-1.5 text-sm font-medium text-blue-100/80 transition hover:bg-white/10 hover:text-white"
            >
              Keluar
            </button>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-[1600px] px-6 py-6">{children}</main>
    </div>
  );
}
