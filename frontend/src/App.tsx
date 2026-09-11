import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchPlant, type PlantSnapshot } from "./api";

// Sungrow's free API tier caps at 2000 calls/hour, 100000/month, and solar
// power doesn't change fast enough to need finer than this anyway.
const POLL_MS = 60_000;
const MAX_POINTS = 60; // 1 hour of history at this poll rate

interface PowerPoint {
  time: string;
  power: number;
}

function formatValue(value: number | string | null): string {
  if (value === null || value === undefined) return "—";
  const n = typeof value === "string" ? Number(value) : value;
  if (Number.isNaN(n)) return String(value);
  return n.toLocaleString("es-ES", { maximumFractionDigits: 2 });
}

function StatCard({
  label,
  value,
  unit,
  icon,
  accent,
}: {
  label: string;
  value: string;
  unit: string | null;
  icon: React.ReactNode;
  accent: string;
}) {
  return (
    <div className="flex flex-1 min-w-[160px] items-center gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl"
        style={{ background: `${accent}1a`, color: accent }}
      >
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-sm text-slate-500 dark:text-slate-400">{label}</p>
        <p className="truncate text-2xl font-semibold text-slate-900 dark:text-slate-50">
          {value}
          {unit ? (
            <span className="ml-1 text-base font-normal text-slate-400">
              {unit}
            </span>
          ) : null}
        </p>
      </div>
    </div>
  );
}

const SunIcon = () => (
  <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="12" cy="12" r="4" />
    <path
      strokeLinecap="round"
      d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"
    />
  </svg>
);

const LeafIcon = () => (
  <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M4 20c8 0 14-6 16-16C10 6 4 12 4 20Z" strokeLinejoin="round" />
    <path d="M4 20c4-6 8-10 16-16" strokeLinecap="round" />
  </svg>
);

const CounterIcon = () => (
  <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2">
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <path strokeLinecap="round" d="M7 9h4M7 13h6M7 17h3" />
  </svg>
);

const CoinIcon = () => (
  <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="12" cy="12" r="9" />
    <path strokeLinecap="round" d="M12 7v10M9 9.5c0-1.4 1.3-2.5 3-2.5s3 1.1 3 2.5-1.3 1.9-3 2.5-3 1.1-3 2.5 1.3 2.5 3 2.5 3-1.1 3-2.5" />
  </svg>
);

const AlertIcon = () => (
  <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
    <path strokeLinejoin="round" d="M12 3 2 20h20L12 3Z" />
    <path strokeLinecap="round" d="M12 10v4M12 17h.01" />
  </svg>
);

export default function App() {
  const [history, setHistory] = useState<PowerPoint[]>([]);

  const { data, isLoading, isError, error, dataUpdatedAt } = useQuery<PlantSnapshot>({
    queryKey: ["plant"],
    queryFn: fetchPlant,
    refetchInterval: POLL_MS,
  });

  useEffect(() => {
    if (!data) return;
    const power = Number(data.power.value);
    if (Number.isNaN(power)) return;
    setHistory((prev) => {
      const next = [
        ...prev,
        {
          time: new Date().toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" }),
          power,
        },
      ];
      return next.slice(-MAX_POINTS);
    });
  }, [data]);

  return (
    <div className="mx-auto min-h-svh max-w-4xl px-5 py-8">
      <header className="mb-8 flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-slate-50">
            ☀️ Solar
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {data?.plant_name ?? "Cargando planta…"}
          </p>
        </div>
        {dataUpdatedAt ? (
          <p className="text-xs text-slate-400">
            Actualizado {new Date(dataUpdatedAt).toLocaleTimeString("es-ES")}
          </p>
        ) : null}
      </header>

      {isError ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          No se pudo conectar con el backend: {(error as Error)?.message}
        </div>
      ) : null}

      {isLoading ? (
        <p className="text-sm text-slate-400">Cargando…</p>
      ) : data ? (
        <>
          <div className="mb-4 flex flex-wrap gap-4">
            <StatCard
              label="Potencia"
              value={formatValue(data.power.value)}
              unit={data.power.unit}
              icon={<SunIcon />}
              accent="#f59e0b"
            />
            <StatCard
              label="Hoy"
              value={formatValue(data.today_energy.value)}
              unit={data.today_energy.unit}
              icon={<LeafIcon />}
              accent="#22c55e"
            />
            <StatCard
              label="Total"
              value={formatValue(data.total_energy.value)}
              unit={data.total_energy.unit}
              icon={<CounterIcon />}
              accent="#3b82f6"
            />
          </div>

          <div className="mb-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <p className="mb-3 text-sm font-medium text-slate-600 dark:text-slate-300">
              Potencia en esta sesión
            </p>
            {history.length > 1 ? (
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={history} margin={{ left: -20, right: 10, top: 5 }}>
                  <defs>
                    <linearGradient id="powerFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#f59e0b" stopOpacity={0.4} />
                      <stop offset="100%" stopColor="#f59e0b" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-slate-100 dark:text-slate-800" />
                  <XAxis dataKey="time" tick={{ fontSize: 11 }} stroke="currentColor" className="text-slate-400" />
                  <YAxis tick={{ fontSize: 11 }} stroke="currentColor" className="text-slate-400" width={40} />
                  <Tooltip
                    contentStyle={{ borderRadius: 12, border: "1px solid #e2e8f0", fontSize: 13 }}
                    formatter={(v) => [`${v ?? "—"} ${data.power.unit ?? ""}`, "Potencia"]}
                  />
                  <Area type="monotone" dataKey="power" stroke="#f59e0b" strokeWidth={2} fill="url(#powerFill)" />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <p className="py-10 text-center text-sm text-slate-400">
                Recogiendo datos… vuelve en un par de minutos.
              </p>
            )}
          </div>

          <div className="flex flex-wrap gap-4">
            <StatCard
              label="Ingreso hoy"
              value={formatValue(data.today_income.value)}
              unit={data.today_income.unit}
              icon={<CoinIcon />}
              accent="#a855f7"
            />
            <StatCard
              label="CO2 evitado (total)"
              value={formatValue(data.co2_reduce_total.value)}
              unit={data.co2_reduce_total.unit}
              icon={<LeafIcon />}
              accent="#10b981"
            />
            <StatCard
              label="Alarmas activas"
              value={formatValue(data.alarm_count.value)}
              unit={null}
              icon={<AlertIcon />}
              accent={Number(data.alarm_count.value) > 0 ? "#ef4444" : "#64748b"}
            />
          </div>
        </>
      ) : null}
    </div>
  );
}
