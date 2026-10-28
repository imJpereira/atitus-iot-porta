const EVENT_LABEL = {
  entrada: "Entrada autorizada",
  saida: "Saída registrada",
  acesso_negado: "Acesso negado",
  tentativa_invasao: "Tentativa de invasão",
};

const state = {
  currentView: "dashboard",
  employees: [],
  editingEmployeeId: null,
  logs: { offset: 0, limit: 20, total: 0, rows: [] },
  isRefreshing: { dashboard: false, monitoring: false, logs: false, reports: false, devices: false },
  pollTimer: null,
  clockTimer: null,
  reportsCache: [],
  notificationsCount: 0,
};

const employeeForm = document.getElementById("employee-form");
const employeeFields = ["name", "registration_id", "role", "rfid_tag"];
const pageMeta = {
  dashboard: { title: "Início", subtitle: "Visão geral operacional do ARGOS." },
  monitoring: { title: "Monitoramento", subtitle: "Acompanhe eventos em tempo real da sala de segurança." },
  employees: { title: "Colaboradores", subtitle: "Cadastre e gerencie acessos administrativos." },
  logs: { title: "Logs de acesso", subtitle: "Consulte o histórico de eventos RFID." },
  reports: { title: "Relatórios", subtitle: "Análises de movimentação e permanência." },
  devices: { title: "Dispositivos", subtitle: "Status de integração disponível para frontend." },
};

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function getSessionUsername() {
  const fromStorage = sessionStorage.getItem("argosAdminUsername");
  if (fromStorage) return fromStorage;
  const fallback = document.getElementById("session-user")?.textContent?.trim();
  return fallback || "admin";
}

