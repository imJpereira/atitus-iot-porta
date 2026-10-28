CREATE TABLE events (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('entrada', 'saida', 'acesso_negado', 'tentativa_invasao')),
    rfid_tag TEXT NOT NULL,
    employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
    timestamp TEXT NOT NULL,
    source TEXT NOT NULL,
    received_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX events_timestamp ON events (timestamp);
CREATE INDEX events_employee_id ON events (employee_id);
