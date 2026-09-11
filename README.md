# Solar Dashboard

A small full-stack app that talks directly to Sungrow's **iSolarCloud OpenAPI**
(the AppKey/SecretKey/RSA-key flow, not the OAuth2 variant) and shows live
production stats from a home solar installation.

- **`backend/`** — FastAPI service wrapping `SungrowClient`, a from-scratch
  implementation of Sungrow's authentication protocol.
- **`frontend/`** — React + Vite + Tailwind dashboard, polls the backend every
  15s, shows current power / today's & total energy / income / CO2 avoided,
  plus a live power chart.

## Why this exists

Sungrow's OpenAPI docs sit behind a developer-portal login, and the
AppKey/SecretKey/RSA flow (as opposed to their newer OAuth2 flow) isn't
documented anywhere public. The protocol here was reverse-engineered from the
[Java reference client](https://github.com/Afrouper/sungrow-api-client) and
cross-checked against forum reports, then verified against the real API:

- Every request body is JSON, AES-encrypted (`AES/ECB/PKCS7`) with a key
  derived from a password (UTF-8 bytes, truncated/padded to 16 bytes).
- That AES key is itself RSA-encrypted (`PKCS1v1.5`) with the RSA public key
  Sungrow's developer portal issues, base64url-encoded, and sent as the
  `x-random-secret-key` header.
- The Secret Key goes in the `x-access-key` header; the AppKey goes in the
  request body.
- See `backend/app/sungrow_client.py` for the implementation and
  `backend/tests/test_sungrow_client.py` for a self-contained round-trip test
  (throwaway keypair, no network).

## Running locally

```bash
# backend
cd backend
pip install -r requirements-dev.txt
cp .env.example .env   # fill in your Sungrow credentials
uvicorn app.main:app --reload

# frontend (separate terminal)
cd frontend
bun install
bun run dev
```

## Deploying

`docker-compose.yml` builds both services. The frontend is a static build
served by nginx inside its container; a reverse proxy in front (see
`frontend/nginx.conf` for the container-internal config, and set up your own
system nginx + TLS in front of ports 4100/8081) terminates TLS and routes
`/api/*` to the backend and everything else to the frontend — same pattern as
this NAS's other projects.

## Also on this NAS

The same `SungrowClient` protocol is implemented again (independently, in
`homeassistant`-flavored Python) as a Home Assistant custom_component at
`custom_components/sungrow_isolarcloud` for long-term history/automations —
this project is the standalone, portfolio-facing version of the same idea.
