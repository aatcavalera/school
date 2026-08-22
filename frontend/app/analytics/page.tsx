"use client";

import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import AppShell from "@/components/AppShell";
import { apiFetch } from "@/lib/api";

type School = { id: string; name: string };
type Analytics = {
  school: { id: string; code: string; name: string; timezone: string };
  executive: { students: number; teachers: number; classes: number; subjects: number; student_teacher_ratio: number; average_class_size: number; active_year: string | null; last_sync_at: string | null };
  students: { by_gender: Datum[]; gender_estimate: { counts:Datum[]; estimated:number; unresolved:number; average_confidence:number; method:string }; by_status: Datum[]; by_level: { level: string; classes: number; students: number }[]; completeness: { field: string; filled: number; percent: number }[] };
  teachers: { active: number; homeroom_assignments: number; by_gender: Datum[]; gender_estimate:Datum[] };
  academic: { classes: ClassRow[]; subjects: string[]; school_years: { name: string; active: boolean }[] };
  attendance: { latest_date: string | null; dates_available: number; records: number; unique_students:number; historical_coverage_percent:number; latest_observed: number; coverage_percent: number; attendance_rate: number; pending_check_in:number; status: Datum[] };
  operations: { last_success_at: string | null; error_count: number; domains: { domain: string; scope: string; last_success_at: string | null }[]; recent_runs: { domain: string; status: string; started_at: string; rows_seen: number; rows_changed: number }[] };
};
type Datum = { name: string; value: number };
type ClassRow = { id: string; name: string; level: string; students: number; source_students: number; has_homeroom_teacher: boolean };
type Insights = { period_comparison: { date:string; observed:number; attendance_rate:number }[]; attendance_change_points:number|null; at_risk_students: { student_id:string; name:string; class_name:string; alpha:number; late:number; observations:number; risk_score:number }[]; class_anomalies: { class_name:string; observed:number; attendance_rate:number; gap_from_average:number }[] };

const COLORS = ["#2563eb", "#ec4899", "#94a3b8", "#22c55e", "#f59e0b", "#ef4444"];
const DOMAIN_NAMES: Record<string, string> = {
  school_years: "Tahun ajaran", students: "Siswa", teachers: "Guru", classes: "Kelas",
  subjects: "Mata pelajaran", student_attendance_summary: "Ringkasan presensi", student_attendance_daily: "Presensi harian",
};

export default function AnalyticsPage() {
  const [schools, setSchools] = useState<School[]>([]);
  const [schoolId, setSchoolId] = useState("");
  const [data, setData] = useState<Analytics | null>(null);
  const [insights, setInsights] = useState<Insights | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    apiFetch("/api/sync/schools").then((rows: School[]) => {
      setSchools(rows);
      if (rows.length) setSchoolId(rows[0].id);
      else setLoading(false);
    }).catch((reason) => { setError(reason.message); setLoading(false); });
  }, []);

  useEffect(() => {
    if (!schoolId) return;
    setLoading(true); setError("");
    Promise.all([
      apiFetch(`/api/analytics?school_id=${encodeURIComponent(schoolId)}`),
      apiFetch(`/api/analytics/insights?school_id=${encodeURIComponent(schoolId)}`),
    ]).then(([analytics, insightRows]) => { setData(analytics); setInsights(insightRows); })
      .catch((reason) => setError(reason.message)).finally(() => setLoading(false));
  }, [schoolId, refreshToken]);

  return (
    <AppShell>
      <div className="mb-6 flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
        <div>
          <p className="mb-1 text-xs font-bold uppercase tracking-[0.2em] text-blue-600">Portal Analitik Sekolah</p>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">{data?.school.name || "Ringkasan Sekolah"}</h1>
          <p className="mt-1 text-sm text-slate-500">Kesiswaan, SDM, akademik, kehadiran, dan kesehatan data dalam satu tampilan.</p>
        </div>
        <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Sekolah
          <select className="input mt-1 block min-w-64 normal-case" value={schoolId} onChange={(event) => setSchoolId(event.target.value)}>
            {schools.map((school) => <option key={school.id} value={school.id}>{school.name}</option>)}
          </select>
        </label>
      </div>

      {error && <div className="mb-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>}
      {loading && !data ? <Skeleton /> : data && (
        <Portal data={data} insights={insights} schoolId={schoolId} onCorrected={() => setRefreshToken((v) => v + 1)} />
      )}
    </AppShell>
  );
}