function setupSessionCard() {
  const trigger = document.getElementById("btn-session-card");
  const popover = document.getElementById("session-popover");
  if (!trigger || !popover) return;

  const username = getSessionUsername();
  setText("session-user", username);

  const key = `argos_admin_access_meta_${username.toLowerCase()}`;
  const now = new Date().toISOString();
  const persisted = JSON.parse(localStorage.getItem(key) || "{}");
  const firstAccess = persisted.firstAccess || now;
  const lastAccess = persisted.lastAccess || null;
  const totalAccess = Number(persisted.totalAccess || 0) + 1;
  localStorage.setItem(
    key,
    JSON.stringify({
      firstAccess,
      lastAccess: now,
      totalAccess,
    }),
  );

  setText("session-first-access", formatDateTime(firstAccess));
  setText("session-last-access", lastAccess ? formatDateTime(lastAccess) : "Primeiro acesso");
  setText("session-current-access", formatDateTime(now));
  setText("session-total-access", String(totalAccess));

  const close = () => {
    popover.hidden = true;
    trigger.setAttribute("aria-expanded", "false");
  };

  trigger.addEventListener("click", (event) => {
    event.stopPropagation();
    const isOpening = popover.hidden;
    popover.hidden = !isOpening;
    trigger.setAttribute("aria-expanded", isOpening ? "true" : "false");
  });

  document.addEventListener("click", (event) => {
    if (popover.hidden) return;
    if (trigger.contains(event.target) || popover.contains(event.target)) return;
    close();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") close();
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showMessage(id, message) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = message;
  el.hidden = !message;
}

function setStatusBadge(id, text, kind) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.className = `status-badge ${kind}`;
}

function setGlobalStatus(text, kind) {
  setStatusBadge("global-status", text, kind);
}

function updateTopbarClock() {
  const now = new Date();
  const dateLabel = now.toLocaleDateString("pt-BR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
  const timeLabel = now.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", hour12: false });
  setText("topbar-date", dateLabel.replace(/\./g, ""));
  setText("topbar-time", timeLabel);
}

function startTopbarClock() {
  updateTopbarClock();
  if (state.clockTimer) clearInterval(state.clockTimer);
  state.clockTimer = setInterval(updateTopbarClock, 1000);
}

function setNotificationsCount(count) {
  state.notificationsCount = Math.max(0, Number(count || 0));
  const dot = document.getElementById("notification-dot");
  const button = document.getElementById("btn-notifications");
  if (!dot || !button) return;
  const labelCount = state.notificationsCount > 99 ? "99+" : String(state.notificationsCount);
  dot.textContent = labelCount;
  dot.hidden = state.notificationsCount === 0;
  const suffix = state.notificationsCount ? ` (${state.notificationsCount})` : "";
  button.setAttribute("aria-label", `Abrir alertas${suffix}`);
}

function formatDateTime(isoDate) {
  if (!isoDate) return "—";
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) return isoDate;
  return date.toLocaleString("pt-BR", { hour12: false });
}

function formatDuration(totalSeconds) {
  if (typeof totalSeconds !== "number") return "Indisponível";
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  return `${hours}h ${String(minutes).padStart(2, "0")}min`;
}

function formatElapsedFrom(isoDate) {
  if (!isoDate) return "Indisponível";
  const started = new Date(isoDate).getTime();
  if (Number.isNaN(started)) return "Indisponível";
  const seconds = Math.max(0, Math.floor((Date.now() - started) / 1000));
  return formatDuration(seconds);
}

function toIsoLocalInput(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toISOString().slice(0, 16);
}

function toIsoWithTimezone(localDateTime) {
  if (!localDateTime) return "";
  const date = new Date(localDateTime);
  return Number.isNaN(date.getTime()) ? "" : date.toISOString();
}

function eventBadge(type) {
  const label = EVENT_LABEL[type] || type;
  const cssType = ["entrada", "saida", "acesso_negado", "tentativa_invasao"].includes(type) ? type : "acesso_negado";
  return `<span class="event-badge event-${cssType}">${escapeHtml(label)}</span>`;
}

function eventResult(type) {
  if (type === "entrada" || type === "saida") return '<span class="result-ok">Sucesso</span>';
  if (type === "acesso_negado") return '<span class="result-warn">Negado</span>';
  return '<span class="result-danger">Incidente</span>';
}

function monitoringType(type) {
  const map = {
    entrada: { label: "Entrada", icon: "↑" },
    saida: { label: "Saída", icon: "↓" },
    acesso_negado: { label: "Negado", icon: "✕" },
    tentativa_invasao: { label: "Invasão", icon: "⚠" },
  };
  const current = map[type] || { label: type, icon: "•" };
  return `<span class="monitor-type monitor-type-${escapeHtml(type)}"><span class="monitor-type-icon">${escapeHtml(current.icon)}</span>${escapeHtml(current.label)}</span>`;
}

function monitoringStatus(type) {
  if (type === "entrada") return '<span class="monitor-status monitor-status-ok">Autorizado</span>';
  if (type === "saida") return '<span class="monitor-status monitor-status-regular">Registrado</span>';
  if (type === "acesso_negado") return '<span class="monitor-status monitor-status-warn">Negado</span>';
  return '<span class="monitor-status monitor-status-danger">Bloqueado</span>';
}

function monitoringDetails(event) {
  if (event.type === "entrada") return "Acesso à sala";
  if (event.type === "saida") return "Saída da sala";
  if (event.type === "acesso_negado") return "Sem permissão";
  return `Tentativa de invasão${event.rfid_tag ? ` (${event.rfid_tag})` : ""}`;
}

async function api(url, opts = {}) {
  const request = {
    ...opts,
    headers: { ...(opts.headers || {}) },
  };
  if (opts.body && !request.headers["Content-Type"]) {
    request.headers["Content-Type"] = "application/json";
  }
  const response = await fetch(url, request);
  if (response.status === 401) {
    location.href = "/login";
    throw new Error("Sessão expirada.");
  }
  let data = null;
  if (response.status !== 204) {
    try {
      data = await response.json();
    } catch (_ignore) {
      data = null;
    }
  }
  if (!response.ok) {
    throw new Error(data?.error || `Erro ${response.status}`);
  }
  return { data, headers: response.headers, status: response.status };
}

function employeeById(employeeId) {
  return state.employees.find((employee) => employee.id === employeeId) || null;
}

function eventActor(event) {
  const employee = employeeById(event.employee_id);
  if (event.employee_name || employee) {
    const name = event.employee_name || employee?.name || "Colaborador";
    const registration = employee?.registration_id ? ` (${employee.registration_id})` : "";
    return `${name}${registration}`;
  }
  return `TAG ${event.rfid_tag}`;
}

function buildEventsQuery(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === "" || value === null || value === undefined) return;
    query.set(key, String(value));
  });
  const suffix = query.toString();
  return suffix ? `?${suffix}` : "";
}

async function fetchEvents(params = {}) {
  const { data, headers } = await api(`/api/events${buildEventsQuery(params)}`);
  return { rows: Array.isArray(data) ? data : [], total: Number(headers.get("X-Total-Count") || 0) };
}

async function fetchInside() {
  const { data } = await api("/api/events/inside");
  return Array.isArray(data) ? data : [];
}

function countsByType(events) {
  const counts = { entrada: 0, saida: 0, acesso_negado: 0, tentativa_invasao: 0 };
  events.forEach((event) => {
    if (counts[event.type] !== undefined) counts[event.type] += 1;
  });
  return counts;
}

function recentAlerts(events) {
  return events
    .filter((event) => event.type === "tentativa_invasao" || event.type === "acesso_negado")
    .slice(0, 8);
}

function renderRecentEvents(targetId, events) {
  const tbody = document.getElementById(targetId);
  if (!tbody) return;
  tbody.innerHTML = events
    .map(
      (event) => `
      <tr>
        <td>${formatDateTime(event.timestamp)}</td>
        <td>${eventBadge(event.type)}</td>
        <td>${escapeHtml(eventActor(event))}</td>
        <td>${eventResult(event.type)}</td>
      </tr>
    `,
    )
    .join("");
}

