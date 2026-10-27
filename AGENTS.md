# AGENTS.md

Monolito: API e frontend no mesmo repositório.

## Stack

- Banco de dados: SQLite (módulo `sqlite3` da stdlib, arquivo em `data/app.db`)
- API: Flask (Python)
- Frontend: HTML, CSS e JavaScript vanilla (sem framework, sem build, sem npm)
- Gerenciador do projeto: [uv](https://docs.astral.sh/uv/)

## Estrutura

- `api/` — aplicação Flask (`create_app()` em `api/__init__.py`)
- `web/` — frontend estático, servido pelo Flask na raiz (`/`)
- `data/` — banco SQLite (ignorado pelo git)
- `pyproject.toml` / `uv.lock` — dependências

## Comandos

```bash
uv sync                                   # instala dependências
uv run flask --app api run --debug        # sobe API + frontend em http://127.0.0.1:5000
uv add <pacote>                           # adiciona dependência
```

## Convenções

- Rotas da API sob o prefixo `/api`.
- Dependências só via `uv add`/`uv remove`; nunca editar `uv.lock` à mão.
- Frontend sem dependências externas; usar `fetch` para falar com `/api`.
- Não adicionar ORM nem framework JS sem decisão explícita.
