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


class SungrowApiError(Exception):
    """Raised when the iSolarCloud API returns a non-success result."""


def _pad_b64(value: str) -> str:
    return value + "=" * (-len(value) % 4)


class SungrowClient:
    """Logs in fresh on every call — see README for why token caching is
    deliberately skipped."""

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

    def get_plant(self, plant_id: str | None = None) -> dict:
        token = self._login()
        result = self._post(
            "/openapi/getPowerStationList", {"curPage": 1, "size": 100}, token
        )
        plants = result.get("pageList") or []
        if not plants:
            raise SungrowApiError("No plants returned for this account")
        if plant_id:
            for plant in plants:
                if plant.get("ps_id") == plant_id:
                    return plant
            raise SungrowApiError(f"plant_id {plant_id} not found in account")
        return plants[0]

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
