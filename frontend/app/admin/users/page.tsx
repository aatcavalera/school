"use client";

import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { apiFetch } from "@/lib/api";

type SchoolGrant = { school_id: string; role: string };
type UserRow = { id: number; username: string; role: string; schools: SchoolGrant[]; diknas_categories: string[] };
type SchoolRow = { id: string; code: string; name: string; category: string | null; is_active: boolean; school_start_time: string | null; late_cutoff_time: string | null };

const ROLES = [
  { value: "school_admin", label: "Admin Sekolah" },
  { value: "viewer", label: "Viewer Sekolah" },
  { value: "diknas", label: "Diknas (per kategori)" },
  { value: "cluster", label: "Cluster (semua sekolah)" },
  { value: "operator", label: "Operator" },
  { value: "super_admin", label: "Super Admin" },
];
const CATEGORIES = ["SMA", "SMK", "SMP", "SD", "Lainnya"];

export default function AdminUsersPage() {
  const [users, setUsers] = useState<UserRow[]>([]);
  const [schools, setSchools] = useState<SchoolRow[]>([]);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState("viewer");
  const [creating, setCreating] = useState(false);

  async function refresh() {
    setError("");
    try {
      const [u, s] = await Promise.all([
        apiFetch("/api/admin/users"),
        apiFetch("/api/admin/users/schools"),
      ]);
      setUsers(u);
      setSchools(s);
    } catch (err: any) {
      setError(err.message);
    }
  }

  useEffect(() => { refresh(); }, []);

  function flash(type: "ok" | "err", text: string) {
    setMsg({ type, text });
    setTimeout(() => setMsg(null), 4000);
  }

  async function createUser(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    try {
      await apiFetch("/api/admin/users", {
        method: "POST",
        body: JSON.stringify({ username: newUsername, password: newPassword, role: newRole }),
      });
      setNewUsername(""); setNewPassword(""); setNewRole("viewer");
      flash("ok", `User "${newUsername}" berhasil dibuat.`);
      await refresh();
    } catch (err: any) {
      flash("err", err.message);
    } finally {
      setCreating(false);
    }
  }

  async function grantSchool(userId: number, schoolId: string, role: string) {
    try {
      await apiFetch(`/api/admin/users/${userId}/schools`, {
        method: "PUT",
        body: JSON.stringify({ school_id: schoolId, role }),
      });
      flash("ok", "Akses sekolah diperbarui.");
      await refresh();
    } catch (err: any) {
      flash("err", err.message);
    }
  }

  async function setDiknasScope(userId: number, categories: string[]) {
    try {
      await apiFetch(`/api/admin/users/${userId}/diknas-scope`, {
        method: "PUT",
        body: JSON.stringify({ categories }),
      });
      flash("ok", "Scope Diknas diperbarui.");
      await refresh();
    } catch (err: any) {
      flash("err", err.message);
    }
  }

  async function setSchoolCategory(schoolId: string, category: string) {
    try {
      await apiFetch(`/api/admin/users/schools/${schoolId}/category`, {
        method: "PUT",
        body: JSON.stringify({ category }),
      });
      flash("ok", "Kategori sekolah diperbarui.");
      await refresh();
    } catch (err: any) {
      flash("err", err.message);
    }
  }

  return (
    <AppShell>
      <h1 className="mb-1 text-xl font-bold text-slate-900 dark:text-white">Kelola User & Sekolah</h1>
      <p className="mb-6 text-sm text-slate-500">
        Admin sekolah/viewer diberi akses per sekolah. Diknas melihat semua sekolah aktif dalam kategori yang
        di-assign. Cluster melihat semua sekolah terdaftar tanpa batas kategori.
      </p>

      {error && <div className="mb-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>}
      {msg && (
        <div className={`mb-4 rounded-xl border p-3 text-sm ${msg.type === "ok" ? "border-green-200 bg-green-50 text-green-700" : "border-red-200 bg-red-50 text-red-700"}`}>
          {msg.text}
        </div>
      )}

      <div className="mb-6 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div className="rounded-xl border border-slate-100 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 xl:col-span-1">
          <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-slate-500">Buat User Baru</h2>
          <form onSubmit={createUser} className="space-y-3">
            <input
              placeholder="Username" value={newUsername} onChange={(e) => setNewUsername(e.target.value)}
              required minLength={3} className="input w-full"
            />
            <input
              type="password" placeholder="Password (min. 10 karakter)" value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)} required minLength={10} className="input w-full"
            />
            <select value={newRole} onChange={(e) => setNewRole(e.target.value)} className="input w-full">
              {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            </select>
            <button type="submit" disabled={creating} className="btn-primary w-full">
              {creating ? "Membuat..." : "Buat User"}
            </button>
          </form>
        </div>

        <div className="rounded-xl border border-slate-100 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 xl:col-span-2">
          <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-slate-500">Kategori Sekolah</h2>
          <div className="space-y-2">
            {schools.map((s) => (
              <div key={s.id} className="flex items-center justify-between gap-3 rounded-lg border border-slate-100 px-3 py-2 dark:border-slate-800">
                <div>
                  <p className="text-sm font-medium">{s.name}</p>
                  <p className="text-[11px] text-slate-400">{s.code}</p>
                </div>
                <select
                  value={s.category || ""}
                  onChange={(e) => e.target.value && setSchoolCategory(s.id, e.target.value)}
                  className="input"
                >
                  <option value="" disabled>Pilih kategori</option>
                  {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
            ))}
            {schools.length === 0 && <p className="text-sm text-slate-400">Belum ada sekolah terdaftar.</p>}
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-slate-100 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-slate-500">Daftar User</h2>
        <div className="space-y-3">
          {users.map((u) => (
            <UserCard
              key={u.id}
              user={u}
              schools={schools}
              onGrantSchool={grantSchool}
              onSetDiknasScope={setDiknasScope}
            />
          ))}
          {users.length === 0 && <p className="text-sm text-slate-400">Belum ada user.</p>}
        </div>
      </div>
    </AppShell>
  );
}

function UserCard({
  user, schools, onGrantSchool, onSetDiknasScope,
}: {
  user: UserRow; schools: SchoolRow[];
  onGrantSchool: (userId: number, schoolId: string, role: string) => void;
  onSetDiknasScope: (userId: number, categories: string[]) => void;
}) {
  const [grantSchoolId, setGrantSchoolId] = useState("");
  const [grantRole, setGrantRole] = useState("viewer");
  const [diknasCategories, setDiknasCategories] = useState<string[]>(user.diknas_categories);

  const schoolName = (id: string) => schools.find((s) => s.id === id)?.name || id;

  function toggleCategory(category: string) {
    setDiknasCategories((prev) =>
      prev.includes(category) ? prev.filter((c) => c !== category) : [...prev, category]
    );
  }

  return (
    <div className="rounded-lg border border-slate-100 p-4 dark:border-slate-800">
      <div className="mb-2 flex items-center justify-between">
        <div>
          <span className="font-semibold">{user.username}</span>
          <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-slate-500 dark:bg-slate-800">
            {ROLES.find((r) => r.value === user.role)?.label || user.role}
          </span>
        </div>
      </div>

      {(user.role === "school_admin" || user.role === "viewer") && (
        <div>
          {user.schools.length > 0 && (
            <ul className="mb-2 space-y-1 text-xs text-slate-500">
              {user.schools.map((g) => <li key={g.school_id}>{schoolName(g.school_id)} — {g.role}</li>)}
            </ul>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <select value={grantSchoolId} onChange={(e) => setGrantSchoolId(e.target.value)} className="input text-xs">
              <option value="">Pilih sekolah...</option>
              {schools.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <select value={grantRole} onChange={(e) => setGrantRole(e.target.value)} className="input text-xs">
              <option value="school_admin">Admin Sekolah</option>
              <option value="viewer">Viewer</option>
            </select>
            <button
              disabled={!grantSchoolId}
              onClick={() => grantSchoolId && onGrantSchool(user.id, grantSchoolId, grantRole)}
              className="btn-secondary text-xs disabled:opacity-50"
            >
              Beri Akses
            </button>
          </div>
        </div>
      )}

      {user.role === "diknas" && (
        <div>
          <div className="mb-2 flex flex-wrap gap-2">
            {CATEGORIES.map((c) => (
              <label key={c} className="flex items-center gap-1.5 text-xs">
                <input type="checkbox" checked={diknasCategories.includes(c)} onChange={() => toggleCategory(c)} />
                {c}
              </label>
            ))}
          </div>
          <button onClick={() => onSetDiknasScope(user.id, diknasCategories)} className="btn-secondary text-xs">
            Simpan Scope
          </button>
        </div>
      )}

      {(user.role === "cluster" || user.role === "operator" || user.role === "super_admin") && (
        <p className="text-xs text-slate-400">Akses ke semua sekolah aktif, tidak perlu diatur per sekolah.</p>
      )}
    </div>
  );
}