function renderAlerts(targetId, emptyId, alerts) {
  const list = document.getElementById(targetId);
  if (!list) return;
  const grouped = new Map();
  alerts.forEach((event) => {
    const key = `${event.type}:${event.employee_id || ""}:${event.rfid_tag || ""}`;
    const current = grouped.get(key);
    if (!current) {
      grouped.set(key, { event, count: 1 });
      return;
    }
    current.count += 1;
  });
  list.innerHTML = [...grouped.values()]
    .map(({ event, count }) => {
      const level = event.type === "tentativa_invasao" ? "alert-high" : "alert-medium";
      const repeated = count > 1 ? ` x${count}` : "";
      return `<li class="${level}">${escapeHtml(EVENT_LABEL[event.type])} - ${escapeHtml(eventActor(event))}${repeated} (${escapeHtml(formatDateTime(event.timestamp))})</li>`;
    })
    .join("");
  document.getElementById(emptyId).hidden = alerts.length > 0;
}

function renderDashboardTimeline(events) {
  const target = document.getElementById("dashboard-timeline");
  const empty = document.getElementById("dashboard-timeline-empty");
  if (!target || !empty) return;

  const perHour = new Map();
  events.forEach((event) => {
    if (event.type !== "entrada" && event.type !== "saida") return;
    const date = new Date(event.timestamp);
    if (Number.isNaN(date.getTime())) return;
    const hour = String(date.getHours()).padStart(2, "0");
    if (!perHour.has(hour)) perHour.set(hour, { entrada: 0, saida: 0 });
    perHour.get(hour)[event.type] += 1;
  });

  const hours = [...perHour.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  if (!hours.length) {
    target.innerHTML = "";
    empty.hidden = false;
    return;
  }

  empty.hidden = true;
  const peak = Math.max(...hours.map(([, values]) => values.entrada + values.saida), 1);
  target.innerHTML = hours
    .map(([hour, values]) => {
      const inHeight = values.entrada ? Math.max(8, Math.round((values.entrada / peak) * 100)) : 0;
      const outHeight = values.saida ? Math.max(8, Math.round((values.saida / peak) * 100)) : 0;
      return `
      <div class="timeline-col" title="${hour}h: ${values.entrada} entrada(s), ${values.saida} saída(s)">
        <div class="timeline-bars">
          <div class="timeline-bar timeline-bar-entry" style="height:${inHeight}%"></div>
          <div class="timeline-bar timeline-bar-exit" style="height:${outHeight}%"></div>
        </div>
        <small>${hour}h</small>
      </div>
    `;
    })
    .join("");
}

function renderDashboardRoomStatus(events, insideRows, counts) {
  const status = document.getElementById("dashboard-room-status");
  const details = document.getElementById("dashboard-room-details");
  const lastEvent = document.getElementById("dashboard-room-last-event");
  if (!status || !details || !lastEvent) return;

  const latest = events[0];
  lastEvent.textContent = `Último evento: ${latest ? formatDateTime(latest.timestamp) : "—"}`;

  if (counts.tentativa_invasao > 0) {
    status.className = "status-badge status-error";
    status.textContent = "Incidente crítico";
    details.textContent = `${counts.tentativa_invasao} tentativa(s) de invasão no período.`;
    return;
  }
  if (counts.acesso_negado > 0) {
    status.className = "status-badge status-warning";
    status.textContent = "Atenção";
    details.textContent = `${counts.acesso_negado} acesso(s) negado(s) no período.`;
    return;
  }
  status.className = "status-badge status-success";
  status.textContent = "Operação normal";
  details.textContent = `${insideRows.length} pessoa(s) na sala e sem incidentes críticos recentes.`;
}

async function refreshDashboard() {
  if (state.isRefreshing.dashboard) return;
  state.isRefreshing.dashboard = true;
  setStatusBadge("global-status", "Atualizando dashboard...", "status-neutral");
  try {
    const from = new Date(Date.now() - 24 * 3600 * 1000).toISOString();
    const [eventsResponse, insideRows] = await Promise.all([
      fetchEvents({ from, limit: 1000 }),
      fetchInside(),
    ]);
    const counts = countsByType(eventsResponse.rows);
    setText("metric-inside", String(insideRows.length));
    setText("metric-entries", String(counts.entrada));
    setText("metric-exits", String(counts.saida));
    setText("metric-denied", String(counts.acesso_negado));
    setText("metric-intrusion", String(counts.tentativa_invasao));

    const recent = eventsResponse.rows.slice(0, 8);
    renderDashboardTimeline(eventsResponse.rows);
    renderDashboardRoomStatus(eventsResponse.rows, insideRows, counts);
    renderRecentEvents("dashboard-events-body", recent);
    document.getElementById("dashboard-events-empty").hidden = recent.length > 0;
    const alerts = recentAlerts(eventsResponse.rows);
    renderAlerts("dashboard-alerts", "dashboard-alerts-empty", alerts);
    setNotificationsCount(alerts.length);
    setGlobalStatus("Dashboard atualizado", "status-success");
  } catch (error) {
    setGlobalStatus(`Falha no dashboard: ${error.message}`, "status-error");
  } finally {
    state.isRefreshing.dashboard = false;
  }
}

function renderMonitoring(events, insideRows) {
  const body = document.getElementById("monitoring-events-body");
  body.innerHTML = events
    .map(
      (event) => `
      <tr>
        <td>${formatDateTime(event.timestamp)}</td>
        <td>${monitoringType(event.type)}</td>
        <td>${escapeHtml(eventActor(event))}</td>
        <td>${monitoringStatus(event.type)}</td>
        <td>${escapeHtml(monitoringDetails(event))}</td>
      </tr>
    `,
    )
    .join("");
  document.getElementById("monitoring-empty").hidden = events.length > 0;
  setText("monitoring-inside-count", String(insideRows.length));
  setText("monitoring-inside-pill", String(insideRows.length));

  const latestEntryByEmployee = new Map();
  [...events]
    .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp))
    .forEach((event) => {
      if (!event.employee_id) return;
      if (event.type === "entrada") latestEntryByEmployee.set(event.employee_id, event.timestamp);
      if (event.type === "saida") latestEntryByEmployee.delete(event.employee_id);
    });

  const insideList = document.getElementById("inside-list");
  insideList.innerHTML = insideRows
    .map((employee) => {
      const entryTime = latestEntryByEmployee.get(employee.id);
      const enteredAt = entryTime ? formatDateTime(entryTime) : "Indisponível";
      const elapsed = entryTime ? formatElapsedFrom(entryTime) : "Indisponível";
      return `<li>${escapeHtml(employee.name)} (${escapeHtml(employee.registration_id)}) — Entrada: ${escapeHtml(enteredAt)} — Tempo: ${escapeHtml(elapsed)}</li>`;
    })
    .join("");
  document.getElementById("inside-empty").hidden = insideRows.length > 0;
  const alerts = recentAlerts(events);
  renderAlerts("monitoring-alerts", "monitoring-alerts-empty", alerts);
  setText("monitoring-alerts-pill", String(alerts.length));
  setNotificationsCount(alerts.length);
}

