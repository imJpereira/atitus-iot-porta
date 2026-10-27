# Employees API Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, the walk, check_proofs, the Verifier and the screens sub-agent).

**If the skill cannot be activated, STOP and tell the user - do not proceed without it.**

---

**Design**: none - small change inline (one blueprint in the existing app factory, no new patterns)
**Status**: Done (T1-T6 implemented, uncommitted)
**Approved**: 2026-10-27 - user: "aprovado, deixe as mudanças prontas para que eu comite"
**Mutations**: 3
**Build**: `uv run pytest`

---

## Test Coverage Matrix

> Generated from codebase, project guidelines, and spec - confirm before Execute. Guidelines found: `AGENTS.md` (stack and conventions only, no test rules), `pyproject.toml` (no test or lint config) - strong defaults applied. The repo has no tests yet; pytest is added in T1.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| ---------- | ------------------ | -------------------- | ---------------- | ----------- |
| Routes (`api/employees.py`) | integration (Flask test client, temp SQLite) | All routes: happy path + every listed edge case + error paths; 1:1 to spec ACs | `tests/test_employees.py` | `uv run pytest tests/test_employees.py` |
| App factory (`api/__init__.py`) | integration | `create_app(db_path)` uses the given database | `tests/test_app.py` | `uv run pytest tests/test_app.py` |
| Dependencies / config | none | - (build gate only) | - | build gate only |

## Gate Check Commands

> Generated from codebase - confirm before Execute.

| Gate Level | When to Use | Command |
| ---------- | ----------- | ------- |
| Quick | After tasks with unit tests only | `uv run pytest` |
| Full | After tasks with integration tests | `uv run pytest` |
| Build | After phase completion or config-only tasks | `uv run pytest` (no linter configured) |

---

## Execution Plan

### Phase 1: Foundation

```
T1 → T2
```

### Phase 2: Endpoints

```
T2 → T3 → T4 → T5 → T6
```

---

## Task Breakdown

### T1: Add pytest as dev dependency

**What**: Add pytest to the dev dependency group.
**Where**: `pyproject.toml`
**Depends on**: None
**Reuses**: `uv add` (never edit `uv.lock` by hand)
**Requirement**: EMP-01

**Done when**:

- [ ] `uv add --dev pytest` ran; `uv run pytest --version` works
- [ ] Gate check passes: `uv run pytest --version`

**Tests**: none
**Gate**: build

**Commit**: `chore(deps): add pytest as dev dependency`

---

### T2: Let `create_app` take a database path

**What**: `create_app(db_path=None)` stores the path in `app.config["DATABASE"]` (default `data/app.db`); `get_db` and `migrate` use it. Adds the `tests/conftest.py` `client` fixture (temp DB per test).
**Where**: `api/__init__.py`
**Depends on**: T1
**Reuses**: existing `get_db`, `migrate`
**Requirement**: EMP-01

**Done when**:

- [ ] `create_app(tmp_path / "t.db")` creates and migrates that file, not `data/app.db`
- [ ] `create_app()` still defaults to `data/app.db`
- [ ] `tests/test_app.py` proves both and `/api/health` returns 200 with `{"status": "ok"}`
- [ ] Gate check passes: `uv run pytest`
- [ ] Test count: 3 tests pass

**Tests**: integration
**Gate**: full

**Commit**: `refactor(api): create_app accepts database path`

---

### T3: `POST /api/employees` and the employees blueprint

**What**: Blueprint `employees` under `/api/employees` with `POST`, plus the shared validation (required fields, strip, booleans, unknown fields, JSON object) and serializer (booleans as JSON booleans); registered in `create_app`.
**Where**: `api/employees.py` (new; the one-line registration in `api/__init__.py` is part of it)
**Depends on**: T2
**Reuses**: `get_db`, `jsonify`, flask-python skill (blueprint, JSON errors `{"error": ...}`)
**Requirement**: EMP-01, EMP-02

**Done when**:

