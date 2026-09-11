import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  fetchPlant,
  fetchQuota,
  fetchRealtime,
  type PlantSnapshot,
  type QuotaSnapshot,
  type RealtimeSnapshot,
} from "./api";

// Sungrow's free API tier caps at 2000 calls/hour, 100000/month, and solar
// power doesn't change fast enough to need finer than this anyway.
const POLL_MS = 60_000;
const MAX_POINTS = 60; // 1 hour of history at this poll rate

interface FlowPoint {
  time: string;
  pv: number;
  grid: number;
  battery: number;
  load: number;
}

const SERIES = [
  { key: "pv", label: "PV", color: "var(--pv)" },
  { key: "grid", label: "Red", color: "var(--grid)" },
  { key: "battery", label: "Batería", color: "var(--battery)" },
  { key: "load", label: "Carga", color: "var(--load)" },
] as const;

function formatValue(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const n = typeof value === "string" ? Number(value) : value;
  if (Number.isNaN(n)) return String(value);
  return n.toLocaleString("es-ES", { maximumFractionDigits: 2 });
}

function StatChip({
  label,
  value,
  unit,
  color,
}: {
  label: string;
  value: string;
  unit: string | null;
  color: string;
}) {
  return (
    <div
      className="min-w-[140px] flex-1 rounded-lg border-l-2 bg-[var(--surface)] px-4 py-3"
      style={{ borderLeftColor: color }}
    >
      <p className="text-xs text-[var(--text-muted)]">{label}</p>
      <p className="font-mono text-xl font-medium">
        {value}
        {unit ? <span className="ml-1 text-sm text-[var(--text-muted)]">{unit}</span> : null}
      </p>
    </div>
  );
}

function QuotaBar({ label, used, limit }: { label: string; used: number; limit: number }) {
  const pct = Math.min(100, (used / limit) * 100);
  const color = pct > 90 ? "var(--danger)" : pct > 70 ? "var(--pv)" : "var(--battery)";
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs text-[var(--text-muted)]">
        <span>{label}</span>
        <span className="font-mono">
          {used.toLocaleString("es-ES")} / {limit.toLocaleString("es-ES")}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-[var(--border)]">
        <div
          className="h-full rounded-full transition-[width]"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
    </div>
  );
}

const LiveDot = () => (
  <span className="relative flex h-2 w-2">
    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--battery)] opacity-75" />
    <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--battery)]" />
  </span>
);

const AlertIcon = () => (
  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
    <path strokeLinejoin="round" d="M12 3 2 20h20L12 3Z" />
    <path strokeLinecap="round" d="M12 10v4M12 17h.01" />
  </svg>
);

const ChevronIcon = ({ open }: { open: boolean }) => (
  <svg
    viewBox="0 0 24 24"
    width="16"
    height="16"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    style={{ transform: open ? "rotate(180deg)" : undefined, transition: "transform 150ms" }}
  >
    <path strokeLinecap="round" strokeLinejoin="round" d="m6 9 6 6 6-6" />
  </svg>
);

