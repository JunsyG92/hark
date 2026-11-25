ALTER TABLE meetings ADD COLUMN analysis TEXT NOT NULL DEFAULT 'none';
ALTER TABLE meetings ADD COLUMN analysis_error TEXT;

-- One analysis per meeting. `input_hash` = sha256(prompt version, model, profile, transcript):
-- the same input is never sent to the LLM twice (token control).
CREATE TABLE analyses (
    meeting_id     TEXT PRIMARY KEY REFERENCES meetings (id) ON DELETE CASCADE,
    input_hash     TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    provider       TEXT NOT NULL,
    model          TEXT NOT NULL,
    title          TEXT NOT NULL DEFAULT '',
    summary        TEXT NOT NULL,
    decisions      TEXT NOT NULL,
    open_questions TEXT NOT NULL,
    tasks_proposed INTEGER NOT NULL DEFAULT 0,
    chunks         INTEGER NOT NULL DEFAULT 1,
    tokens_in      INTEGER NOT NULL DEFAULT 0,
    tokens_out     INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL
);
