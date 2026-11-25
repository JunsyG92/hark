CREATE TABLE meetings (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL CHECK (status IN ('recording', 'recorded', 'failed')),
    app         TEXT NOT NULL DEFAULT '',
    started_at  TEXT NOT NULL,
    ended_at    TEXT,
    duration_ms INTEGER,
    system_path TEXT,
    mic_path    TEXT
);

CREATE INDEX idx_meetings_started ON meetings (started_at DESC);
