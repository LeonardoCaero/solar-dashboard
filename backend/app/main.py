"""FastAPI wrapper around SungrowClient — one endpoint, one cache.

ponytail: no DB/history here on purpose — long-term stats already live in
Home Assistant's recorder (see the sungrow_isolarcloud custom_component).
This API is just the live snapshot for the web dashboard / wall widget.
"""
from __future__ import annotations

import os
import time

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.sungrow_client import SungrowApiError, SungrowClient

load_dotenv()

app = FastAPI(title="Solar Dashboard API", version="0.1.0")

cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)

_client = SungrowClient(
    region=os.environ.get("SUNGROW_REGION", "europe"),
    app_key=os.environ["SUNGROW_APP_KEY"],
    secret_key=os.environ["SUNGROW_SECRET_KEY"],
    username=os.environ["SUNGROW_USERNAME"],
    password=os.environ["SUNGROW_PASSWORD"],
    rsa_public_key=os.environ.get("SUNGROW_RSA_PUBLIC_KEY"),
    api_call_password=os.environ.get("SUNGROW_API_CALL_PASSWORD"),
)
_plant_id = os.environ.get("SUNGROW_PLANT_ID")

_CACHE_TTL_SECONDS = 60
_cache: dict = {"data": None, "fetched_at": 0.0}


def _get_plant_cached() -> dict:
    if time.monotonic() - _cache["fetched_at"] > _CACHE_TTL_SECONDS:
        _cache["data"] = _client.get_plant(_plant_id)
        _cache["fetched_at"] = time.monotonic()
    return _cache["data"]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/plant")
def get_plant():
    try:
        plant = _get_plant_cached()
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
        "alarm_count": metric("alarm_count"),
        "updated_at": plant.get("curr_power_update_time"),
    }