async function refreshMonitoring() {
  if (state.isRefreshing.monitoring) return;
  state.isRefreshing.monitoring = true;
  setStatusBadge("monitoring-status", "Atualizando...", "status-neutral");
  showMessage("monitoring-error", "");
  try {
    const [eventsResponse, insideRows] = await Promise.all([fetchEvents({ limit: 1000 }), fetchInside()]);
    renderMonitoring(eventsResponse.rows, insideRows);
    setStatusBadge("monitoring-status", `Atualizado às ${new Date().toLocaleTimeString("pt-BR")}`, "status-success");
  } catch (error) {
    setStatusBadge("monitoring-status", "Dados desatualizados", "status-warning");
    showMessage("monitoring-error", `Não foi possível atualizar monitoramento: ${error.message}`);
  } finally {
    state.isRefreshing.monitoring = false;
  }
}

function markEmployeeFormField(message) {
  employeeFields.forEach((name) => {
    const input = employeeForm.elements[name];
    const hit = message && message.includes(name);
    input.classList.toggle("invalid", hit);
    input.setAttribute("aria-invalid", hit);
    if (hit) input.focus();
  });
}

function employeePayload() {
  const payload = {};
  employeeFields.forEach((field) => {
    payload[field] = employeeForm.elements[field].value.trim();
  });
  payload.rfid_tag = payload.rfid_tag ? payload.rfid_tag.toUpperCase() : null;
  payload.has_room_access = employeeForm.elements.has_room_access.checked;
  payload.is_active = employeeForm.elements.is_active.checked;
  return payload;
}

function resetEmployeeForm() {
  state.editingEmployeeId = null;
  employeeForm.reset();
  employeeForm.elements.is_active.checked = true;
  showMessage("employee-form-feedback", "");
  markEmployeeFormField("");
  setText("employee-form-title", "Novo colaborador");
  setText("btn-employee-submit", "Cadastrar");
  document.getElementById("btn-employee-cancel").hidden = true;
}

function employeeAllowed(employee) {
  return Boolean(employee.is_active && employee.has_room_access);
}

function filteredEmployees() {
  const search = document.getElementById("employee-search").value.trim().toLowerCase();
  const activeFilter = document.getElementById("filter-active").value;
  const accessFilter = document.getElementById("filter-access").value;
  return state.employees.filter((employee) => {
    const haystack = `${employee.name} ${employee.registration_id} ${employee.rfid_tag || ""}`.toLowerCase();
    if (search && !haystack.includes(search)) return false;
    if (activeFilter === "active" && !employee.is_active) return false;
    if (activeFilter === "inactive" && employee.is_active) return false;
    if (activeFilter === "denied" && employeeAllowed(employee)) return false;
    if (accessFilter === "allowed" && !employeeAllowed(employee)) return false;
    if (accessFilter === "denied" && employeeAllowed(employee)) return false;
    return true;
  });
}

