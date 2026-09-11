"""Self-check for the AES/RSA handshake in SungrowClient — a throwaway
keypair, no network, no real credentials. Verifies the encrypt/decrypt
logic round-trips exactly like it does against the real API (same padding,
same key derivation, same encodings)."""
import base64
import json

from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad, unpad

from app.sungrow_client import SungrowClient, _pad_b64


def _make_client(rsa_public_key_b64url: str) -> SungrowClient:
    return SungrowClient(
        region="europe",
        app_key="APPKEY",
        secret_key="SECRETKEY",
        username="user@example.com",
        password="hunter2",
        rsa_public_key=rsa_public_key_b64url,
        api_call_password="mySecretPortalPassword",
    )


def test_aes_key_derivation_pads_and_truncates():
    short = _make_client(_throwaway_rsa_pub())
    assert len(short._aes_key) == 16


def test_rsa_and_aes_round_trip():
    key = RSA.generate(2048)
    pub_b64url = base64.urlsafe_b64encode(
        key.publickey().export_key(format="DER")
    ).decode("ascii").rstrip("=")

    client = _make_client(pub_b64url)

    # x-random-secret-key: RSA-encrypted AES key, decryptable with the private key
    x_random_secret_key = client._encrypt_aes_key()
    recovered_aes_key = PKCS1_v1_5.new(key).decrypt(
        base64.urlsafe_b64decode(_pad_b64(x_random_secret_key)), None
    )
    assert recovered_aes_key == client._aes_key

    # request body: AES/ECB/PKCS7 hex, decryptable with the same AES key
    payload = {"appkey": "X", "user_account": "a@b.com", "user_password": "hunter2"}
    hex_body = client._encrypt(json.dumps(payload))
    decrypted = unpad(
        AES.new(client._aes_key, AES.MODE_ECB).decrypt(bytes.fromhex(hex_body)),
        AES.block_size,
    ).decode()
    assert json.loads(decrypted) == payload

    # and SungrowClient._decrypt does the same thing in reverse
    assert json.loads(client._decrypt(hex_body)) == payload


def _throwaway_rsa_pub() -> str:
    key = RSA.generate(1024)
    return base64.urlsafe_b64encode(
        key.publickey().export_key(format="DER")
    ).decode("ascii").rstrip("=")
