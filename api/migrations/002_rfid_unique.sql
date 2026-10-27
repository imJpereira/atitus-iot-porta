CREATE TABLE employees_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    registration_id TEXT NOT NULL UNIQUE,
    rfid_tag TEXT UNIQUE,
    role TEXT NOT NULL,
    has_room_access INTEGER NOT NULL DEFAULT 0 CHECK (has_room_access IN (0, 1)),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

INSERT INTO employees_new
SELECT id, name, registration_id, rfid_tag, role, has_room_access, is_active, created_at, updated_at
FROM employees;

DROP TABLE employees;
ALTER TABLE employees_new RENAME TO employees;
