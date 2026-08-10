"use client";

import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { apiFetch } from "@/lib/api";

type ParamRow = { key: string; value: string; keterangan: string | null };
type SyncRun = {
  id: string;
  domain: string;
  started_at: string;
  rows_seen: number;
  rows_inserted: number;
  rows_updated: number;
  rows_unchanged: number;
  status: string;
};

export default function SettingsPage() {
  const [params, setParams] = useState<ParamRow[]>([]);
  const [runs, setRuns] = useState<SyncRun[]>([]);
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [pwMsg, setPwMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  async function refresh() {
    const [p, syncRuns] = await Promise.all([
      apiFetch("/api/settings/parameters"),
      apiFetch("/api/sync/runs"),
    ]);
    setParams(p);
    setRuns(syncRuns);
  }

  useEffect(() => {
    refresh().catch(() => {});
  }, []);

  async function saveParam(row: ParamRow) {
    await apiFetch("/api/settings/parameters", { method: "PUT", body: JSON.stringify(row) });
    await refresh();
  }

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    setPwMsg(null);
    try {
      await apiFetch("/api/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
      });
      setPwMsg({ type: "ok", text: "Password berhasil diperbarui." });
      setOldPassword("");
      setNewPassword("");
    } catch (err: any) {
      setPwMsg({ type: "err", text: err.message });
    }
  }

  return (
    <AppShell>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div className="rounded-xl bg-white p-5 shadow-card dark:bg-slate-900 xl:col-span-2">
          <h2 className="mb-1 text-base font-semibold">Sinkronisasi School ID</h2>
          <p className="mb-4 text-sm text-slate-500">
            Data dashboard diperbarui otomatis oleh worker School ID. Import Excel legacy telah dinonaktifkan
            agar data asli tidak tercampur dengan data manual atau dummy.
          </p>
          <h3 className="mb-2 mt-6 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Riwayat Sinkronisasi
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-slate-400 dark:border-slate-800">
                  <th className="py-2">Waktu</th>
                  <th className="py-2">Domain</th>
                  <th className="py-2">Dilihat</th>
                  <th className="py-2">Baru</th>
                  <th className="py-2">Berubah</th>
                  <th className="py-2">Tetap</th>
                  <th className="py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((h) => (
                  <tr key={h.id} className="border-b border-slate-50 dark:border-slate-800/50">
                    <td className="py-2">{new Date(h.started_at).toLocaleString("id-ID")}</td>
                    <td className="py-2">{h.domain}</td>
                    <td className="py-2">{h.rows_seen}</td>
                    <td className="py-2">{h.rows_inserted}</td>
                    <td className="py-2">{h.rows_updated}</td>
                    <td className="py-2">{h.rows_unchanged}</td>
                    <td className="py-2">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                          h.status === "success" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
                        }`}
                      >
                        {h.status}
                      </span>
                    </td>
                  </tr>
                ))}
                {runs.length === 0 && (
                  <tr>
                    <td colSpan={7} className="py-4 text-center text-slate-400">
                      Belum ada riwayat sinkronisasi
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-xl bg-white p-5 shadow-card dark:bg-slate-900">
            <h2 className="mb-3 text-base font-semibold">Parameter Jam Sekolah</h2>
            <div className="space-y-3">
              {params.map((p) => (
                <div key={p.key}>
                  <label className="mb-1 block text-xs font-medium text-slate-500">{p.key}</label>
                  <input
                    defaultValue={p.value}
                    onBlur={(e) => saveParam({ ...p, value: e.target.value })}
                    className="input w-full"
                  />
                </div>
              ))}
              {params.length === 0 && <p className="text-sm text-slate-400">Belum ada parameter.</p>}
            </div>
          </div>

          <div className="rounded-xl bg-white p-5 shadow-card dark:bg-slate-900">
            <h2 className="mb-3 text-base font-semibold">Ganti Password</h2>
            <form onSubmit={handleChangePassword} className="space-y-3">
              <input
                type="password"
                placeholder="Password lama"
                value={oldPassword}
                onChange={(e) => setOldPassword(e.target.value)}
                required
                className="input w-full"
              />
              <input
                type="password"
                placeholder="Password baru"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                minLength={10}
                className="input w-full"
              />
              <button type="submit" className="btn-primary w-full">
                Perbarui Password
              </button>
              {pwMsg && (
                <div
                  className={`rounded-lg px-3 py-2 text-sm ${
                    pwMsg.type === "ok" ? "bg-green-50 text-green-700" : "bg-red-50 text-red-600"
                  }`}
                >
                  {pwMsg.text}
                </div>
              )}
            </form>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
