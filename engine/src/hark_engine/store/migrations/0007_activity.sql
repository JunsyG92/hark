-- Gamification ledger: one row per credited action. Derived from board actions only (no extra tracking).
CREATE TABLE activity (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    kind      TEXT NOT NULL CHECK (kind IN ('task_completed', 'proposal_validated')),
    task_id   TEXT NOT NULL,
    title     TEXT NOT NULL DEFAULT '',
    mine      INTEGER NOT NULL DEFAULT 0,
    person_id TEXT,
    on_time   INTEGER NOT NULL DEFAULT 0,
    points    INTEGER NOT NULL DEFAULT 0,
    at        TEXT NOT NULL,
    day       TEXT NOT NULL          -- local date YYYY-MM-DD
);

-- A task is credited at most once per kind: moving it in and out of « Fait » cannot farm points.
CREATE UNIQUE INDEX idx_activity_once ON activity (kind, task_id);
CREATE INDEX idx_activity_day ON activity (day);

-- Approximate history for tasks already done before this feature (no points: we cannot know when/how).
INSERT INTO activity (kind, task_id, title, mine, person_id, on_time, points, at, day)
SELECT 'task_completed', id, title,
       CASE WHEN is_mine = 1 OR (assignee_id IS NULL AND assignee = '') THEN 1 ELSE 0 END,
       assignee_id, 0, 0, updated_at, substr(updated_at, 1, 10)
FROM tasks WHERE "column" = 'done';
