from pathlib import Path


def test_postgres_policies_cover_every_private_table():
    sql = Path(__file__).resolve().parents[1].joinpath("db", "postgres_rls.sql").read_text(encoding="utf-8")
    for table in ("profiles", "journal_entries", "habits", "habit_logs"):
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in sql
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in sql
        assert f"CREATE POLICY {table}_isolation ON {table}" in sql
        assert "user_id = current_setting('app.user_id', true)" in sql
    assert "NOBYPASSRLS" in sql
    assert "hinga_app" in sql
    assert "replace-me" in sql
