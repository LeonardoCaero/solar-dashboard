"""Tiny local time series for the day chart — plain sqlite3 (stdlib, no new
dependency), pruned to the last 2 days so it never grows unbounded."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

_RETENTION_SECONDS = 2 * 86400


class HistoryStore:
    def __init__(self, path: Path):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS readings ("
            "ts INTEGER PRIMARY KEY, pv REAL, grid REAL, battery REAL, load REAL, soc REAL)"
        )
        self._conn.commit()

    def add(self, pv: float, grid: float, battery: float, load: float, soc: float) -> None:
        now = int(time.time())
        self._conn.execute(
            "INSERT OR REPLACE INTO readings (ts, pv, grid, battery, load, soc) VALUES (?,?,?,?,?,?)",
            (now, pv, grid, battery, load, soc),
        )
        self._conn.execute("DELETE FROM readings WHERE ts < ?", (now - _RETENTION_SECONDS,))
        self._conn.commit()

    def since(self, since_ts: int) -> list[dict]:
        cur = self._conn.execute(
            "SELECT ts, pv, grid, battery, load, soc FROM readings WHERE ts >= ? ORDER BY ts",
            (since_ts,),
        )
        return [
            {"ts": ts, "pv": pv, "grid": grid, "battery": battery, "load": load, "soc": soc}
            for ts, pv, grid, battery, load, soc in cur.fetchall()
        ]
