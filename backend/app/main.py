"""FastAPI wrapper around SungrowClient — one endpoint, one cache.

ponytail: no DB/history here on purpose — long-term stats already live in
Home Assistant's recorder (see the sungrow_isolarcloud custom_component).
This API is just the live snapshot for the web dashboard / wall widget.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.sungrow_client import SungrowApiError, SungrowClient
from app.usage_tracker import UsageTracker

load_dotenv()

app = FastAPI(title="Solar Dashboard API", version="0.1.0")

cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)

_usage = UsageTracker(Path(__file__).resolve().parent.parent / "quota_usage.json")

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
        data = _get_realtime_cached()
    except SungrowApiError as err:
        raise HTTPException(status_code=502, detail=str(err)) from err

    def kw(watts: float) -> float:
        return round(watts / 1000, 3)

    return {
        "pv": {"value": kw(data["pv_w"]), "unit": "kW"},
        "grid": {"value": kw(data["grid_w"]), "unit": "kW"},
        "battery": {"value": kw(data["battery_w"]), "unit": "kW"},
        "load": {"value": kw(data["load_w"]), "unit": "kW"},
        "battery_soc": {"value": data["battery_soc_pct"], "unit": "%"},
    }


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
