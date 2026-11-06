"""Offline migration planning tests. No PostgreSQL driver/server required."""
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.db.migrate import MigrationError, load_migrations, migrate, pending_migrations


def write_migration(path, name="0001_test.sql", content="SELECT 1;\n"):
    (path / name).write_text(content, encoding="utf-8")
    return load_migrations(path)


def test_default_directory_contains_actual_schema():
    assert [m.filename for m in load_migrations()] == [
        "0001_enable_pgvector.sql", "0002_application_schema.sql"
    ]


def test_empty_directory_fails_before_connect(tmp_path):
    connector = Mock()
    with pytest.raises(MigrationError, match="No SQL migrations"):
        migrate("not-used", tmp_path, connector=connector)
    connector.assert_not_called()


def test_missing_directory_fails(tmp_path):
    with pytest.raises(MigrationError, match="does not exist"):
        load_migrations(tmp_path / "missing")


@pytest.mark.parametrize("name", ["init.sql", "1_init.sql", "0001-Bad.sql"])
def test_invalid_filename_fails(tmp_path, name):
    (tmp_path / name).write_text("SELECT 1;")
    with pytest.raises(MigrationError, match="Invalid"):
        load_migrations(tmp_path)


def test_duplicate_number_fails(tmp_path):
    write_migration(tmp_path)
    with pytest.raises(MigrationError, match="duplicate"):
        write_migration(tmp_path, "0001_second.sql")


def test_blank_migration_fails(tmp_path):
    with pytest.raises(MigrationError, match="Empty migration"):
        write_migration(tmp_path, content=" \n\t")


def test_checksum_is_stable_across_newlines(tmp_path):
    first = write_migration(tmp_path)[0]
    (tmp_path / first.filename).write_bytes(b"SELECT 1;\r\n")
    assert load_migrations(tmp_path)[0].checksum == first.checksum


def test_clean_install_plans_all_files(tmp_path):
    migrations = write_migration(tmp_path)
    assert pending_migrations(migrations, {}) == migrations


def test_replay_plans_no_changes(tmp_path):
    migrations = write_migration(tmp_path)
    assert pending_migrations(migrations, {m.filename: m.checksum for m in migrations}) == []


def test_changed_applied_migration_fails(tmp_path):
    migrations = write_migration(tmp_path)
    with pytest.raises(MigrationError, match="Checksum mismatch"):
        pending_migrations(migrations, {migrations[0].filename: "0" * 64})


def test_unknown_history_fails(tmp_path):
    with pytest.raises(MigrationError, match="missing from checkout"):
        pending_migrations(write_migration(tmp_path), {"0099_missing.sql": "0" * 64})


def test_out_of_order_history_fails(tmp_path):
    write_migration(tmp_path)
    migrations = write_migration(tmp_path, "0002_second.sql")
    with pytest.raises(MigrationError, match="contiguous prefix"):
        pending_migrations(migrations, {migrations[1].filename: migrations[1].checksum})


def test_url_required_no_implicit_target(tmp_path, monkeypatch):
    write_migration(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(MigrationError, match="DATABASE_URL is required"):
        migrate(directory=tmp_path)


def test_paths_independent_of_current_working_directory(tmp_path, monkeypatch):
    before = load_migrations()
    monkeypatch.chdir(tmp_path)
    assert load_migrations() == before


def test_env_url_is_read_at_call_time(tmp_path, monkeypatch):
    write_migration(tmp_path)
    connector = Mock(side_effect=RuntimeError("intercept"))
    monkeypatch.setenv("DATABASE_URL", "postgresql://test.invalid/placeholder")
    with pytest.raises(RuntimeError, match="intercept"):
        migrate(directory=tmp_path, connector=connector)
    assert connector.call_args.args[0] == "postgresql://test.invalid/placeholder"
