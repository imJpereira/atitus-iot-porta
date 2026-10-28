# atitus-iot-porta

Stack e convenções em [AGENTS.md](AGENTS.md).

```bash
uv sync
export PI_API_KEY=... SECRET_KEY=...   # ver .env.example
uv run flask --app api create-admin <usuario>   # pede a senha (ou use ADMIN_PASSWORD)
uv run flask --app api run --debug
```

Rotas administrativas (`/api/employees`, `GET /api/events*`, `/api/export/*`) exigem login em `POST /api/auth/login`; a Raspberry Pi usa só `X-API-Key`.
