# Employees API Specification

**Approved**: 2026-10-27 - user: "aprovado, implemente"

## Problem Statement

A tabela `employees` existe, mas a API não expõe cadastro de colaboradores. BAG-48 pede o CRUD sob `/api/employees` para que o sistema da porta IoT registre, consulte, edite e remova colaboradores e suas tags RFID.

## Goals

- [ ] 5 rotas (`POST`, `GET` lista, `GET` por id, `PATCH`, `DELETE`) respondem conforme os critérios abaixo.
- [ ] Nenhuma mudança de schema: o banco atual (`001_employees.sql`) é a fonte de verdade.

## Out of Scope

| Feature | Reason |
| ------- | ------ |
| Migração para tornar `rfid_tag` opcional ou `UNIQUE` | Decisão do usuário: o banco prevalece sobre a issue (AD-001) |
| Autenticação, paginação, filtros | Não pedidos na issue |
| Frontend | Issue cobre só endpoints |
| Leitura de tag RFID / abertura da porta | Outra issue |

---

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --------------------- | -------------- | --------- | ---------- |
| Issue x banco | O banco prevalece | Usuário: "sobre conflitos de Issue/banco priorize o banco" | y |
| `rfid_tag` | Obrigatório (`NOT NULL` no banco), sem 409 de duplicidade (sem `UNIQUE` no banco) | Consequência de priorizar o banco | y |
| `rfid_tag` vazio | 400 | Mesma regra de campo obrigatório vazio | y |
| Campos de texto | `strip()` antes de validar e gravar | Default aceito pelo usuário | y |
| Campos `id`, `created_at`, `updated_at` no corpo | Ignorados | Recomendação, acompanha "concordo com os defaults" | y |
| Outros campos desconhecidos | 400 indicando o campo | Recomendação, acompanha "concordo com os defaults" | y |
| Formato de erro | `{"error": "mensagem"}` | Default aceito pelo usuário | y |
| Ordem da listagem | Por `id` crescente | Default aceito pelo usuário | y |
| Corpo da requisição | Deve ser objeto JSON, senão 400 | Default aceito pelo usuário | y |
| Timestamps | UTC ISO, formato do banco | Default aceito pelo usuário | y |
| Testes | pytest (`uv add --dev pytest`) com banco temporário; `create_app()` aceita caminho do banco | Recomendação, acompanha "concordo com os defaults" | y |
| Registro de `rfid_tag` duplicado na issue | Não implementado | Conflita com o banco | y |

**Open questions:** none - all resolved or logged above (required before the spec is confirmed).

---

## User Stories

### P1: Cadastrar e consultar colaboradores ⭐ MVP

**User Story**: As an administrador, I want cadastrar e consultar colaboradores so that o sistema conheça quem tem tag RFID.

**Why P1**: Sem cadastro não há dados para o controle de acesso.

**Acceptance Criteria**:

1. WHEN `POST /api/employees` recebe `name`, `registration_id`, `rfid_tag` e `role` válidos THEN the API SHALL responder 201 com o colaborador criado, incluindo `id`  <!-- event-driven -->
2. WHEN `POST /api/employees` omite `has_room_access` e `is_active` THEN the API SHALL gravar `has_room_access = false` e `is_active = true`  <!-- event-driven -->
3. IF `POST /api/employees` não traz `name`, `registration_id`, `rfid_tag` ou `role`, ou o valor é vazio após `strip()` THEN the API SHALL responder 400 com mensagem que cita o campo  <!-- unwanted -->
4. IF `POST /api/employees` traz `registration_id` já existente THEN the API SHALL responder 409  <!-- unwanted -->
5. IF `has_room_access` ou `is_active` não é booleano em `POST` ou `PATCH` THEN the API SHALL responder 400 citando o campo  <!-- unwanted -->
6. IF o corpo da requisição de `POST` ou `PATCH` não é um objeto JSON THEN the API SHALL responder 400  <!-- unwanted -->
7. IF o corpo traz campo desconhecido (diferente de `id`, `created_at`, `updated_at`) THEN the API SHALL responder 400 citando o campo  <!-- unwanted -->
8. WHEN `GET /api/employees` é chamado THEN the API SHALL responder 200 com a lista ordenada por `id` crescente  <!-- event-driven -->
9. The API SHALL retornar `has_room_access` e `is_active` como booleanos JSON em todas as respostas com colaborador  <!-- ubiquitous -->
10. WHEN `GET /api/employees/<id>` recebe `id` existente THEN the API SHALL responder 200 com o colaborador  <!-- event-driven -->
11. IF `GET /api/employees/<id>` recebe `id` inexistente THEN the API SHALL responder 404  <!-- unwanted -->
12. WHILE um colaborador está inativo, the API SHALL retorná-lo normalmente com `is_active = false`  <!-- state-driven -->