function Portal({ data, insights, schoolId, onCorrected }: { data: Analytics; insights: Insights | null; schoolId:string; onCorrected: () => void }) {
  const e = data.executive;
  const studentGenderMissing = data.students.by_gender.find((row) => row.name === "Belum terisi")?.value || 0;
  const teacherGenderMissing = data.teachers.by_gender.find((row) => row.name === "Belum terisi")?.value || 0;
  const studentGenderPresentation = [
    ...data.students.by_gender.filter((row) => row.name !== "Belum terisi").map((row) => ({...row, name:`${row.name} · terverifikasi`})),
    ...data.students.gender_estimate.counts.filter((row) => row.name !== "Belum dapat ditentukan" && row.value > 0).map((row) => ({...row, name:`${row.name} · estimasi`})),
    {name:"Belum dapat ditentukan", value:data.students.gender_estimate.unresolved},
  ];
  return <>
    <section className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      <Metric label="Siswa" value={format(e.students)} detail="Master aktif" tone="blue" />
      <Metric label="Guru" value={format(e.teachers)} detail={`${data.teachers.active} aktif`} tone="emerald" />
      <Metric label="Kelas" value={format(e.classes)} detail={`Rata-rata ${e.average_class_size} siswa`} tone="violet" />
      <Metric label="Mata Pelajaran" value={format(e.subjects)} detail="Master akademik" tone="amber" />
      <Metric label="Rasio Siswa : Guru" value={`${e.student_teacher_ratio} : 1`} detail="Indikator kapasitas" tone="cyan" />
      <Metric label="Tahun Ajaran" value={e.active_year || "—"} detail={relativeTime(e.last_sync_at)} tone="slate" />
    </section>

    <SectionHeading eyebrow="Kesiswaan" title="Profil dan distribusi siswa" />
    {studentGenderMissing > 0 && <DataQualityNotice
      title="Jenis kelamin siswa tidak lengkap di School ID"
      message={`${format(studentGenderMissing)} siswa tidak memiliki nilai resmi. Pola nama lengkap mengestimasi ${format(data.students.gender_estimate.estimated)} siswa dengan confidence rata-rata ${Math.round(data.students.gender_estimate.average_confidence*100)}%; ${format(data.students.gender_estimate.unresolved)} tetap belum dapat ditentukan. Estimasi ditandai dan tidak menimpa School ID.`}
    />}
    {studentGenderMissing > 0 && <GenderReviewPanel schoolId={schoolId} onCorrected={onCorrected} />}
    <section className="mb-8 grid grid-cols-1 gap-4 xl:grid-cols-12">
      <Panel title="Siswa per Tingkat" className="xl:col-span-5">
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={data.students.by_level}><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey="level" /><YAxis /><Tooltip /><Bar dataKey="students" name="Siswa" fill="#2563eb" radius={[5,5,0,0]} /></BarChart>
        </ResponsiveContainer>
      </Panel>
      <Panel title="Jenis Kelamin Siswa" className="xl:col-span-3"><Donut data={studentGenderPresentation} center={format(e.students)} /></Panel>
      <Panel title="Kelengkapan Data Siswa" className="xl:col-span-4">
        <div className="space-y-4 pt-2">{data.students.completeness.map((row) => <Progress key={row.field} label={row.field} value={row.percent} detail={`${format(row.filled)} / ${format(e.students)}`} />)}</div>
      </Panel>
    </section>

    <SectionHeading eyebrow="Guru & SDM" title="Kapasitas tenaga pendidik" />
    {teacherGenderMissing > 0 && <DataQualityNotice
      title="Jenis kelamin guru tidak lengkap di School ID"
      message={`${format(teacherGenderMissing)} dari ${format(e.teachers)} guru tidak memiliki nilai jenis kelamin dari sumber.`}
    />}
    <section className="mb-8 grid grid-cols-1 gap-4 lg:grid-cols-3">
      <Metric label="Guru Aktif" value={format(data.teachers.active)} detail={`dari ${format(e.teachers)} guru tersinkron`} tone="emerald" large />
      <Metric label="Wali Kelas Terpetakan" value={format(data.teachers.homeroom_assignments)} detail={`dari ${format(e.classes)} kelas`} tone="violet" large />
      <Panel title="Jenis Kelamin Guru"><CompactLegend data={data.teachers.by_gender} /></Panel>
    </section>

    <SectionHeading eyebrow="Akademik" title="Struktur kelas dan mata pelajaran" />
    <section className="mb-8 grid grid-cols-1 gap-4 xl:grid-cols-12">
      <Panel title="Kapasitas Kelas Aktual" className="xl:col-span-8">
        <div className="max-h-[390px] overflow-auto"><table className="w-full text-sm"><thead className="sticky top-0 bg-white text-left text-xs uppercase text-slate-400 dark:bg-slate-900"><tr><th className="pb-3">Kelas</th><th className="pb-3">Tingkat</th><th className="pb-3 text-right">Siswa terhubung</th><th className="pb-3 text-center">Wali kelas</th></tr></thead><tbody>{data.academic.classes.map((row) => <tr key={row.id} className="border-t border-slate-100 dark:border-slate-800"><td className="py-2.5 font-medium">{row.name}</td><td className="py-2.5">{row.level}</td><td className="py-2.5 text-right font-semibold">{row.students}</td><td className="py-2.5 text-center"><StatusDot ok={row.has_homeroom_teacher} /></td></tr>)}</tbody></table></div>
      </Panel>
      <Panel title={`Mata Pelajaran (${data.academic.subjects.length})`} className="xl:col-span-4">
        <div className="flex max-h-[390px] flex-wrap content-start gap-2 overflow-auto">{data.academic.subjects.map((name) => <span key={name} className="rounded-full bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 dark:bg-blue-950 dark:text-blue-200">{name}</span>)}</div>
      </Panel>
    </section>

    <SectionHeading eyebrow="Kehadiran" title="Cakupan data presensi" />
    <section className="mb-8 grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Metric label="Tanggal Tersedia" value={format(data.attendance.dates_available)} detail="Hari berisi data" tone="blue" />
      <Metric label="Record Presensi" value={format(data.attendance.records)} detail={`${format(data.attendance.unique_students)} siswa unik · ${data.attendance.historical_coverage_percent}% master`} tone="slate" />
      <Metric label="Cakupan Terakhir" value={`${data.attendance.coverage_percent}%`} detail={`${data.attendance.latest_observed} siswa teramati`} tone="amber" />
      <Metric label="Sudah Check-in" value={`${data.attendance.attendance_rate}%`} detail={`${format(data.attendance.pending_check_in)} belum check-in, bukan Alpha`} tone="emerald" />
    </section>

    <section className="mb-8 grid grid-cols-1 gap-4 xl:grid-cols-12">
      <Panel title="Perbandingan Periode" className="xl:col-span-4">
        <div className="space-y-3">{insights?.period_comparison.map((row, index) => <div key={row.date} className="flex items-center justify-between rounded-lg bg-slate-50 p-3 dark:bg-slate-800"><div><p className="text-sm font-semibold">{row.date}</p><p className="text-[11px] text-slate-400">{row.observed} record teramati</p></div><b className={index === 0 ? "text-blue-600" : "text-slate-500"}>{row.attendance_rate}%</b></div>)}</div>
        {insights?.attendance_change_points != null && <p className={`mt-3 text-xs font-semibold ${insights.attendance_change_points >= 0 ? "text-emerald-600" : "text-red-600"}`}>{insights.attendance_change_points >= 0 ? "+" : ""}{insights.attendance_change_points} poin dibanding tanggal sebelumnya</p>}
      </Panel>
      <Panel title="Siswa Membutuhkan Perhatian" className="xl:col-span-5">
        <div className="max-h-64 overflow-auto"><table className="w-full text-xs"><thead><tr className="text-left text-slate-400"><th className="pb-2">Siswa</th><th>Kelas</th><th className="text-right">Alpha</th><th className="text-right">Skor</th></tr></thead><tbody>{insights?.at_risk_students.map((row) => <tr key={row.student_id} className="border-t border-slate-100 dark:border-slate-800"><td className="py-2 font-medium">{row.name}</td><td>{row.class_name}</td><td className="text-right text-red-600">{row.alpha}</td><td className="text-right font-bold">{row.risk_score}</td></tr>)}</tbody></table>{!insights?.at_risk_students.length && <p className="py-6 text-center text-sm text-slate-400">Tidak ada sinyal risiko pada data tersedia.</p>}</div>
      </Panel>
      <Panel title="Laporan" className="xl:col-span-3">
        <p className="mb-4 text-sm text-slate-500">Unduh data presensi terstruktur untuk analisis lanjutan. File dibuat langsung tanpa disimpan di server.</p>
        <a href={`/api/analytics/attendance.csv?school_id=${encodeURIComponent(schoolId)}&days=366`} className="btn-primary inline-flex">Unduh CSV Presensi</a>
        <p className="mt-3 text-[11px] text-slate-400">Maksimum 366 hari · akses mengikuti sekolah user</p>
      </Panel>
      <RecapDownloadPanel schoolId={schoolId} />
    </section>

    <SectionHeading eyebrow="Operasional Data" title="Kesehatan sinkronisasi" />
    <section className="mb-4 grid grid-cols-1 gap-4 xl:grid-cols-12">
      <Panel title="Freshness per Domain" className="xl:col-span-7"><div className="grid gap-2 sm:grid-cols-2">{data.operations.domains.map((row, index) => <div key={`${row.domain}-${row.scope}-${index}`} className="flex items-center justify-between rounded-lg border border-slate-100 p-3 dark:border-slate-800"><div><p className="text-sm font-medium">{DOMAIN_NAMES[row.domain] || row.domain}</p><p className="text-[11px] text-slate-400">{row.scope === "default" ? "Semua data" : "Scope spesifik"}</p></div><span className="text-xs font-semibold text-emerald-600">{relativeTime(row.last_success_at)}</span></div>)}</div></Panel>
      <Panel title="Aktivitas Sinkronisasi Terakhir" className="xl:col-span-5"><div className="space-y-2">{data.operations.recent_runs.map((run, index) => <div key={`${run.domain}-${run.started_at}-${index}`} className="flex items-center justify-between border-b border-slate-100 pb-2 text-sm last:border-0 dark:border-slate-800"><div><p className="font-medium">{DOMAIN_NAMES[run.domain] || run.domain}</p><p className="text-[11px] text-slate-400">{relativeTime(run.started_at)} · {format(run.rows_seen)} dibaca</p></div><span className={`rounded-full px-2 py-1 text-[10px] font-bold ${run.status === "success" ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>{run.status}</span></div>)}</div></Panel>
    </section>
  </>;
}

function Metric({ label, value, detail, tone, large=false }: { label: string; value: string; detail: string; tone: string; large?: boolean }) {
  const tones: Record<string,string> = { blue:"border-blue-200 bg-blue-50/70 text-blue-700", emerald:"border-emerald-200 bg-emerald-50/70 text-emerald-700", violet:"border-violet-200 bg-violet-50/70 text-violet-700", amber:"border-amber-200 bg-amber-50/70 text-amber-700", cyan:"border-cyan-200 bg-cyan-50/70 text-cyan-700", slate:"border-slate-200 bg-slate-50 text-slate-700" };
  return <div className={`rounded-xl border p-4 ${tones[tone]}`}><p className="text-[11px] font-bold uppercase tracking-wide opacity-70">{label}</p><p className={`${large ? "mt-3 text-4xl" : "mt-2 text-2xl"} font-bold`}>{value}</p><p className="mt-1 text-[11px] opacity-70">{detail}</p></div>;
}
function Panel({ title, children, className="" }: { title:string; children:React.ReactNode; className?:string }) { return <div className={`rounded-xl border border-slate-100 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 ${className}`}><h3 className="mb-4 text-xs font-bold uppercase tracking-wider text-slate-500">{title}</h3>{children}</div>; }
function SectionHeading({ eyebrow, title }: { eyebrow:string; title:string }) { return <div className="mb-3"><p className="text-[10px] font-bold uppercase tracking-[.2em] text-blue-600">{eyebrow}</p><h2 className="text-lg font-bold text-slate-800 dark:text-white">{title}</h2></div>; }
function Donut({ data, center }: { data:Datum[]; center:string }) { return <div><div className="relative"><ResponsiveContainer width="100%" height={180}><PieChart><Pie data={data} dataKey="value" nameKey="name" innerRadius={55} outerRadius={75}>{data.map((_,i)=><Cell key={i} fill={COLORS[i%COLORS.length]} />)}</Pie><Tooltip /></PieChart></ResponsiveContainer><div className="pointer-events-none absolute inset-0 flex items-center justify-center text-xl font-bold">{center}</div></div><CompactLegend data={data} /></div>; }
function CompactLegend({ data }: { data:Datum[] }) { return <div className="space-y-2">{data.map((row,i)=><div key={row.name} className="flex items-center justify-between text-sm"><span className="flex items-center gap-2"><i className="h-2.5 w-2.5 rounded-full" style={{background:COLORS[i%COLORS.length]}} />{row.name}</span><b>{format(row.value)}</b></div>)}</div>; }
function Progress({ label, value, detail }: { label:string; value:number; detail:string }) { return <div><div className="mb-1 flex justify-between text-xs"><span className="font-medium">{label}</span><span className="text-slate-400">{detail} · {value}%</span></div><div className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800"><div className={`h-full rounded-full ${value >= 90 ? "bg-emerald-500" : value >= 60 ? "bg-amber-500" : "bg-red-500"}`} style={{width:`${value}%`}} /></div></div>; }
function StatusDot({ ok }: { ok:boolean }) { return <span title={ok ? "Terpetakan" : "Belum terpetakan"} className={`inline-block h-2.5 w-2.5 rounded-full ${ok ? "bg-emerald-500" : "bg-slate-300"}`} />; }
function DataQualityNotice({ title, message }: { title:string; message:string }) { return <div className="mb-4 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100"><span className="rounded-full bg-amber-200 px-2 py-0.5 text-xs font-bold text-amber-800">!</span><div><p className="text-sm font-bold">{title}</p><p className="mt-1 text-xs leading-relaxed opacity-80">{message}</p></div></div>; }

function defaultSemesterStart(): string {
  const now = new Date();
  const year = now.getFullYear();
  // Semester ganjil: Juli-Des, semester genap: Jan-Jun.
  const start = now.getMonth() >= 6 ? new Date(year, 6, 1) : new Date(year, 0, 1);
  return start.toISOString().slice(0, 10);
}

function RecapDownloadPanel({ schoolId }: { schoolId: string }) {
  const [start, setStart] = useState(defaultSemesterStart());
  const [end, setEnd] = useState(new Date().toISOString().slice(0, 10));

  const url = `/api/analytics/attendance-recap.csv?school_id=${encodeURIComponent(schoolId)}&start=${start}&end=${end}`;
  const invalid = !start || !end || end < start;

  return (
    <Panel title="Rekap Kehadiran per Semester" className="xl:col-span-12">
      <p className="mb-4 text-sm text-slate-500">
        Rekap jumlah Hadir/Terlambat/Sakit/Izin/Alpa per siswa dalam rentang tanggal - untuk kebutuhan penilaian
        guru per semester. Tidak disimpan di server, dibuat langsung saat diunduh.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-500">Dari Tanggal</label>
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="input" />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-500">Sampai Tanggal</label>
          <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="input" />
        </div>
        {invalid ? (
          <span className="rounded-lg bg-slate-100 px-4 py-1.5 text-sm font-semibold text-slate-400 dark:bg-slate-800">
            Unduh CSV Rekap
          </span>
        ) : (
          <a href={url} className="btn-primary inline-flex">Unduh CSV Rekap</a>
        )}
      </div>
      {invalid && <p className="mt-2 text-xs text-red-500">Tanggal akhir harus sama atau setelah tanggal awal.</p>}
    </Panel>
  );
}

type GenderReviewItem = { entity_type: "student" | "teacher"; source_uuid: string; name: string; detail: string | null; suggested_gender: string | null; confidence: number };

function GenderReviewPanel({ schoolId, onCorrected }: { schoolId: string; onCorrected: () => void }) {
  const [items, setItems] = useState<GenderReviewItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState<string | null>(null);

  function load() {
    setLoading(true);
    apiFetch(`/api/analytics/gender-review?school_id=${encodeURIComponent(schoolId)}`)
      .then((res) => { setItems(res.items); setTotal(res.total_unresolved); })
      .finally(() => setLoading(false));
  }

  useEffect(() => { if (schoolId) load(); }, [schoolId]);

  async function correct(item: GenderReviewItem, gender: "Laki-laki" | "Perempuan") {
    const key = `${item.entity_type}:${item.source_uuid}`;
    setSavingKey(key);
    try {
      await apiFetch(`/api/analytics/gender-override?school_id=${encodeURIComponent(schoolId)}`, {
        method: "PUT",
        body: JSON.stringify({ entity_type: item.entity_type, source_uuid: item.source_uuid, gender }),
      });
      setItems((prev) => prev.filter((row) => !(row.entity_type === item.entity_type && row.source_uuid === item.source_uuid)));
      setTotal((prev) => prev - 1);
      onCorrected();
    } finally {
      setSavingKey(null);
    }
  }

  if (loading) return null;
  if (items.length === 0) return null;

  return (
    <div className="mb-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
          Koreksi Jenis Kelamin Manual ({format(total)} perlu ditinjau)
        </h3>
      </div>
      <p className="mb-3 text-xs text-slate-500">
        Nama di bawah ini tidak memiliki jenis kelamin resmi dari School ID. Sistem menebak dari pola nama —
        konfirmasi atau perbaiki sekali, tersimpan permanen dan tidak akan ditebak ulang.
      </p>
      <div className="max-h-80 space-y-2 overflow-y-auto">
        {items.map((item) => {
          const key = `${item.entity_type}:${item.source_uuid}`;
          return (
            <div
              key={key}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-100 px-3 py-2 dark:border-slate-800"
            >
              <div>
                <p className="text-sm font-medium">
                  {item.name}
                  <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-slate-500 dark:bg-slate-800">
                    {item.entity_type === "student" ? "Siswa" : "Guru"}
                  </span>
                </p>
                <p className="text-[11px] text-slate-400">
                  {item.detail ? `${item.detail} · ` : ""}
                  {item.suggested_gender
                    ? `Tebakan: ${item.suggested_gender} (${Math.round(item.confidence * 100)}%)`
                    : "Tidak dapat ditebak dari nama"}
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  disabled={savingKey === key}
                  onClick={() => correct(item, "Laki-laki")}
                  className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-700 transition hover:bg-blue-100 disabled:opacity-50"
                >
                  Laki-laki
                </button>
                <button
                  disabled={savingKey === key}
                  onClick={() => correct(item, "Perempuan")}
                  className="rounded-lg border border-pink-200 bg-pink-50 px-3 py-1.5 text-xs font-semibold text-pink-700 transition hover:bg-pink-100 disabled:opacity-50"
                >
                  Perempuan
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
function Skeleton() { return <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{Array.from({length:12}).map((_,i)=><div key={i} className="h-28 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />)}</div>; }
function format(value:number) { return value.toLocaleString("id-ID"); }
function relativeTime(value:string|null) { if(!value) return "Belum tersinkron"; const seconds=Math.max(0,(Date.now()-new Date(value).getTime())/1000); if(seconds<60)return "Baru saja"; if(seconds<3600)return `${Math.floor(seconds/60)} menit lalu`; if(seconds<86400)return `${Math.floor(seconds/3600)} jam lalu`; return `${Math.floor(seconds/86400)} hari lalu`; }
