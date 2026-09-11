import axios from "axios";

export interface Metric {
  value: number | string | null;
  unit: string | null;
}

export interface Fault {
  device_name: string | null;
  status: string;
}

export interface PlantSnapshot {
  plant_name: string | null;
  power: Metric;
  today_energy: Metric;
  total_energy: Metric;
  today_income: Metric;
  co2_reduce_total: Metric;
  alarm_count: Metric;
  faults: Fault[];
  updated_at: string | null;
}

export interface RealtimeSnapshot {
  pv: Metric;
  grid: Metric;
  battery: Metric;
  load: Metric;
  battery_soc: Metric;
}

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "/api",
});

export async function fetchPlant(): Promise<PlantSnapshot> {
  const { data } = await api.get<PlantSnapshot>("/plant");
  return data;
}

export async function fetchRealtime(): Promise<RealtimeSnapshot> {
  const { data } = await api.get<RealtimeSnapshot>("/realtime");
  return data;
}
