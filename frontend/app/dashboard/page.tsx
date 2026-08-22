"use client";

import { useEffect, useState, useCallback } from "react";
import {
  PieChart,
  Pie,
  Cell,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  CartesianGrid,
} from "recharts";
import AppShell from "@/components/AppShell";
import KpiCard from "@/components/KpiCard";
import { apiFetch } from "@/lib/api";

type Filters = {
  jenjang: string[];
  kelas: string[];
  wali_kelas: string[];
  tahun_ajaran: string[];
};
type School = { id: string; code: string; name: string; is_active: boolean };
type SchoolOverview = {
  id: string; name: string; latest_attendance_date: string | null; last_sync_at: string | null;
  total_students: number; observed_students: number; present: number; absent: number;
  attendance_rate: number; pending_check_in: number; sync_status: string;
};

const RATING_COLORS: Record<string, string> = {
  "Sangat Baik": "#22c55e",
  Baik: "#3b82f6",
  Cukup: "#f59e0b",
  "Perlu Tindak Lanjut": "#ef4444",
};

function IconUsers() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  );
}
function IconCheck() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M20 6L9 17l-5-5" />
    </svg>
  );
}
function IconClock() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="10" />
      <path d="M12 6v6l4 2" />
    </svg>
  );
}
function IconDoc() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
    </svg>
  );
}
function IconBag() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="2" y="7" width="20" height="14" rx="2" />
      <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
    </svg>
  );
}
function IconX() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="10" />
      <path d="M15 9l-6 6M9 9l6 6" />
    </svg>
  );
}
function IconDoor() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M9 21V3h9v18" />
      <path d="M9 12H3" />
      <path d="M6 9l-3 3 3 3" />
    </svg>
  );
}
function IconHourglass() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M5 2h14M5 22h14M5 2c0 6 14 6 14 12S5 16 5 22" />
    </svg>
  );
}

