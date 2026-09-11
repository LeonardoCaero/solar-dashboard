"""FastAPI wrapper around SungrowClient — one endpoint, one cache, plus a
background sampler that writes to a local sqlite file so the day chart
still has data even when nobody has the dashboard open.
"""
from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.history_store import HistoryStore
from app.sungrow_client import SungrowApiError, SungrowClient
from app.usage_tracker import UsageTracker

load_dotenv()

SAMPLE_INTERVAL_SECONDS = 300  # 5min — see README for the quota math

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_background_sampler())
    yield
    task.cancel()


app = FastAPI(title="Solar Dashboard API", version="0.1.0", lifespan=lifespan)

cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)

_usage = UsageTracker(Path(__file__).resolve().parent.parent / "quota_usage.json")
_history = HistoryStore(Path(__file__).resolve().parent.parent / "history.db")

_client = SungrowClient(
    region=os.environ.get("SUNGROW_REGION", "europe"),
    app_key=os.environ["SUNGROW_APP_KEY"],
    secret_key=os.environ["SUNGROW_SECRET_KEY"],
    username=os.environ["SUNGROW_USERNAME"],
    password=os.environ["SUNGROW_PASSWORD"],
    rsa_public_key=os.environ.get("SUNGROW_RSA_PUBLIC_KEY"),
    api_call_password=os.environ.get("SUNGROW_API_CALL_PASSWORD"),
    usage_tracker=_usage,
)
_plant_id = os.environ.get("SUNGROW_PLANT_ID")


def _ttl_cache(ttl_seconds: float, fetch):
    state: dict = {"data": None, "fetched_at": 0.0}

    def get():
        if time.monotonic() - state["fetched_at"] > ttl_seconds:
            state["data"] = fetch()
            state["fetched_at"] = time.monotonic()
        return state["data"]

    return get


# plant totals (today/total energy, income, co2, alarms) barely move —
# 5min is plenty. Realtime power is what the chart needs fresh, but even
# solar power doesn't swing meaningfully inside 60s.
_get_plant_cached = _ttl_cache(300, lambda: _client.get_plant(_plant_id))
_get_realtime_cached = _ttl_cache(60, lambda: _client.get_realtime(_plant_id))
_get_faults_cached = _ttl_cache(300, lambda: _client.get_active_faults(_plant_id))


def _to_kw(data: dict) -> dict:
    def kw(watts: float) -> float:
        return round(watts / 1000, 3)

    return {
        "pv": kw(data["pv_w"]),
        "grid": kw(data["grid_w"]),
        "battery": kw(data["battery_w"]),
        "load": kw(data["load_w"]),
        "soc": data["battery_soc_pct"],
    }


async def _background_sampler():
    """Keeps sampling on SAMPLE_INTERVAL_SECONDS regardless of whether
    anyone has the dashboard open, so /api/history has no gaps."""
    while True:
        try:
            reading = _to_kw(await asyncio.to_thread(_get_realtime_cached))
            _history.add(
                pv=reading["pv"], grid=reading["grid"],
                battery=reading["battery"], load=reading["load"], soc=reading["soc"],
            )
        except SungrowApiError:
            pass  # transient API error — just try again next interval
        await asyncio.sleep(SAMPLE_INTERVAL_SECONDS)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/plant")
def get_plant():
    try:
        plant = _get_plant_cached()
        faults = _get_faults_cached()
    except SungrowApiError as err:
        raise HTTPException(status_code=502, detail=str(err)) from err

    def metric(key: str):
        field = plant.get(key)
        if isinstance(field, dict):
            return {"value": field.get("value"), "unit": field.get("unit")}
        return {"value": field, "unit": None}

    return {
        "plant_name": plant.get("ps_name"),
        "power": metric("curr_power"),
        "today_energy": metric("today_energy"),
        "total_energy": metric("total_energy"),
        "today_income": metric("today_income"),
        "co2_reduce_total": metric("co2_reduce_total"),
        # per-device fault status, not the plant's own (laggy) alarm_count
        "alarm_count": {"value": len(faults), "unit": None},
        "faults": faults,
        "updated_at": plant.get("curr_power_update_time"),
    }


@app.get("/api/realtime")
def get_realtime():
    try:
        reading = _to_kw(_get_realtime_cached())
    except SungrowApiError as err:
        raise HTTPException(status_code=502, detail=str(err)) from err

    return {
        "pv": {"value": reading["pv"], "unit": "kW"},
        "grid": {"value": reading["grid"], "unit": "kW"},
        "battery": {"value": reading["battery"], "unit": "kW"},
        "load": {"value": reading["load"], "unit": "kW"},
        "battery_soc": {"value": reading["soc"], "unit": "%"},
    }


@app.get("/api/history")
def get_history():
    """Today's samples, 00:00 to now, from the background sampler."""
    midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return [
        {
            "time": datetime.fromtimestamp(r["ts"]).strftime("%H:%M"),
            "pv": r["pv"],
            "grid": r["grid"],
            "battery": r["battery"],
            "load": r["load"],
            "soc": r["soc"],
        }
        for r in _history.since(int(midnight.timestamp()))
    ]


@app.get("/api/quota")
def get_quota():
    """Self-tracked, not an official number from Sungrow — they don't
    expose a "calls remaining" endpoint, so this counts our own requests
    against the documented free-tier limits."""
    snap = _usage.snapshot()
    return {
        "hour_used": snap["hour_used"],
        "hour_limit": snap["hour_limit"],
        "month_used": snap["month_used"],
        "month_limit": snap["month_limit"],
    }