function renderEmployeeRows() {
  const rows = filteredEmployees();
  const tbody = document.getElementById("employees-body");
  tbody.innerHTML = rows
    .map(
      (employee) => `
      <tr>
        <td>${escapeHtml(employee.name)}</td>
        <td>${escapeHtml(employee.registration_id)}</td>
        <td>${escapeHtml(employee.role)}</td>
        <td>${escapeHtml(employee.rfid_tag || "Sem credencial")}</td>
        <td><span class="${employee.is_active ? "result-ok" : "result-danger"}">${employee.is_active ? "Ativo" : "Inativo"}</span></td>
        <td><span class="${employeeAllowed(employee) ? "result-ok" : "result-warn"}">${employeeAllowed(employee) ? "Permitido" : "Negado"}</span></td>
        <td>
          <button class="btn btn-ghost" type="button" data-action="edit" data-id="${employee.id}">Editar</button>
          <button class="btn btn-ghost" type="button" data-action="delete" data-id="${employee.id}">Excluir</button>
        </td>
      </tr>
    `,
    )
    .join("");
  document.getElementById("employees-empty").hidden = rows.length > 0;
}

function populateEmployeeSelects() {
  const select = document.getElementById("logs-employee");
  const current = select.value;
  select.innerHTML = '<option value="">Todos</option>';
  state.employees.forEach((employee) => {
    const option = document.createElement("option");
    option.value = String(employee.id);
    option.textContent = `${employee.name} (${employee.registration_id})`;
    select.append(option);
  });
  select.value = current;
}

async function loadEmployees() {
  try {
    const { data } = await api("/api/employees");
    state.employees = Array.isArray(data) ? data : [];
    showMessage("employees-feedback", "");
    renderEmployeeRows();
    populateEmployeeSelects();
  } catch (error) {
    showMessage("employees-feedback", error.message);
  }
}

async function editEmployee(employeeId) {
  try {
    const { data } = await api(`/api/employees/${employeeId}`);
    resetEmployeeForm();
    state.editingEmployeeId = employeeId;
    employeeFields.forEach((field) => {
      employeeForm.elements[field].value = data[field] ?? "";
    });
    employeeForm.elements.has_room_access.checked = Boolean(data.has_room_access);
    employeeForm.elements.is_active.checked = Boolean(data.is_active);
    setText("employee-form-title", `Editando: ${data.name}`);
    setText("btn-employee-submit", "Salvar");
    document.getElementById("btn-employee-cancel").hidden = false;
    employeeForm.elements.name.focus();
  } catch (error) {
    showMessage("employees-feedback", error.message);
  }
}

async function deleteEmployee(employeeId) {
  const employee = state.employees.find((item) => item.id === employeeId);
  if (!employee) return;
  if (!confirm(`Excluir ${employee.name}?`)) return;
  try {
    await api(`/api/employees/${employeeId}`, { method: "DELETE" });
    if (state.editingEmployeeId === employeeId) resetEmployeeForm();
    await loadEmployees();
  } catch (error) {
    showMessage("employees-feedback", error.message);
  }
}

function logsFiltersParams() {
  return {
    from: toIsoWithTimezone(document.getElementById("logs-from").value),
    to: toIsoWithTimezone(document.getElementById("logs-to").value),
    type: document.getElementById("logs-type").value,
    employee_id: document.getElementById("logs-employee").value,
  };
}

function currentSearchedLogsRows() {
  const search = document.getElementById("logs-search").value.trim().toLowerCase();
  return state.logs.rows.filter((event) => {
    if (!search) return true;
    const employee = employeeById(event.employee_id);
    const source = `${event.source || ""} ${event.rfid_tag || ""} ${event.employee_name || ""} ${employee?.registration_id || ""}`.toLowerCase();
    return source.includes(search);
  });
}

function renderLogs() {
  const rows = currentSearchedLogsRows();
  state.logs.total = rows.length;
  const pages = Math.max(1, Math.ceil(state.logs.total / state.logs.limit));
  const maxOffset = Math.max(0, (pages - 1) * state.logs.limit);
  if (state.logs.offset > maxOffset) state.logs.offset = maxOffset;
  const pageRows = rows.slice(state.logs.offset, state.logs.offset + state.logs.limit);
  const body = document.getElementById("logs-body");
  body.innerHTML = pageRows
    .map(
      (event) => `
      <tr>
        <td>${formatDateTime(event.timestamp)}</td>
        <td>${eventBadge(event.type)}</td>
        <td>${escapeHtml(eventActor(event))} / TAG ${escapeHtml(event.rfid_tag || "—")}</td>
        <td>${eventResult(event.type)}</td>
        <td>${escapeHtml(event.source || "—")}</td>
      </tr>
    `,
    )
    .join("");
  document.getElementById("logs-empty").hidden = pageRows.length > 0;

  const page = Math.floor(state.logs.offset / state.logs.limit) + 1;
  setText("logs-page-info", `Página ${page} de ${pages}`);
  document.getElementById("logs-prev").disabled = state.logs.offset === 0;
  document.getElementById("logs-next").disabled = state.logs.offset + state.logs.limit >= state.logs.total;
}