export default function DashboardPage() {
  const [filters, setFilters] = useState<Filters>({ jenjang: [], kelas: [], wali_kelas: [], tahun_ajaran: [] });
  const [schools, setSchools] = useState<School[]>([]);
  const [overview, setOverview] = useState<SchoolOverview[]>([]);
  const [schoolId, setSchoolId] = useState("");
  const [tanggal, setTanggal] = useState("");
  const [jenjang, setJenjang] = useState("Semua");
  const [kelas, setKelas] = useState("Semua");
  const [waliKelas, setWaliKelas] = useState("Semua");
  const [tahunAjaran, setTahunAjaran] = useState("Semua");
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const qs = new URLSearchParams();
      if (schoolId) qs.set("school_id", schoolId);
      if (tanggal) qs.set("tanggal", tanggal);
      qs.set("jenjang", jenjang);
      qs.set("kelas", kelas);
      qs.set("wali_kelas", waliKelas);
      qs.set("tahun_ajaran", tahunAjaran);
      const res = await apiFetch(`/api/dashboard?${qs.toString()}`);
      setData(res);
      if (!tanggal) setTanggal(res.tanggal);
    } catch (e: any) {
      setErrorMsg(e.message);
    } finally {
      setLoading(false);
    }
  }, [schoolId, tanggal, jenjang, kelas, waliKelas, tahunAjaran]);

  useEffect(() => {
    Promise.all([apiFetch("/api/sync/schools"), apiFetch("/api/dashboard/overview")])
      .then(([schoolRows, overviewData]) => {
        setSchools(schoolRows);
        setOverview(overviewData.schools);
        if (schoolRows.length) setSchoolId(schoolRows[0].id);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    const suffix = schoolId ? `?school_id=${encodeURIComponent(schoolId)}` : "";
    apiFetch(`/api/dashboard/filters${suffix}`).then(setFilters).catch(() => {});
    setKelas("Semua");
    setJenjang("Semua");
    setTahunAjaran("Semua");
  }, [schoolId]);

  useEffect(() => {
    if (schoolId) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schoolId]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function applyFilters() {
    load();
  }

  function resetFilters() {
    setJenjang("Semua");
    setKelas("Semua");
    setWaliKelas("Semua");
    setTahunAjaran("Semua");
    setTimeout(load, 0);
  }

  function selectSchool(id: string) {
    setSchoolId(id);
    setTanggal("");
  }

  return (
    <AppShell>
      <div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
        {overview.map((school) => (
          <button
            key={school.id}
            onClick={() => selectSchool(school.id)}
            className={`rounded-xl border p-4 text-left shadow-sm transition ${
              schoolId === school.id
                ? "border-blue-500 bg-blue-50 ring-2 ring-blue-500/10 dark:bg-blue-950/30"
                : "border-slate-200 bg-white hover:border-blue-300 dark:border-slate-800 dark:bg-slate-900"
            }`}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-semibold text-slate-900 dark:text-white">{school.name}</p>
                <p className="mt-1 text-xs text-slate-500">{school.total_students.toLocaleString("id-ID")} siswa</p>
              </div>
              <span className={`rounded-full px-2 py-1 text-[10px] font-semibold ${school.sync_status === "healthy" ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}>
                {school.sync_status === "healthy" ? "Tersinkron" : "Menunggu"}
              </span>
            </div>
            <div className="mt-4 flex items-end justify-between">
              <div>
                <p className="text-2xl font-bold text-blue-700 dark:text-blue-300">{school.attendance_rate}%</p>
                <p className="text-[11px] text-slate-400">sudah check-in dari {school.observed_students} record</p>
                {school.pending_check_in > 0 && <p className="text-[11px] font-medium text-amber-600">{school.pending_check_in} belum check-in</p>}
              </div>
              <p className="text-right text-[11px] text-slate-400">Data terakhir<br />{school.latest_attendance_date || "Belum tersedia"}</p>
            </div>
          </button>
        ))}
      </div>
      <div className="mb-4 rounded-xl bg-white p-4 shadow-card dark:bg-slate-900">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Sekolah">
            <select value={schoolId} onChange={(e) => selectSchool(e.target.value)} className="input min-w-48">
              {schools.map((school) => <option key={school.id} value={school.id}>{school.name}</option>)}
            </select>
          </Field>
          <Field label="Tanggal">
            <input
              type="date"
              value={tanggal}
              onChange={(e) => setTanggal(e.target.value)}
              className="input"
            />
          </Field>
          <Field label="Jenjang">
            <select value={jenjang} onChange={(e) => setJenjang(e.target.value)} className="input">
              <option>Semua</option>
              {filters.jenjang.map((j) => (
                <option key={j}>{j}</option>
              ))}
            </select>
          </Field>
          <Field label="Kelas">
            <select value={kelas} onChange={(e) => setKelas(e.target.value)} className="input">
              <option>Semua</option>
              {filters.kelas.map((k) => (
                <option key={k}>{k}</option>
              ))}
            </select>
          </Field>
          <Field label="Wali Kelas">
            <select value={waliKelas} onChange={(e) => setWaliKelas(e.target.value)} className="input">
              <option>Semua</option>
              {filters.wali_kelas.map((w) => (
                <option key={w}>{w}</option>
              ))}
            </select>
          </Field>
          <Field label="Tahun Ajaran">
            <select value={tahunAjaran} onChange={(e) => setTahunAjaran(e.target.value)} className="input">
              <option>Semua</option>
              {filters.tahun_ajaran.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </Field>
          <button onClick={applyFilters} className="btn-primary">
            Terapkan
          </button>
          <button onClick={resetFilters} className="btn-secondary">
            Reset Filter
          </button>
        </div>
      </div>

      {errorMsg && (
        <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600">{errorMsg}</div>
      )}

      {data?.metadata?.is_partial && (
        <div className="mb-4 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          <span className="mt-0.5">⚠</span>
          <div>
            <p className="font-semibold">Cakupan presensi parsial</p>
            <p className="text-xs opacity-80">School ID mengembalikan {data.metadata.observed_students} dari {data.metadata.total_students} siswa ({data.metadata.coverage_percent}%) pada tanggal ini. Persentase kehadiran dihitung dari record yang tersedia.</p>
          </div>
        </div>
      )}

      {loading && !data ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-8">
          {Array.from({ length: 8 }).map((_, index) => <div key={index} className="h-28 animate-pulse rounded-xl bg-slate-200 dark:bg-slate-800" />)}
        </div>
      ) : !data ? null : (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-8">
            <KpiCard label="Total Siswa" value={data.kartu.total_siswa.toLocaleString("id-ID")} sub="Siswa Aktif" color="bg-blue-600" icon={<IconUsers />} />
            <KpiCard label="Hadir" value={data.kartu.hadir.toLocaleString("id-ID")} sub={`${data.tingkat_kehadiran.persen}%`} color="bg-green-600" icon={<IconCheck />} />
            <KpiCard label="Terlambat" value={data.kartu.terlambat} sub={pct(data.kartu.terlambat, data.kartu.record_teramati)} color="bg-orange-500" icon={<IconClock />} />
            <KpiCard label="Izin" value={data.kartu.izin} sub={pct(data.kartu.izin, data.kartu.record_teramati)} color="bg-yellow-500" icon={<IconDoc />} />
            <KpiCard label="Sakit" value={data.kartu.sakit} sub={pct(data.kartu.sakit, data.kartu.record_teramati)} color="bg-sky-500" icon={<IconBag />} />
            <KpiCard label="Alpha" value={data.kartu.alpha} sub={pct(data.kartu.alpha, data.kartu.record_teramati)} color="bg-red-600" icon={<IconX />} />
            <KpiCard label="Belum Absen Pulang" value={data.kartu.belum_absen_pulang} sub={pct(data.kartu.belum_absen_pulang, data.kartu.record_teramati)} color="bg-violet-600" icon={<IconDoor />} />
            <KpiCard label="Belum Absen Masuk" value={data.kartu.belum_absen_masuk} sub={pct(data.kartu.belum_absen_masuk, data.kartu.record_teramati)} color="bg-slate-600" icon={<IconHourglass />} />
          </div>

          <div className="mb-4 grid grid-cols-1 gap-3 xl:grid-cols-12">
            <Panel title="Komposisi Kehadiran Hari Ini" className="xl:col-span-3">
              <div className="relative">
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie
                      data={data.komposisi_kehadiran}
                      dataKey="jumlah"
                      nameKey="status"
                      innerRadius={60}
                      outerRadius={90}
                      paddingAngle={2}
                    >
                      {data.komposisi_kehadiran.map((entry: any, i: number) => (
                        <Cell key={i} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
                <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                  <span className="text-2xl font-bold text-slate-800 dark:text-white">
                    {data.tingkat_kehadiran.persen}%
                  </span>
                  <span className="text-xs text-slate-400">{data.metadata.pending_check_in ? "Sudah Check-in" : "Tingkat Kehadiran"}</span>
                </div>
              </div>
              <ul className="mt-2 space-y-1 text-sm">
                {data.komposisi_kehadiran.map((k: any) => (
                  <li key={k.status} className="flex items-center justify-between">
                    <span className="flex items-center gap-2">
                      <span className="h-2.5 w-2.5 rounded-full" style={{ background: k.color }} />
                      {k.status}
                    </span>
                    <span className="font-medium">
                      {k.jumlah} ({k.persen}%)
                    </span>
                  </li>
                ))}
              </ul>
            </Panel>

            <Panel title="Trend Kehadiran 30 Hari Terakhir" className="xl:col-span-6">
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={data.trend_30_hari}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="tanggal" tick={{ fontSize: 11 }} tickFormatter={(v) => v.slice(5)} />
                  <YAxis domain={[80, 100]} tick={{ fontSize: 11 }} unit="%" />
                  <Tooltip />
                  <Line type="monotone" dataKey="persentase" name="Persentase Kehadiran" stroke="#22c55e" strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            </Panel>

            <Panel title="Ringkasan Hari Ini" className="xl:col-span-3">
              <ul className="space-y-3 text-sm">
                <SummaryRow label="Jam Masuk Sekolah" value={data.ringkasan.jam_masuk_sekolah} />
                <SummaryRow label="Batas Terlambat" value={data.ringkasan.batas_terlambat} />
                <SummaryRow label="Jam Pulang Sekolah" value={data.ringkasan.jam_pulang_sekolah} />
                <SummaryRow label={data.metadata.pending_check_in ? "Sudah Check-in" : "Tingkat Kehadiran"} value={`${data.ringkasan.tingkat_kehadiran}%`} highlight="green" />
                <SummaryRow label="Siswa Masih di Sekolah" value={data.ringkasan.siswa_masih_di_sekolah} />
                <SummaryRow label="Total Siswa Hadir Hari Ini" value={data.ringkasan.total_siswa_hadir} />
              </ul>
            </Panel>
          </div>

          <div className="mb-4 grid grid-cols-1 gap-3 xl:grid-cols-12">
            <Panel title="Persentase Kehadiran per Jenjang" className="xl:col-span-3">
              <div className="grid grid-cols-3 gap-2">
                {data.per_jenjang.map((j: any) => (
                  <div key={j.jenjang} className="text-center">
                    <ResponsiveContainer width="100%" height={90}>
                      <PieChart>
                        <Pie
                          data={[{ v: j.persentase }, { v: 100 - j.persentase }]}
                          dataKey="v"
                          innerRadius={28}
                          outerRadius={40}
                          startAngle={90}
                          endAngle={-270}
                        >
                          <Cell fill="#22c55e" />
                          <Cell fill="#e2e8f0" />
                        </Pie>
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="-mt-14 text-sm font-bold">{j.persentase}%</div>
                    <div className="mt-10 text-xs font-medium">{j.jenjang}</div>
                    <div className="text-[11px] text-slate-400">{j.total_siswa} Siswa</div>
                  </div>
                ))}
              </div>
            </Panel>

            <Panel title={data.metadata.pending_check_in ? "Persentase Check-in per Kelas" : "Persentase Kehadiran per Kelas"} className="xl:col-span-3">
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={data.per_kelas} layout="vertical" margin={{ left: 10 }}>
                  <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11 }} unit="%" />
                  <YAxis type="category" dataKey="kelas" width={45} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="persentase" radius={[0, 4, 4, 0]}>
                    {data.per_kelas.map((k: any, i: number) => (
                      <Cell key={i} fill={k.persentase >= 95 ? "#22c55e" : k.persentase >= 90 ? "#84cc16" : k.persentase >= 80 ? "#f59e0b" : "#ef4444"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </Panel>

            <Panel title="Top 10 Siswa Terlambat" className="xl:col-span-3">
              <RankTable rows={data.top_terlambat} valueKey="hari" valueLabel="Hari" color="text-orange-600" />
            </Panel>
            <Panel title="Top 10 Siswa Alpha" className="xl:col-span-3">
              <RankTable rows={data.top_alpha} valueKey="hari" valueLabel="Hari" color="text-red-600" />
            </Panel>
          </div>

          <div className="mb-4 grid grid-cols-1 gap-3 xl:grid-cols-12">
            <Panel title="Distribusi Jam Kedatangan" className="xl:col-span-3">
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={data.distribusi_jam_kedatangan}>
                  <XAxis dataKey="label" tick={{ fontSize: 9 }} interval={0} angle={-20} textAnchor="end" height={50} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Bar dataKey="jumlah" fill="#22c55e" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Panel>
            <Panel title="Distribusi Jam Pulang" className="xl:col-span-3">
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={data.distribusi_jam_pulang}>
                  <XAxis dataKey="label" tick={{ fontSize: 9 }} interval={0} angle={-20} textAnchor="end" height={50} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Bar dataKey="jumlah" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Panel>
            <Panel title="Perlu Perhatian Hari Ini" className="xl:col-span-4">
              <ul className="space-y-2 text-sm">
                {data.perlu_perhatian.length === 0 && (
                  <li className="text-slate-400">Tidak ada catatan khusus hari ini.</li>
                )}
                {data.perlu_perhatian.map((p: string, i: number) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-red-500" />
                    <span>{p}</span>
                  </li>
                ))}
              </ul>
            </Panel>
            <Panel title={data.metadata.pending_check_in ? "Check-in Terdata Hari Ini" : "Tingkat Kehadiran Hari Ini"} className="xl:col-span-2">
              <div className="relative">
                <ResponsiveContainer width="100%" height={140}>
                  <PieChart>
                    <Pie
                      data={[{ v: data.tingkat_kehadiran.persen }, { v: 100 - data.tingkat_kehadiran.persen }]}
                      dataKey="v"
                      innerRadius={45}
                      outerRadius={60}
                      startAngle={90}
                      endAngle={-270}
                    >
                      <Cell fill={RATING_COLORS[data.tingkat_kehadiran.rating] || "#22c55e"} />
                      <Cell fill="#e2e8f0" />
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
                <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                  <span className="text-xl font-bold">{data.tingkat_kehadiran.persen}%</span>
                  <span className="text-[11px] text-slate-400">{data.tingkat_kehadiran.rating}</span>
                </div>
              </div>
              <ul className="mt-2 space-y-1 text-[11px] text-slate-500">
                <li>&ge; 95% Sangat Baik</li>
                <li>90 - 94,9% Baik</li>
                <li>80 - 89,9% Cukup</li>
                <li>&lt; 80% Perlu Tindak Lanjut</li>
              </ul>
            </Panel>
          </div>

          <div className="mb-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
            <Panel title={`Siswa Belum Absen Masuk (${data.siswa_belum_absen_masuk.length})`}>
              <NameList rows={data.siswa_belum_absen_masuk} />
            </Panel>
            <Panel title={`Siswa Belum Absen Pulang (${data.siswa_belum_absen_pulang.length})`}>
              <NameList rows={data.siswa_belum_absen_pulang} />
            </Panel>
          </div>
        </>
      )}
    </AppShell>
  );
}

function pct(n: number, total: number) {
  if (!total) return "0%";
  return `${((100 * n) / total).toFixed(1)}%`;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-slate-500">{label}</label>
      {children}
    </div>
  );
}

function Panel({ title, children, className = "" }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl bg-white p-4 shadow-card dark:bg-slate-900 ${className}`}>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
      {children}
    </div>
  );
}

function SummaryRow({ label, value, highlight }: { label: string; value: any; highlight?: string }) {
  return (
    <li className="flex items-center justify-between border-b border-slate-100 pb-2 last:border-0 dark:border-slate-800">
      <span className="text-slate-500">{label}</span>
      <span className={`font-semibold ${highlight === "green" ? "text-green-600" : ""}`}>{value}</span>
    </li>
  );
}

function RankTable({ rows, valueKey, valueLabel, color }: { rows: any[]; valueKey: string; valueLabel: string; color: string }) {
  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-left text-slate-400">
          <th className="pb-2">No</th>
          <th className="pb-2">Nama Siswa</th>
          <th className="pb-2">Kelas</th>
          <th className="pb-2 text-right">{valueLabel}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className="border-t border-slate-100 dark:border-slate-800">
            <td className="py-1.5">{i + 1}</td>
            <td className="py-1.5">{r.nama}</td>
            <td className="py-1.5">{r.kelas}</td>
            <td className={`py-1.5 text-right font-semibold ${color}`}>{r[valueKey]}</td>
          </tr>
        ))}
        {rows.length === 0 && (
          <tr>
            <td colSpan={4} className="py-3 text-center text-slate-400">
              Tidak ada data
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

function NameList({ rows }: { rows: { nama: string; kelas: string }[] }) {
  return (
    <ul className="max-h-64 space-y-1 overflow-y-auto text-sm">
      {rows.map((r, i) => (
        <li key={i} className="flex items-center justify-between border-b border-slate-100 py-1.5 last:border-0 dark:border-slate-800">
          <span>
            {i + 1}. {r.nama}
          </span>
          <span className="text-xs text-slate-400">{r.kelas}</span>
        </li>
      ))}
      {rows.length === 0 && <li className="py-3 text-center text-slate-400">Tidak ada data</li>}
    </ul>
  );
}
