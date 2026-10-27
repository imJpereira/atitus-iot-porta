# employees-api verification

**Verdict**: FAIL
**Mutations**: 3 - probed strip-on-store (C3/C1), list order (C9), PATCH `updated_at` (C15)
**Proofs**: `proofs.md` at b2c9955 (22 pass, 0 fail). Its `Mutations` section is absent: `mutate.py` crashes on Windows (`signal.SIGHUP` missing), so `check_proofs.py --mutations` reported "0 killed, 0 not". The 3 mutations were applied by hand from `mutations.json` and the files restored byte for byte (verified with `git status`).
**Verifier**: independent sub-agent (author != verifier)

## Findings

| Finding | Evidence | Fix | Closed |
| --- | --- | --- | --- |
| Whitespace stripping of stored values (spec assumption "strip() antes de validar e gravar") is not proven by any test | mutation `fields[key] = value.strip()` -> `value` SURVIVED: all 51 tests pass | add a test that POSTs and PATCHes `"  Ana  "` and asserts the stored and returned value is `"Ana"` | uncommitted fix: `test_text_fields_are_stripped` (C22); add the commit sha after committing |
| AC 5 ("POST ou PATCH") is proven on POST only | `test_flag_not_boolean_400` calls only `post(...)`. The code path is shared, so an own PATCH example passed, but a PATCH-only regression would go unnoticed | parametrize the test over PATCH (`has_room_access`/`is_active` = 1, "true", None) | uncommitted fix: `test_flag_not_boolean_400_on_patch` (selected by C5's filter); add the commit sha after committing |
| AC 6 and AC 7 ("POST ou PATCH") are proven on POST only | `test_body_not_object_400` and `test_unknown_field_400` only use `client.post` | add PATCH cases (`[1]`, `{"x": 1}`) | uncommitted fix: `test_body_not_object_400_on_patch` and `test_unknown_field_400_on_patch` (selected by C6 and C7 filters); add the commit sha after committing |
| `test_list_ordered_by_id` cannot tell ORDER BY id from insertion order | ids are created in insertion order, so the `ids == sorted(ids)` assertion would also hold without `ORDER BY` (SQLite rowid order). `ORDER BY id DESC` is killed, so the direction is proven | low priority: delete the first record and re-add so rowid order differs, or accept | |
| `mutate.py` cannot run on Windows | `AttributeError: module 'signal' has no attribute 'SIGHUP'`, `mutate.py:214`. `check_proofs.py` hides it as "0 killed, 0 not" and the gate could read it as passing | guard the `SIGHUP` use with `getattr(signal, "SIGHUP", None)`. This is a skill tooling bug, not feature code | |

Not findings (own examples passed at HEAD, run from a throwaway test under the scratch dir, outside the repo):
- PATCH with the employee's own `registration_id` returns 200, not 409.
- A duplicate `rfid_tag` is accepted on POST (201).
- Stripped values are stored on POST and PATCH, and a stripped duplicate `registration_id` returns 409.
- PATCH sets both flags to booleans, and rejects `0` and `null` for them with 400.
- PATCH with a non-object body, an unknown field, or `{"id": 50}` returns 400, 400 and 200 respectively.
- Mutations killed: `ORDER BY id DESC` (C9) and `updated_at` left unchanged on PATCH (C15).
