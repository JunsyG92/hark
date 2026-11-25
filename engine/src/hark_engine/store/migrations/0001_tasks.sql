CREATE TABLE tasks (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    assignee      TEXT NOT NULL DEFAULT '',
    due           TEXT,
    priority      TEXT NOT NULL DEFAULT 'normal'
                  CHECK (priority IN ('low', 'normal', 'high')),
    "column"      TEXT NOT NULL
                  CHECK ("column" IN ('to_validate', 'todo', 'in_progress', 'done')),
    position      REAL NOT NULL,
    source        TEXT NOT NULL,
    evidence_meeting_id TEXT,
    evidence_start_ms   INTEGER,
    evidence_end_ms     INTEGER,
    is_mine       INTEGER NOT NULL DEFAULT 0,
    confidence    REAL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE INDEX idx_tasks_column_position ON tasks ("column", position);