**Independent Test**: `POST` um colaborador, depois `GET` lista e `GET` por id mostram os mesmos dados.

---

### P1: Editar e excluir colaboradores ⭐ MVP

**User Story**: As an administrador, I want editar e excluir colaboradores so that os dados reflitam a realidade.

**Why P1**: Cadastro sem manutenção fica desatualizado e uma tag perdida precisa ser descartada.

**Acceptance Criteria**:

1. WHEN `PATCH /api/employees/<id>` recebe campos válidos THEN the API SHALL atualizar só os campos enviados e responder 200 com o colaborador  <!-- event-driven -->
2. WHEN `PATCH /api/employees/<id>` atualiza um colaborador THEN the API SHALL atualizar `updated_at`  <!-- event-driven -->
3. IF `PATCH /api/employees/<id>` recebe `id` inexistente THEN the API SHALL responder 404  <!-- unwanted -->
4. IF `PATCH /api/employees/<id>` deixa `name`, `registration_id`, `rfid_tag` ou `role` vazio ou nulo THEN the API SHALL responder 400 citando o campo  <!-- unwanted -->
5. IF `PATCH /api/employees/<id>` traz `registration_id` já usado por outro colaborador THEN the API SHALL responder 409  <!-- unwanted -->
6. WHEN `DELETE /api/employees/<id>` recebe `id` existente THEN the API SHALL remover o colaborador e responder 204 sem corpo  <!-- event-driven -->
7. IF `DELETE /api/employees/<id>` recebe `id` inexistente THEN the API SHALL responder 404  <!-- unwanted -->

**Independent Test**: `PATCH` muda `role` e `updated_at`; `DELETE` e então `GET` por id retorna 404.

---

## Edge Cases

- IF o corpo de `POST` ou `PATCH` não é JSON válido THEN the API SHALL responder 400 com `{"error": ...}`
- WHEN `PATCH` recebe corpo `{}` THEN the API SHALL responder 200 com o colaborador inalterado

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| -------------- | ----- | ----- | ------ |
| EMP-01 | P1: Cadastrar e consultar (criar, defaults, 201) | Design | Pending |
| EMP-02 | P1: Cadastrar e consultar (validações 400 e 409) | Design | Pending |
| EMP-03 | P1: Cadastrar e consultar (listar, buscar, booleanos, 404) | Design | Pending |
| EMP-04 | P1: Editar e excluir (PATCH) | Design | Pending |
| EMP-05 | P1: Editar e excluir (DELETE) | Design | Pending |

**Coverage:** 5 total, 0 mapped to tasks, 5 unmapped ⚠️

---

## Sources

- https://linear.app/bagual/issue/BAG-48/endpoints-para-cadastro - rotas, códigos de status e regras gerais
- `api/migrations/001_employees.sql` - schema vigente, prevalece sobre a issue em conflitos

---

## Success Criteria

- [ ] Todos os critérios acima passam em testes pytest com banco temporário.
- [ ] `uv run flask --app api run` sobe e as 5 rotas respondem.
