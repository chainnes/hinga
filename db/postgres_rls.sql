-- Hinga row-level security for Postgres (including Supabase).
--
-- The running app also filters every private query by the signed-in person.
-- These policies are the database backstop, and they only bind for a role
-- that does not bypass RLS. Superusers bypass them even with FORCE.
-- Connect the app as hinga_app, not as a superuser.
--
-- Replace the password before you run this file. Then set DATABASE_URL to
-- that role. Safe to re-run: policies are dropped and created again.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'hinga_app') THEN
    CREATE ROLE hinga_app
      LOGIN
      PASSWORD 'replace-me'
      NOSUPERUSER
      NOBYPASSRLS
      NOCREATEDB
      NOCREATEROLE;
  END IF;
END
$$;

CREATE TABLE IF NOT EXISTS users (
  id VARCHAR(36) PRIMARY KEY,
  display_name VARCHAR(120) NOT NULL
);

CREATE TABLE IF NOT EXISTS profiles (
  user_id VARCHAR(36) PRIMARY KEY REFERENCES users (id),
  values_sealed TEXT NOT NULL,
  goals_sealed TEXT NOT NULL,
  tone_sealed TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journal_entries (
  id VARCHAR(36) PRIMARY KEY,
  user_id VARCHAR(36) NOT NULL REFERENCES users (id),
  body TEXT NOT NULL, -- Fernet ciphertext, never plaintext
  mood INTEGER NOT NULL,
  created_at TIMESTAMP NOT NULL,
  embedding_json TEXT NOT NULL DEFAULT '[]',
  embedding_space VARCHAR(80) NOT NULL DEFAULT 'local',
  reflection_json TEXT, -- ciphertext when present
  analysis_json TEXT, -- ciphertext when present
  analysis_status VARCHAR(20) NOT NULL DEFAULT 'analyzed',
  safety_hold BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS habits (
  id VARCHAR(36) PRIMARY KEY,
  user_id VARCHAR(36) NOT NULL REFERENCES users (id),
  name VARCHAR(120) NOT NULL,
  intention TEXT NOT NULL,
  intention_small TEXT NOT NULL DEFAULT '',
  value_link TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS habit_logs (
  id VARCHAR(36) PRIMARY KEY,
  user_id VARCHAR(36) NOT NULL REFERENCES users (id),
  habit_id VARCHAR(36) NOT NULL REFERENCES habits (id),
  logged_on DATE NOT NULL,
  CONSTRAINT habit_log_once UNIQUE (habit_id, logged_on)
);

CREATE INDEX IF NOT EXISTS ix_journal_entries_user_id ON journal_entries (user_id);
CREATE INDEX IF NOT EXISTS ix_habits_user_id ON habits (user_id);
CREATE INDEX IF NOT EXISTS ix_habit_logs_user_id ON habit_logs (user_id);
CREATE INDEX IF NOT EXISTS ix_habit_logs_habit_id ON habit_logs (habit_id);

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE profiles FORCE ROW LEVEL SECURITY;
ALTER TABLE journal_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE journal_entries FORCE ROW LEVEL SECURITY;
ALTER TABLE habits ENABLE ROW LEVEL SECURITY;
ALTER TABLE habits FORCE ROW LEVEL SECURITY;
ALTER TABLE habit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE habit_logs FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS profiles_isolation ON profiles;
CREATE POLICY profiles_isolation ON profiles
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

DROP POLICY IF EXISTS journal_entries_isolation ON journal_entries;
CREATE POLICY journal_entries_isolation ON journal_entries
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

DROP POLICY IF EXISTS habits_isolation ON habits;
CREATE POLICY habits_isolation ON habits
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

DROP POLICY IF EXISTS habit_logs_isolation ON habit_logs;
CREATE POLICY habit_logs_isolation ON habit_logs
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

GRANT USAGE ON SCHEMA public TO hinga_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON users, profiles, journal_entries, habits, habit_logs TO hinga_app;

-- Optional, not applied by this demo: CREATE EXTENSION IF NOT EXISTS vector;
-- The running desk stores local hashing vectors in embedding_json.
-- A pgvector column would be a later index, not a second source of truth.

-- The app sets this at the start of each request:
--   SELECT set_config('app.user_id', '<signed-in user id>', true);
-- users has no policy on purpose. It stores only an id and a display name.
-- The demo personas are fictional. Do not point this schema at real clinical notes.
