ALTER TABLE meetings ADD COLUMN transcription TEXT NOT NULL DEFAULT 'none';
ALTER TABLE meetings ADD COLUMN transcription_error TEXT;
ALTER TABLE meetings ADD COLUMN language TEXT;
ALTER TABLE meetings ADD COLUMN audio_expires_at TEXT;

CREATE TABLE transcript_segments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id TEXT NOT NULL REFERENCES meetings (id) ON DELETE CASCADE,
    track      TEXT NOT NULL CHECK (track IN ('system', 'mic')),
    speaker    TEXT NOT NULL CHECK (speaker IN ('me', 'others')),
    start_ms   INTEGER NOT NULL,
    end_ms     INTEGER NOT NULL,
    text       TEXT NOT NULL
);

CREATE INDEX idx_segments_meeting ON transcript_segments (meeting_id, start_ms);

-- Full-text search over titles, summaries (step 5) and transcript segments.
CREATE VIRTUAL TABLE search USING fts5(
    text,
    meeting_id UNINDEXED,
    kind UNINDEXED,
    segment_id UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);