export default function App() {
  const [history, setHistory] = useState<FlowPoint[]>([]);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [faultsOpen, setFaultsOpen] = useState(false);

  function toggleSeries(key: string) {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  const { data, isLoading, isError, error } = useQuery<PlantSnapshot>({
    queryKey: ["plant"],
    queryFn: fetchPlant,
    refetchInterval: 5 * 60_000,
  });

  const { data: realtime, dataUpdatedAt: realtimeUpdatedAt } = useQuery<RealtimeSnapshot>({
    queryKey: ["realtime"],
    queryFn: fetchRealtime,
    refetchInterval: POLL_MS,
  });

  const { data: quota } = useQuery<QuotaSnapshot>({
    queryKey: ["quota"],
    queryFn: fetchQuota,
    refetchInterval: POLL_MS,
  });

  useEffect(() => {
    // keyed on the fetch timestamp, not the `realtime` object — React
    // Query reuses the same object reference when two polls return
    // identical values (structural sharing), which would otherwise skip
    // this effect and leave the chart's time axis stuck
    if (!realtime || !realtimeUpdatedAt) return;
    const pv = Number(realtime.pv.value);
    const grid = Number(realtime.grid.value);
    const battery = Number(realtime.battery.value);
    const load = Number(realtime.load.value);
    if ([pv, grid, battery, load].some(Number.isNaN)) return;
    setHistory((prev) => {
      const next = [
        ...prev,
        {
          time: new Date().toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" }),
          pv,
          grid,
          battery,
          load,
        },
      ];
      return next.slice(-MAX_POINTS);
    });
  }, [realtimeUpdatedAt]);

  const faultCount = data?.faults.length ?? 0;

  return (
    <div className="mx-auto min-h-svh max-w-3xl px-5 py-10">
      <header className="mb-10 flex items-start justify-between">
        <div>
          <p className="text-sm text-[var(--text-muted)]">{data?.plant_name ?? "Cargando planta…"}</p>
        </div>
        {realtimeUpdatedAt ? (
          <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
            <LiveDot />
            {new Date(realtimeUpdatedAt).toLocaleTimeString("es-ES")}
          </div>
        ) : null}
      </header>

      {isError ? (
        <div className="rounded-lg border border-[var(--danger)]/40 bg-[var(--danger)]/10 p-4 text-sm text-[var(--danger)]">
          No se pudo conectar con el backend: {(error as Error)?.message}
        </div>
      ) : null}

      {isLoading ? (
        <p className="text-sm text-[var(--text-muted)]">Cargando…</p>
      ) : data ? (
        <>
          <div className="mb-8">
            <div className="flex items-baseline gap-2">
              <span className="font-mono text-6xl font-medium tabular-nums">
                {formatValue(realtime?.pv.value)}
              </span>
              <span className="text-2xl text-[var(--text-muted)]">kW</span>
            </div>
            <p className="mt-1 text-sm text-[var(--text-muted)]">potencia solar ahora</p>
          </div>

          <div className="mb-8 flex flex-wrap gap-3">
            <StatChip label="Red" value={formatValue(realtime?.grid.value)} unit={realtime?.grid.unit ?? null} color="var(--grid)" />
            <StatChip label="Batería" value={formatValue(realtime?.battery.value)} unit={realtime?.battery.unit ?? null} color="var(--battery)" />
            <StatChip label="Carga" value={formatValue(realtime?.load.value)} unit={realtime?.load.unit ?? null} color="var(--load)" />
            <StatChip label="SOC batería" value={formatValue(realtime?.battery_soc.value)} unit={realtime?.battery_soc.unit ?? null} color="var(--battery)" />
          </div>

          <div className="mb-8 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
            <p className="mb-3 text-sm text-[var(--text-muted)]">PV / Red / Batería / Carga — última hora</p>
            {history.length > 1 ? (
              <ResponsiveContainer width="100%" height={260}>
                <AreaChart data={history} margin={{ left: -20, right: 10, top: 5 }}>
                  <defs>
                    {SERIES.map((s) => (
                      <linearGradient key={s.key} id={`fill-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={s.color} stopOpacity={0.35} />
                        <stop offset="100%" stopColor={s.color} stopOpacity={0} />
                      </linearGradient>
                    ))}
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="time" tick={{ fontSize: 11, fill: "var(--text-muted)" }} stroke="var(--border)" />
                  <YAxis tick={{ fontSize: 11, fill: "var(--text-muted)" }} stroke="var(--border)" width={40} unit=" kW" />
                  <Tooltip
                    contentStyle={{
                      borderRadius: 10,
                      border: "1px solid var(--border)",
                      background: "var(--surface-raised)",
                      fontSize: 13,
                      color: "var(--text)",
                    }}
                    formatter={(v, name) => [`${v ?? "—"} kW`, name]}
                  />
                  <Legend
                    wrapperStyle={{ fontSize: 12, cursor: "pointer" }}
                    onClick={(e) => toggleSeries(String(e.dataKey))}
                    formatter={(value, entry) => (
                      <span style={{ opacity: hidden.has(String(entry.dataKey)) ? 0.4 : 1, color: "var(--text-muted)" }}>
                        {value}
                      </span>
                    )}
                  />
                  {SERIES.map((s) => (
                    <Area
                      key={s.key}
                      type="monotone"
                      dataKey={s.key}
                      name={s.label}
                      stroke={s.color}
                      strokeWidth={2}
                      fill={`url(#fill-${s.key})`}
                      dot={false}
                      hide={hidden.has(s.key)}
                    />
                  ))}
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <p className="py-10 text-center text-sm text-[var(--text-muted)]">
                Recogiendo datos… vuelve en un par de minutos.
              </p>
            )}
          </div>

          <div className="mb-8 grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-4">
            <div>
              <p className="text-[var(--text-muted)]">Energía hoy</p>
              <p className="font-mono">{formatValue(data.today_energy.value)} {data.today_energy.unit}</p>
            </div>
            <div>
              <p className="text-[var(--text-muted)]">Energía total</p>
              <p className="font-mono">{formatValue(data.total_energy.value)} {data.total_energy.unit}</p>
            </div>
            <div>
              <p className="text-[var(--text-muted)]">Ingreso hoy</p>
              <p className="font-mono">{formatValue(data.today_income.value)} {data.today_income.unit}</p>
            </div>
            <div>
              <p className="text-[var(--text-muted)]">CO2 evitado</p>
              <p className="font-mono">{formatValue(data.co2_reduce_total.value)} {data.co2_reduce_total.unit}</p>
            </div>
          </div>

          {faultCount > 0 ? (
            <div className="mb-6 rounded-lg border border-[var(--danger)]/30 bg-[var(--danger)]/5">
              <button
                onClick={() => setFaultsOpen((o) => !o)}
                className="flex w-full items-center justify-between px-4 py-3 text-left"
              >
                <span className="flex items-center gap-2 text-sm font-medium" style={{ color: "var(--danger)" }}>
                  <AlertIcon />
                  {faultCount} fallo{faultCount > 1 ? "s" : ""} activo{faultCount > 1 ? "s" : ""}
                </span>
                <span className="flex items-center gap-1 text-xs text-[var(--text-muted)]">
                  {faultsOpen ? "ocultar" : "ver detalles"}
                  <ChevronIcon open={faultsOpen} />
                </span>
              </button>
              {faultsOpen ? (
                <ul className="divide-y divide-[var(--border)] border-t border-[var(--border)]">
                  {data.faults.map((f, i) => (
                    <li key={i} className="px-4 py-3 text-sm">
                      <p className="font-medium">
                        {f.device_name} <span style={{ color: "var(--danger)" }}>· {f.status}</span>
                      </p>
                      <p className="mt-0.5 font-mono text-xs text-[var(--text-muted)]">
                        {f.device_type_name} · {f.model_code} · S/N {f.serial}
                      </p>
                      {f.connected_since ? (
                        <p className="text-xs text-[var(--text-muted)]">Conectado desde {f.connected_since}</p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}

          {quota ? (
            <div className="grid grid-cols-1 gap-4 border-t border-[var(--border)] pt-5 sm:grid-cols-2">
              <QuotaBar label="Cuota API (hora)" used={quota.hour_used} limit={quota.hour_limit} />
              <QuotaBar label="Cuota API (mes)" used={quota.month_used} limit={quota.month_limit} />
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