async function loadLogs() {
  if (state.isRefreshing.logs) return;
  state.isRefreshing.logs = true;
  showMessage("logs-feedback", "");
  try {
    const params = { ...logsFiltersParams(), limit: 1000, offset: 0 };
    const response = await fetchEvents(params);
    state.logs.rows = response.rows;
    renderLogs();
  } catch (error) {
    showMessage("logs-feedback", error.message);
  } finally {
    state.isRefreshing.logs = false;
  }
}

function reportFiltersParams() {
  return {
    from: toIsoWithTimezone(document.getElementById("reports-from").value),
    to: toIsoWithTimezone(document.getElementById("reports-to").value),
    limit: 1000,
    offset: 0,
  };
}

function renderReportChart(events) {
  const chart = document.getElementById("report-chart");
  const grouping = document.getElementById("report-grouping")?.value || "hour";
  const perHour = new Map();
  events.forEach((event) => {
    if (event.type !== "entrada" && event.type !== "saida") return;
    const date = new Date(event.timestamp);
    if (Number.isNaN(date.getTime())) return;
    const hour = String(date.getHours()).padStart(2, "0");
    const half = date.getMinutes() < 30 ? "00" : "30";
    const bucket = grouping === "30min" ? `${hour}:${half}` : hour;
    if (!perHour.has(bucket)) perHour.set(bucket, { entrada: 0, saida: 0 });
    perHour.get(bucket)[event.type] += 1;
  });
  const entries = [...perHour.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  if (!entries.length) {
    chart.innerHTML = "";
    document.getElementById("report-chart-empty").hidden = false;
    return;
  }
  document.getElementById("report-chart-empty").hidden = true;
  const peak = Math.max(...entries.map(([, values]) => Math.max(values.entrada, values.saida)), 1);
  chart.innerHTML = entries
    .map(([bucket, values], index) => `
      ${index === 0
    ? `
      <div class="report-chart-legend">
        <span><i class="legend-dot legend-entry"></i> Entradas</span>
        <span><i class="legend-dot legend-exit"></i> Saídas</span>
      </div>
      `
    : ""}
      <div class="report-hour-row">
        <div class="report-hour-label">${grouping === "30min" ? bucket : `${bucket}h`}</div>
        <div class="report-hour-metrics">
          <div class="report-metric-row">
            <span class="report-metric-name">Entradas</span>
            <div class="report-bar-track">
              <div class="report-bar report-bar-entry" style="width: ${values.entrada ? Math.round((values.entrada / peak) * 100) : 0}%;"></div>
            </div>
            <span class="report-metric-value">${values.entrada}</span>
          </div>
          <div class="report-metric-row">
            <span class="report-metric-name">Saídas</span>
            <div class="report-bar-track">
              <div class="report-bar report-bar-exit" style="width: ${values.saida ? Math.round((values.saida / peak) * 100) : 0}%;"></div>
            </div>
            <span class="report-metric-value">${values.saida}</span>
          </div>
        </div>
      </div>
    `)
    .join("");
}

function renderReportRanking(events) {
  const ranking = new Map();
  events.forEach((event) => {
    if (event.type !== "acesso_negado" && event.type !== "tentativa_invasao") return;
    const employee = employeeById(event.employee_id);
    const key = employee
      ? `emp:${employee.id}:${employee.name}`
      : `tag:${event.rfid_tag || "desconhecida"}:TAG ${event.rfid_tag || "desconhecida"}`;
    ranking.set(key, (ranking.get(key) || 0) + 1);
  });
  const rows = [...ranking.entries()]
    .map(([key, count]) => ({ key, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 8);
  const target = document.getElementById("report-ranking");
  target.innerHTML = rows
    .map(({ key, count }) => {
      const [, , name] = key.split(":");
      return `<li>${escapeHtml(name)} - ${count} tentativa(s)</li>`;
    })
    .join("");
  document.getElementById("report-ranking-empty").hidden = rows.length > 0;
}

function renderReportStay(stayResponse) {
  const rows = stayResponse?.employees || [];
  const body = document.getElementById("report-stay-body");
  body.innerHTML = rows
    .map((employee) => {
      const sessions = (employee.sessions || [])
        .map((session) => {
          if (session.sem_saida) return `${escapeHtml(formatDateTime(session.entrada))} -> sem saída`;
          return `${escapeHtml(formatDateTime(session.entrada))} -> ${escapeHtml(formatDateTime(session.saida))}`;
        })
        .join("<br>");
      return `
      <tr>
        <td>${escapeHtml(employee.name)}</td>
        <td>${formatDuration(employee.total_seconds)}</td>
        <td>${sessions || "Sem sessões no período"}</td>
      </tr>
    `;
    })
    .join("");
  document.getElementById("report-stay-empty").hidden = rows.length > 0;
}

async function loadReports() {
  if (state.isRefreshing.reports) return;
  state.isRefreshing.reports = true;
  showMessage("reports-feedback", "");
  try {
    const reportParams = reportFiltersParams();
    const reportsDate = document.getElementById("reports-date").value;
    const [eventsResponse, stayResponse] = await Promise.all([
      fetchEvents(reportParams),
      api(`/api/stay?date=${encodeURIComponent(reportsDate)}`).then((response) => response.data),
    ]);
    state.reportsCache = eventsResponse.rows;
    const counts = countsByType(eventsResponse.rows);
    setText("report-entries", String(counts.entrada));
    setText("report-exits", String(counts.saida));
    setText("report-denied", String(counts.acesso_negado));
    setText("report-intrusion", String(counts.tentativa_invasao));
    renderReportChart(eventsResponse.rows);
    renderReportRanking(eventsResponse.rows);
    renderReportStay(stayResponse);
  } catch (error) {
    showMessage("reports-feedback", error.message);
  } finally {
    state.isRefreshing.reports = false;
  }
}

async function refreshDevices() {
  if (state.isRefreshing.devices) return;
  state.isRefreshing.devices = true;
  try {
    const { data } = await api("/api/health");
    setStatusBadge("device-backend-status", data?.status === "ok" ? "Online" : "Indefinido", "status-success");
    setText("device-backend-details", `Última verificação: ${new Date().toLocaleString("pt-BR")}`);
  } catch (error) {
    setStatusBadge("device-backend-status", "Indisponível", "status-error");
    setText("device-backend-details", `Falha: ${error.message}`);
  } finally {
    state.isRefreshing.devices = false;
  }
}

function switchView(view) {
  state.currentView = view;
  document.querySelectorAll(".menu-item").forEach((item) => {
    item.classList.toggle("is-active", item.dataset.view === view);
  });
  document.querySelectorAll(".view").forEach((section) => {
    section.classList.toggle("is-active", section.dataset.view === view);
  });
  setText("page-title", pageMeta[view].title);
  setText("page-subtitle", pageMeta[view].subtitle);
  document.getElementById("sidebar").classList.remove("is-open");
  if (view === "dashboard") refreshDashboard();
  if (view === "monitoring") refreshMonitoring();
  if (view === "employees") loadEmployees();
  if (view === "logs") loadLogs();
  if (view === "reports") loadReports();
  if (view === "devices") refreshDevices();
}

function setupMenu() {
  document.querySelectorAll(".menu-item").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.view));
  });
  document.getElementById("btn-menu").addEventListener("click", () => {
    document.getElementById("sidebar").classList.toggle("is-open");
  });
}

