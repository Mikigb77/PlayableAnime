-- The tables the old FastAPI app (before WS1) created, which may still be in Neon's production
-- branch, with one row each. CI's backend-image job loads this before `migrate` and checks the rows
-- are still there after it: no migration may drop or change them, because dropping that data needs
-- Miki (CLAUDE.md, docs/DEPLOY.md).
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
CREATE INDEX stories_updated_at_idx ON stories (updated_at DESC);

CREATE TABLE schema_migrations (
    version    text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO stories (id, title, premise, state) VALUES ('legacy-1', 'Old', 'An old story', '{}');
INSERT INTO schema_migrations (version) VALUES ('0001_create_stories');