- [ ] Spec ACs "Cadastrar e consultar" 1 to 7 and the invalid JSON edge case have a test each in `tests/test_employees.py`
- [ ] `sqlite3.IntegrityError` becomes 409
- [ ] Gate check passes: `uv run pytest`
- [ ] Test count: 8 tests pass (plus T2's 3)

**Tests**: integration
**Gate**: full

**Commit**: `feat(api): add POST /api/employees`

---

### T4: `GET /api/employees` and `GET /api/employees/<id>`

**What**: List ordered by `id`; fetch one with 404 when missing.
**Where**: `api/employees.py` (modify)
**Depends on**: T3
**Reuses**: serializer from T3
**Requirement**: EMP-03

**Done when**:

- [ ] Spec ACs "Cadastrar e consultar" 8 to 12 have a test each
- [ ] Gate check passes: `uv run pytest`
- [ ] Test count: 5 new tests pass

**Tests**: integration
**Gate**: full

**Commit**: `feat(api): add GET /api/employees routes`

---

### T5: `PATCH /api/employees/<id>`

**What**: Partial update, reusing T3 validation; empty or null required fields give 400; sets `updated_at`.
**Where**: `api/employees.py` (modify)
**Depends on**: T4
**Reuses**: validation and serializer from T3
**Requirement**: EMP-04

**Done when**:

- [ ] Spec ACs "Editar e excluir" 1 to 5 and the empty-body edge case have a test each; the `updated_at` test first sets an old `updated_at` by SQL, since the stored resolution is one second
- [ ] Gate check passes: `uv run pytest`
- [ ] Test count: 6 new tests pass

**Tests**: integration
**Gate**: full

**Commit**: `feat(api): add PATCH /api/employees/<id>`

---

### T6: `DELETE /api/employees/<id>`

**What**: Delete returns 204 with no body, or 404 when missing.
**Where**: `api/employees.py` (modify)
**Depends on**: T5
**Reuses**: lookup helper from T4
**Requirement**: EMP-05

**Done when**:

- [ ] Spec ACs "Editar e excluir" 6 and 7 have a test each
- [ ] Gate check passes: `uv run pytest`
- [ ] Test count: 2 new tests pass

**Tests**: integration
**Gate**: full

**Commit**: `feat(api): add DELETE /api/employees/<id>`

---

## Checks

**C1** - `POST` with valid fields returns 201 and the employee with an `id` (EMP-01, AC 1)
Proof: `uv run pytest tests/test_employees.py -k test_create_returns_201_with_id`

**C2** - `POST` without flags stores `has_room_access = false` and `is_active = true` (EMP-01, AC 2)
Proof: `uv run pytest tests/test_employees.py -k test_create_defaults_flags`

**C3** - `POST` missing or blank `name`, `registration_id`, `rfid_tag` or `role` returns 400 naming the field (EMP-02, AC 3)
Proof: `uv run pytest tests/test_employees.py -k test_create_missing_field_400`

**C4** - `POST` with an existing `registration_id` returns 409 (EMP-02, AC 4)
Proof: `uv run pytest tests/test_employees.py -k test_create_duplicate_registration_409`

**C5** - A non-boolean `has_room_access` or `is_active` returns 400 naming the field (EMP-02, AC 5)
Proof: `uv run pytest tests/test_employees.py -k test_flag_not_boolean_400`

**C6** - A body that is not a JSON object returns 400 (EMP-02, AC 6)
Proof: `uv run pytest tests/test_employees.py -k test_body_not_object_400`

**C7** - An unknown field returns 400 naming it, while `id`, `created_at` and `updated_at` are ignored (EMP-02, AC 7)
Proof: `uv run pytest tests/test_employees.py -k "test_unknown_field_400 or test_reserved_fields_are_ignored"`

**C8** - Malformed JSON returns 400 with `{"error": ...}` (EMP-02, edge case)
Proof: `uv run pytest tests/test_employees.py -k test_invalid_json_400`

**C9** - `GET /api/employees` returns 200 ordered by `id` ascending (EMP-03, AC 8)
Proof: `uv run pytest tests/test_employees.py -k test_list_ordered_by_id`

**C10** - `has_room_access` and `is_active` are JSON booleans in every response (EMP-03, AC 9)
Proof: `uv run pytest tests/test_employees.py -k test_booleans_are_json_booleans`

**C11** - `GET /api/employees/<id>` returns 200 with the employee (EMP-03, AC 10)
Proof: `uv run pytest tests/test_employees.py -k test_get_existing_200`

**C12** - `GET /api/employees/<id>` with an unknown id returns 404 (EMP-03, AC 11)
Proof: `uv run pytest tests/test_employees.py -k test_get_missing_404`

**C13** - An inactive employee is returned with `is_active = false` (EMP-03, AC 12)
Proof: `uv run pytest tests/test_employees.py -k test_inactive_returned_normally`

**C14** - `PATCH` changes only the sent fields and returns 200 (EMP-04, AC 1)
Proof: `uv run pytest tests/test_employees.py -k test_patch_updates_only_sent_fields`

**C15** - `PATCH` moves `updated_at` forward (EMP-04, AC 2)
Proof: `uv run pytest tests/test_employees.py -k test_patch_updates_updated_at`

**C16** - `PATCH` with an unknown id returns 404 (EMP-04, AC 3)
Proof: `uv run pytest tests/test_employees.py -k test_patch_missing_404`

**C17** - `PATCH` with an empty or null required field returns 400 naming it (EMP-04, AC 4)
Proof: `uv run pytest tests/test_employees.py -k test_patch_empty_required_400`

**C18** - `PATCH` with another employee's `registration_id` returns 409 (EMP-04, AC 5)
Proof: `uv run pytest tests/test_employees.py -k test_patch_duplicate_registration_409`

**C19** - `PATCH` with `{}` returns 200 and the employee unchanged (EMP-04, edge case)
Proof: `uv run pytest tests/test_employees.py -k test_patch_empty_body_unchanged`

**C20** - `DELETE` returns 204 with no body and the employee is gone (EMP-05, AC 6)
Proof: `uv run pytest tests/test_employees.py -k test_delete_204`

**C21** - `DELETE` with an unknown id returns 404 (EMP-05, AC 7)
Proof: `uv run pytest tests/test_employees.py -k test_delete_missing_404`

---

## Handoff

**Settled mid-build:** user: "deixe as mudanças prontas para que eu comite" - no agent commits (AGENTS.md); T1-T6 implemented and left uncommitted. Added `[tool.pytest.ini_options] pythonpath = ["."]` to `pyproject.toml` so tests import `api`.
**Dispatched:** none (Verifier not run: proofs need a committed, clean `HEAD`)
**Walked:** none

---

## Phase Execution Map

```
Phase 1 → Phase 2

Phase 1:  T1 ------→ T2
Phase 2:  T2 ------→ T3 ------→ T4 ------→ T5 ------→ T6
```
