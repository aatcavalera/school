"use client";

import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { apiFetch } from "@/lib/api";

export default function OperationsPage() {
  const [status, setStatus] = useState<any>(null);
  const [storage, setStorage] = useState<any>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    Promise.all([apiFetch("/api/operations/status"), apiFetch("/api/operations/storage")])
      .then(([statusRows, storageRows]) => { setStatus(statusRows); setStorage(storageRows); })
      .catch((reason) => setError(reason.message));
  }, []);
  return <AppShell>
    <div className="mb-6"><p className="text-xs font-bold uppercase tracking-[.2em] text-blue-600">Observability</p><h1 className="text-2xl font-bold">Operasional Platform</h1><p className="mt-1 text-sm text-slate-500">Kinerja API, antrean sinkronisasi, alert, dan pertumbuhan storage.</p></div>
    {error && <div className="rounded-xl bg-red-50 p-4 text-red-700">{error}</div>}
    {!status ? <div className="h-40 animate-pulse rounded-xl bg-slate-100" /> : <>
      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Card label="API p50" value={`${status.telemetry.latency_ms.p50} ms`} />
        <Card label="API p95" value={`${status.telemetry.latency_ms.p95} ms`} />
        <Card label="Request" value={format(status.telemetry.request_count)} />
        <Card label="Queue" value={format(status.queue.queued || 0)} />
        <Card label="Database" value={bytes(status.database_bytes)} />
      </div>
      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title={`Alert Aktif (${status.alerts.length})`}>{status.alerts.length ? <div className="space-y-2">{status.alerts.map((row:any,index:number)=><div key={index} className={`rounded-lg border p-3 text-sm ${row.severity === "critical" ? "border-red-200 bg-red-50 text-red-800" : "border-amber-200 bg-amber-50 text-amber-800"}`}><b className="mr-2 uppercase">{row.severity}</b>{row.message}<p className="mt-1 text-[11px] opacity-70">{row.domain || "platform"}</p></div>)}</div> : <p className="py-8 text-center text-sm text-emerald-600">Tidak ada alert aktif.</p>}</Panel>
        <Panel title="Status Queue"><div className="grid grid-cols-2 gap-2">{Object.entries(status.queue).map(([name,value])=><div key={name} className="rounded-lg bg-slate-50 p-3 dark:bg-slate-800"><p className="text-xs uppercase text-slate-400">{name}</p><p className="text-2xl font-bold">{format(value as number)}</p></div>)}</div></Panel>
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="Storage per Sekolah">{storage?.tenants.map((row:any)=><div key={row.school_id} className="mb-2 flex items-center justify-between rounded-lg border border-slate-100 p-3 dark:border-slate-800"><div><p className="font-semibold">{row.school_name}</p><p className="text-xs text-slate-400">Seluruh domain terstruktur</p></div><b>{format(row.total_rows)} baris</b></div>)}</Panel>
        <Panel title="Tabel Terbesar"><div className="space-y-2">{storage?.relations.slice(0,10).map((row:any)=><div key={row.name} className="flex justify-between border-b border-slate-100 pb-2 text-sm dark:border-slate-800"><span>{row.name}</span><b>{bytes(row.bytes)}</b></div>)}</div></Panel>
      </div>
    </>}
  </AppShell>;
}
function Card({label,value}:{label:string;value:string}) { return <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"><p className="text-[11px] font-bold uppercase text-slate-400">{label}</p><p className="mt-2 text-2xl font-bold">{value}</p></div>; }
function Panel({title,children}:{title:string;children:React.ReactNode}) { return <section className="rounded-xl border border-slate-100 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900"><h2 className="mb-4 text-xs font-bold uppercase tracking-wider text-slate-500">{title}</h2>{children}</section>; }
function format(value:number){return value.toLocaleString("id-ID");}
function bytes(value:number){const units=["B","KB","MB","GB"];let size=value,index=0;while(size>=1024&&index<units.length-1){size/=1024;index++;}return `${size.toFixed(index?1:0)} ${units[index]}`;}
