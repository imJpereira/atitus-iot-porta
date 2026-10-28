const form = document.getElementById("employee-form");
const formError = document.getElementById("form-error");
const listError = document.getElementById("list-error");
const list = document.getElementById("employee-list");
const FIELDS = ["name", "registration_id", "role", "rfid_tag"];
let editingId = null;

// fetch wrapper: 401 -> login; returns parsed JSON (null for 204) or throws Error(api message)
async function api(url, opts = {}) {
  const res = await fetch(url, {
    ...opts,
    headers: opts.body ? { "Content-Type": "application/json" } : undefined,
  });
  if (res.status === 401) {
    location.href = "/login";
    throw new Error("Sessão expirada");
  }
  const data = res.status === 204 ? null : await res.json();
  if (!res.ok) throw new Error(data?.error || `Erro ${res.status}`);
  return data;
}

function showError(el, message) {
  el.textContent = message;
  el.hidden = !message;
}

// Highlight the field named in the API error (e.g. "registration_id already exists")
function markField(message) {
  for (const name of FIELDS) {
    const input = form.elements[name];
    const hit = message.includes(name);
    input.classList.toggle("invalid", hit);
    input.setAttribute("aria-invalid", hit);
    if (hit) input.focus();
  }
}

function cell(text, className) {
  const td = document.createElement("td");
  td.textContent = text;
  if (className) td.className = className;
  return td;
}

function button(label, onClick) {
  const b = document.createElement("button");
  b.type = "button";
  b.textContent = label;
  b.addEventListener("click", onClick);
  return b;
}

function render(employees) {
  list.replaceChildren(
    ...employees.map((e) => {
      const allowed = e.is_active && e.has_room_access;
      const tr = document.createElement("tr");
      if (!e.is_active) tr.className = "inactive";
      tr.append(
        cell(e.name),
        cell(e.registration_id),
        cell(e.role),
        cell(e.rfid_tag || "—"),
        cell(e.is_active ? "Ativo" : "Inativo", e.is_active ? "ok" : "denied"),
        cell(allowed ? "Permitido" : "Negado", allowed ? "ok" : "denied"),
      );
      const actions = document.createElement("td");
      actions.append(button("Editar", () => startEdit(e.id)), button("Excluir", () => remove(e)));
      tr.append(actions);
      return tr;
    }),
  );
  if (!employees.length) list.innerHTML = '<tr><td colspan="7">Nenhum colaborador cadastrado.</td></tr>';
}

async function load() {
  try {
    render(await api("/api/employees"));
    showError(listError, "");
  } catch (err) {
    showError(listError, err.message);
  }
}

function payload() {
  const body = {};
  for (const name of FIELDS) body[name] = form.elements[name].value.trim();
  body.rfid_tag ||= null; // optional
  body.has_room_access = form.elements.has_room_access.checked;
  body.is_active = form.elements.is_active.checked;
  return body;
}

function resetForm() {
  editingId = null;
  form.reset();
  markField("");
  showError(formError, "");
  document.getElementById("form-title").textContent = "Novo colaborador";
  document.getElementById("btn-submit").textContent = "Cadastrar";
  document.getElementById("btn-cancel").hidden = true;
}

async function startEdit(id) {
  try {
    const e = await api(`/api/employees/${id}`);
    resetForm();
    editingId = id;
    for (const name of FIELDS) form.elements[name].value = e[name] ?? "";
    form.elements.has_room_access.checked = e.has_room_access;
    form.elements.is_active.checked = e.is_active;
    document.getElementById("form-title").textContent = `Editando: ${e.name}`;
    document.getElementById("btn-submit").textContent = "Salvar";
    document.getElementById("btn-cancel").hidden = false;
    form.elements.name.focus();
  } catch (err) {
    showError(listError, err.message);
    load(); // 404: someone else deleted it
  }
}

async function remove(e) {
  if (!confirm(`Excluir ${e.name}?`)) return;
  try {
    await api(`/api/employees/${e.id}`, { method: "DELETE" });
    if (editingId === e.id) resetForm();
  } catch (err) {
    showError(listError, err.message);
  }
  load();
}

form.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  try {
    await api(editingId ? `/api/employees/${editingId}` : "/api/employees", {
      method: editingId ? "PATCH" : "POST",
      body: JSON.stringify(payload()),
    });
    resetForm(); // only clear on success; on error the typed values stay
    load();
  } catch (err) {
    showError(formError, err.message);
    markField(err.message);
  }
});

document.getElementById("btn-cancel").addEventListener("click", resetForm);

document.getElementById("btn-logout").addEventListener("click", async () => {
  await fetch("/api/auth/logout", { method: "POST" });
  location.href = "/login";
});

load();
