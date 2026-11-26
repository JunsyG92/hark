-- Team directory: people tasks can be assigned to (lead follow-up).
CREATE TABLE people (
    id         TEXT PRIMARY KEY,
    first_name TEXT NOT NULL DEFAULT '',
    last_name  TEXT NOT NULL DEFAULT '',
    email      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

-- One person per e-mail (empty e-mail allowed for several people).
CREATE UNIQUE INDEX idx_people_email ON people (email) WHERE email <> '';

ALTER TABLE tasks ADD COLUMN assignee_id TEXT REFERENCES people (id) ON DELETE SET NULL;

CREATE INDEX idx_tasks_assignee ON tasks (assignee_id);
