# employees-api proofs

**HEAD**: d26be36
**Tree**: dirty - api/__init__.py, pyproject.toml, uv.lock, api/employees.py, tests/
**Result**: 22 pass, 0 fail; mutations 0 killed, 0 not

| Check | Proof | Ran | Passed | Result |
| --- | --- | --- | --- | --- |
| C1 | `uv run pytest tests/test_employees.py -k test_create_returns_201_with_id` | 1 | 1 | pass |
| C2 | `uv run pytest tests/test_employees.py -k test_create_defaults_flags` | 1 | 1 | pass |
| C3 | `uv run pytest tests/test_employees.py -k test_create_missing_field_400` | 12 | 12 | pass |
| C4 | `uv run pytest tests/test_employees.py -k test_create_duplicate_registration_409` | 1 | 1 | pass |
| C5 | `uv run pytest tests/test_employees.py -k test_flag_not_boolean_400` | 6 | 6 | pass |
| C6 | `uv run pytest tests/test_employees.py -k test_body_not_object_400` | 3 | 3 | pass |
| C7 | `uv run pytest tests/test_employees.py -k "test_unknown_field_400 or test_reserved_fields_are_ignored"` | 2 | 2 | pass |
| C8 | `uv run pytest tests/test_employees.py -k test_invalid_json_400` | 1 | 1 | pass |
| C9 | `uv run pytest tests/test_employees.py -k test_list_ordered_by_id` | 1 | 1 | pass |
| C10 | `uv run pytest tests/test_employees.py -k test_booleans_are_json_booleans` | 1 | 1 | pass |
| C11 | `uv run pytest tests/test_employees.py -k test_get_existing_200` | 1 | 1 | pass |
| C12 | `uv run pytest tests/test_employees.py -k test_get_missing_404` | 1 | 1 | pass |
| C13 | `uv run pytest tests/test_employees.py -k test_inactive_returned_normally` | 1 | 1 | pass |
| C14 | `uv run pytest tests/test_employees.py -k test_patch_updates_only_sent_fields` | 1 | 1 | pass |
| C15 | `uv run pytest tests/test_employees.py -k test_patch_updates_updated_at` | 1 | 1 | pass |
| C16 | `uv run pytest tests/test_employees.py -k test_patch_missing_404` | 1 | 1 | pass |
| C17 | `uv run pytest tests/test_employees.py -k test_patch_empty_required_400` | 12 | 12 | pass |
| C18 | `uv run pytest tests/test_employees.py -k test_patch_duplicate_registration_409` | 1 | 1 | pass |
| C19 | `uv run pytest tests/test_employees.py -k test_patch_empty_body_unchanged` | 1 | 1 | pass |
| C20 | `uv run pytest tests/test_employees.py -k test_delete_204` | 1 | 1 | pass |
| C21 | `uv run pytest tests/test_employees.py -k test_delete_missing_404` | 1 | 1 | pass |
| Build | `uv run pytest` | - | - | pass |
