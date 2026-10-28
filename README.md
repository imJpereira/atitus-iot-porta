# atitus-iot-porta

Stack e convenções em [AGENTS.md](AGENTS.md).

```bash
uv sync
export PI_API_KEY=... SECRET_KEY=...   # ver .env.example
uv run flask --app api create-admin <usuario>   # pede a senha (ou use ADMIN_PASSWORD)
uv run flask --app api run --debug
```

Rotas administrativas (`/api/employees`, `GET /api/events*`, `/api/export/*`) exigem login em `POST /api/auth/login`; a Raspberry Pi usa só `X-API-Key`.

## Tag RFID

- `rfid_tag` é opcional e única. Vincule, troque ou remova com `PATCH /api/employees/<id>`; `null` desvincula.
- Ao salvar, a tag é normalizada com `strip().upper()` (`" aa:bb "` vira `"AA:BB"`). Qualquer string não vazia vale; não há regex.
- Tag já usada por outro colaborador responde 409 `{"error": "rfid_tag already exists", "owner": {"id", "name", "registration_id"}}`.
- `GET /api/sync/employees` (chave da Pi) lista só colaboradores com tag, inclusive inativos; a Pi decide por `is_active` e `has_room_access`. Tag trocada ou removida some da lista.
