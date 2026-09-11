"""Client for Sungrow's iSolarCloud OpenAPI (AppKey/SecretKey/RSA-key login flow,
not the OAuth2 variant).

Protocol reverse-engineered from the Java reference client
https://github.com/Afrouper/sungrow-api-client (EncryptionUtility.java /
BaseSungrowClient.java), since Sungrow's own docs sit behind a developer
portal login: AES/ECB/PKCS7 over the JSON body (key = the api_call_password,
utf8, padded/truncated to 16 bytes), the AES key itself RSA/PKCS1v1.5-
encrypted with the portal's RSA public key and sent as the
x-random-secret-key header; x-access-key carries the Secret Key.
"""
from __future__ import annotations

import base64
import json
import time
import uuid

import requests
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad, unpad

REGIONS = {
    "china": "https://gateway.isolarcloud.com",
    "international": "https://gateway.isolarcloud.com.hk",
    "europe": "https://gateway.isolarcloud.eu",
    "australia": "https://augateway.isolarcloud.com",
}

# Sungrow doesn't document token lifetime. 25min is a conservative guess;
# get_plant() also retries once on failure with a fresh login, so an
# early-expired token still self-heals instead of erroring out.
_TOKEN_TTL_SECONDS = 25 * 60

HYBRID_INVERTER_DEVICE_TYPE = 14

# Point IDs found via getOpenPointInfo on a Sungrow SH6.0RS hybrid inverter —
# all on the one device, so one getDeviceRealTimeData call covers PV/Grid/
# Battery/Load/SOC. Point numbering is shared across the SHx/RS product
# line, but if your inverter reports nothing for these, re-run the
# getOpenPointInfo discovery (see README) and adjust.
REALTIME_POINTS = {
    "pv_power": "13003",  # Total DC power
    "feed_in_power": "13121",  # power exported to grid
    "grid_purchase_power": "13149",  # power imported from grid
    "battery_charge_power": "13126",
    "battery_discharge_power": "13150",
    "load_power": "13119",
    "battery_soc": "13141",  # Battery level (SOC), %
}


class SungrowApiError(Exception):
    """Raised when the iSolarCloud API returns a non-success result."""


def _pad_b64(value: str) -> str:
    return value + "=" * (-len(value) % 4)


