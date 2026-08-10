export default function KpiCard({
  label,
  value,
  sub,
  color,
  icon,
}: {
  label: string;
  value: string | number;
  sub?: string;
  color: string;
  icon: React.ReactNode;
}) {
  return (
    <div className={`rounded-xl ${color} p-4 text-white shadow-card`}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide opacity-90">{label}</span>
        <div className="opacity-90">{icon}</div>
      </div>
      <div className="mt-2 text-3xl font-bold">{value}</div>
      {sub && <div className="mt-0.5 text-xs opacity-90">{sub}</div>}
    </div>
  );
}