function setupEmployees() {
  employeeForm.elements.rfid_tag.addEventListener("input", (event) => {
    event.target.value = event.target.value.toUpperCase();
  });

  employeeForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    markEmployeeFormField("");
    showMessage("employee-form-feedback", "");
    const submitButton = document.getElementById("btn-employee-submit");
    let payload = null;
    submitButton.disabled = true;
    submitButton.textContent = state.editingEmployeeId ? "Salvando..." : "Cadastrando...";
    try {
      payload = employeePayload();
      await api(state.editingEmployeeId ? `/api/employees/${state.editingEmployeeId}` : "/api/employees", {
        method: state.editingEmployeeId ? "PATCH" : "POST",
        body: JSON.stringify(payload),
      });
      resetEmployeeForm();
      await loadEmployees();
      showMessage("employees-feedback", "Operação realizada com sucesso.");
    } catch (error) {
      const owner = payload.rfid_tag
        ? state.employees.find(
          (employee) =>
            String(employee.rfid_tag || "").toUpperCase() === payload.rfid_tag &&
              employee.id !== state.editingEmployeeId,
        )
        : null;
      const message = owner && String(error.message || "").includes("rfid_tag already exists")
        ? `rfid_tag already exists (${owner.name})`
        : error.message;
      showMessage("employee-form-feedback", message);
      markEmployeeFormField(message);
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = state.editingEmployeeId ? "Salvar" : "Cadastrar";
    }
  });

  document.getElementById("btn-employee-cancel").addEventListener("click", resetEmployeeForm);
  document.getElementById("btn-employee-clear").addEventListener("click", resetEmployeeForm);
  document.getElementById("btn-refresh-employees").addEventListener("click", loadEmployees);
  ["employee-search", "filter-active", "filter-access"].forEach((id) => {
    document.getElementById(id).addEventListener("input", renderEmployeeRows);
    document.getElementById(id).addEventListener("change", renderEmployeeRows);
  });

  document.getElementById("employees-body").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const employeeId = Number(button.dataset.id);
    if (button.dataset.action === "edit") {
      await editEmployee(employeeId);
      return;
    }
    if (button.dataset.action === "delete") {
      await deleteEmployee(employeeId);
    }
  });
}

