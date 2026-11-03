-- One row per story. Scenes and world state are JSONB documents for now; they get their own
-- tables once the data model settles (memory retrieval, users, sharing).
CREATE TABLE stories (
    id         text PRIMARY KEY,
    title      text NOT NULL,
    premise    text NOT NULL,
    turn       integer NOT NULL DEFAULT 0,
    scenes     jsonb NOT NULL DEFAULT '[]'::jsonb,
    state      jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- The library lists the most recently played stories first.
CREATE INDEX stories_updated_at_idx ON stories (updated_at DESC);