class SungrowClient:
    """Caches the login token (see _TOKEN_TTL_SECONDS) — Sungrow's free tier
    caps requests at 2000/hour and 100000/month, and login+list used to cost
    2 calls per poll for no reason."""

    def __init__(
        self,
        region: str,
        app_key: str,
        secret_key: str,
        username: str,
        password: str,
        rsa_public_key: str | None = None,
        api_call_password: str | None = None,
    ):
        self._base_url = REGIONS[region]
        self._app_key = app_key
        self._secret_key = secret_key
        self._username = username
        self._password = password
        self._aes_key = None
        self._rsa_key = None
        if rsa_public_key:
            der = base64.urlsafe_b64decode(_pad_b64(rsa_public_key))
            self._rsa_key = RSA.import_key(der)
            key_password = (api_call_password or password).encode("utf-8")
            self._aes_key = key_password[:16].ljust(16, b"0")
        self._token: str | None = None
        self._token_fetched_at = 0.0
        self._inverter_ps_key: str | None = None

    def get_realtime(self, plant_id: str | None = None) -> dict:
        """PV / grid / battery / load power (W) + battery SOC (%), read
        straight off the hybrid inverter."""
        ps_key = self._get_inverter_ps_key(plant_id)
        token = self._get_token()
        body = {
            "device_type": HYBRID_INVERTER_DEVICE_TYPE,
            "point_id_list": list(REALTIME_POINTS.values()),
            "ps_key_list": [ps_key],
        }
        try:
            result = self._post("/openapi/getDeviceRealTimeData", body, token)
        except SungrowApiError:
            self._token = None
            result = self._post("/openapi/getDeviceRealTimeData", body, self._get_token())

        entries = result.get("device_point_list") or []
        if not entries:
            raise SungrowApiError("No real-time data returned for the inverter")
        raw = entries[0].get("device_point") or entries[0]

        def point(name: str) -> float:
            value = raw.get("p" + REALTIME_POINTS[name])
            return float(value) if value is not None else 0.0

        return {
            "pv_w": point("pv_power"),
            "grid_w": point("feed_in_power") - point("grid_purchase_power"),
            "battery_w": point("battery_discharge_power") - point("battery_charge_power"),
            "load_w": point("load_power"),
            "battery_soc_pct": point("battery_soc"),
        }

    def _get_inverter_ps_key(self, plant_id: str | None) -> str:
        if self._inverter_ps_key:
            return self._inverter_ps_key
        for device in self._get_devices(plant_id):
            if device.get("device_type") == HYBRID_INVERTER_DEVICE_TYPE:
                self._inverter_ps_key = device["ps_key"]
                return self._inverter_ps_key
        raise SungrowApiError("No hybrid inverter device found in this plant")

    def get_active_faults(self, plant_id: str | None = None) -> list[dict]:
        """Per-device fault status (dev_fault_status: 1=Faulty, 2=Alarm,
        4=Normal). The plant-level alarm_count from get_plant() lags behind
        this and can miss faults that haven't been logged as a formal
        alarm ticket yet — check this instead for "is something wrong right
        now"."""
        labels = {"1": "Faulty", "2": "Alarm"}
        faults = []
        for device in self._get_devices(plant_id):
            status = labels.get(str(device.get("dev_fault_status")))
            if status:
                faults.append({"device_name": device.get("device_name"), "status": status})
        return faults

    def _get_devices(self, plant_id: str | None) -> list[dict]:
        if plant_id is None:
            plant_id = self.get_plant()["ps_id"]
        result = self._post(
            "/openapi/getDeviceList",
            {"curPage": 1, "size": 20, "ps_id": plant_id},
            self._get_token(),
        )
        return result.get("pageList") or []

    def get_plant(self, plant_id: str | None = None) -> dict:
        result = self._get_station_list()
        plants = result.get("pageList") or []
        if not plants:
            raise SungrowApiError("No plants returned for this account")
        if plant_id:
            for plant in plants:
                if plant.get("ps_id") == plant_id:
                    return plant
            raise SungrowApiError(f"plant_id {plant_id} not found in account")
        return plants[0]

    def _get_station_list(self) -> dict:
        body = {"curPage": 1, "size": 100}
        try:
            return self._post("/openapi/getPowerStationList", body, self._get_token())
        except SungrowApiError:
            # cached token may have expired earlier than our TTL guess —
            # force a fresh login and retry exactly once
            self._token = None
            return self._post("/openapi/getPowerStationList", body, self._get_token())

    def _get_token(self) -> str:
        if self._token is None or time.monotonic() - self._token_fetched_at > _TOKEN_TTL_SECONDS:
            self._token = self._login()
            self._token_fetched_at = time.monotonic()
        return self._token

    def _login(self) -> str:
        result = self._post(
            "/openapi/login",
            {"user_account": self._username, "user_password": self._password},
            token=None,
        )
        if result.get("login_state") != "1":
            raise SungrowApiError(f"Login failed, login_state={result.get('login_state')}")
        return result["token"]

    def _post(self, path: str, body: dict, token: str | None) -> dict:
        payload = dict(body)
        payload["appkey"] = self._app_key
        payload["lang"] = "_en_US"
        if token:
            payload["token"] = token

        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "x-access-key": self._secret_key,
            "sys_code": "901",
        }
        if self._aes_key:
            payload["api_key_param"] = {
                "nonce": uuid.uuid4().hex,
                "timestamp": str(int(time.time() * 1000)),
            }
            body_str = self._encrypt(json.dumps(payload))
            headers["x-random-secret-key"] = self._encrypt_aes_key()
        else:
            body_str = json.dumps(payload)

        response = requests.post(
            self._base_url + path,
            data=body_str.encode("utf-8"),
            headers=headers,
            timeout=15,
        )
        text = response.text
        if self._aes_key:
            try:
                text = self._decrypt(text)
            except (ValueError, KeyError) as err:
                raise SungrowApiError(
                    f"Could not decrypt response from {path} — check "
                    "rsa_public_key / api_call_password"
                ) from err

        data = json.loads(text)
        if data.get("result_code") != "1":
            raise SungrowApiError(
                f"{path} failed: {data.get('result_msg')} ({data.get('result_code')})"
            )
        return data.get("result_data") or {}

    def _encrypt_aes_key(self) -> str:
        cipher = PKCS1_v1_5.new(self._rsa_key)
        encrypted = cipher.encrypt(self._aes_key)
        return base64.urlsafe_b64encode(encrypted).decode("ascii").rstrip("=")

    def _encrypt(self, text: str) -> str:
        cipher = AES.new(self._aes_key, AES.MODE_ECB)
        padded = pad(text.encode("utf-8"), AES.block_size)
        return cipher.encrypt(padded).hex().upper()

    def _decrypt(self, hex_text: str) -> str:
        cipher = AES.new(self._aes_key, AES.MODE_ECB)
        raw = bytes.fromhex(hex_text)
        return unpad(cipher.decrypt(raw), AES.block_size).decode("utf-8")