function setupLogs() {
  document.getElementById("btn-logs-apply").addEventListener("click", () => {
    state.logs.offset = 0;
    loadLogs();
  });
  document.getElementById("btn-logs-clear").addEventListener("click", () => {
    document.getElementById("logs-filters").reset();
    document.getElementById("logs-search").value = "";
    state.logs.offset = 0;
    loadLogs();
  });
  document.getElementById("logs-search").addEventListener("input", () => {
    state.logs.offset = 0;
    renderLogs();
  });
  document.getElementById("logs-prev").addEventListener("click", () => {
    state.logs.offset = Math.max(0, state.logs.offset - state.logs.limit);
    loadLogs();
  });
  document.getElementById("logs-next").addEventListener("click", () => {
    state.logs.offset += state.logs.limit;
    loadLogs();
  });
  document.getElementById("btn-logs-export").addEventListener("click", () => {
    const rows = currentSearchedLogsRows();
    if (!rows.length) {
      showMessage("logs-feedback", "Sem dados para exportar.");
      return;
    }
    const csvValue = [
      ["id", "timestamp", "tipo", "tag_rfid", "colaborador_id", "nome", "matricula", "origem"].join(","),
      ...rows.map((event) => {
        const employee = employeeById(event.employee_id);
        const cols = [
          event.id || "",
          event.timestamp || "",
          event.type || "",
          event.rfid_tag || "",
          event.employee_id || "",
          event.employee_name || employee?.name || "",
          employee?.registration_id || "",
          event.source || "",
        ];
        return cols
          .map((value) => {
            const text = String(value);
            return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
          })
          .join(",");
      }),
    ].join("\n");
    const blob = new Blob([csvValue], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "eventos-filtrados.csv";
    link.click();
    URL.revokeObjectURL(url);
  });
}

function setupReports() {
  document.getElementById("btn-reports-refresh").addEventListener("click", loadReports);
  document.getElementById("report-grouping").addEventListener("change", () => {
    renderReportChart(state.reportsCache || []);
  });
  document.getElementById("btn-reports-export").addEventListener("click", () => {
    const params = new URLSearchParams();
    const from = toIsoWithTimezone(document.getElementById("reports-from").value);
    const to = toIsoWithTimezone(document.getElementById("reports-to").value);
    if (from) params.set("from", from);
    if (to) params.set("to", to);
    location.href = `/api/export/events.json${params.toString() ? `?${params.toString()}` : ""}`;
  });
}

function setupTopActions() {
  document.getElementById("btn-refresh-dashboard").addEventListener("click", refreshDashboard);
  document.getElementById("btn-refresh-monitoring").addEventListener("click", refreshMonitoring);
  document.getElementById("btn-refresh-devices").addEventListener("click", refreshDevices);
  document.getElementById("btn-notifications").addEventListener("click", () => {
    switchView("monitoring");
    const alertsCard = document.getElementById("monitoring-alerts");
    if (alertsCard) alertsCard.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  document.getElementById("btn-logout").addEventListener("click", async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      location.href = "/login";
    }
  });
}

function startPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = setInterval(() => {
    if (state.currentView === "monitoring") {
      refreshMonitoring();
      return;
    }
    if (state.currentView === "dashboard") {
      refreshDashboard();
    }
  }, 5000);
}

function setDefaultDateFilters() {
  const now = new Date();
  const today = now.toISOString().slice(0, 10);
  document.getElementById("reports-date").value = today;
  document.getElementById("reports-to").value = toIsoLocalInput(now.toISOString());
  document.getElementById("reports-from").value = toIsoLocalInput(new Date(now.getTime() - 24 * 3600 * 1000).toISOString());
  document.getElementById("logs-to").value = toIsoLocalInput(now.toISOString());
  document.getElementById("logs-from").value = toIsoLocalInput(new Date(now.getTime() - 24 * 3600 * 1000).toISOString());
}

async function bootstrap() {
  setupSessionCard();
  setupMenu();
  setupEmployees();
  setupLogs();
  setupReports();
  setupTopActions();
  setDefaultDateFilters();
  startTopbarClock();
  resetEmployeeForm();
  await loadEmployees();
  await Promise.all([refreshDashboard(), refreshMonitoring(), loadLogs(), loadReports(), refreshDevices()]);
  startPolling();
}

bootstrap();
