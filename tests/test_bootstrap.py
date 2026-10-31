"""Bootstrap (SPEC 3.3): creates schema, idempotent, aborts unchanged
on mismatched headers."""

import pytest

from leadpipe import errors
from leadpipe.store import schema
from leadpipe.store.fake import FakeGoogleClient
from leadpipe.store.schema import bootstrap_store


def test_bootstrap_creates_schema_on_empty_client():
    client = FakeGoogleClient()
    report = bootstrap_store(client)
    assert sorted(report["created_tabs"]) == ["AuditLog", "Leads", "Meta"]
    assert client.get_headers("Leads") == schema.LEADS_HEADERS
    assert client.get_headers("AuditLog") == schema.AUDIT_HEADERS
    assert client.get_meta("schema_version") == "1"
    assert client.get_meta("next_lead_seq") == "1"
    assert client.get_meta("created_by") == "leadpipe-bootstrap"


def test_bootstrap_is_idempotent():
    client = FakeGoogleClient()
    bootstrap_store(client)
    client.set_meta("next_lead_seq", "42")
    report = bootstrap_store(client)
    assert report["created_tabs"] == []
    assert report["meta_initialised"] is False
    # An advanced counter is never reset by a re-run.
    assert client.get_meta("next_lead_seq") == "42"


def test_bootstrap_aborts_unchanged_on_mismatched_headers():
    client = FakeGoogleClient()
    client.create_tab("Leads", ["lead_id", "wrong", "headers"])
    with pytest.raises(errors.LeadPipeError) as excinfo:
        bootstrap_store(client)
    assert excinfo.value.code == errors.SCHEMA_MISMATCH
    # Nothing else was created or changed.
    assert client.has_tab("AuditLog") is False
    assert client.has_tab("Meta") is False
    assert client.get_headers("Leads") == ["lead_id", "wrong", "headers"]


def test_bootstrap_module_demo_run():
    from leadpipe.bootstrap import run
    from leadpipe.config import Config

    result = run(Config(demo=True), demo_seed=True)
    assert result["mode"] == "demo"
    assert result["seed"]["seeded"] is True
    assert result["seed"]["leads"] == 12


def test_config_errors_are_clear_without_credentials():
    from leadpipe.config import Config

    config = Config.from_env({})
    assert config.demo is False
    with pytest.raises(errors.LeadPipeError) as excinfo:
        config.require_google()
    assert excinfo.value.code == errors.CONFIG_ERROR
    assert "LEADPIPE_SHEET_ID" in excinfo.value.message


def test_google_store_construction_error_is_clear(monkeypatch):
    # Even with env vars set, a missing credentials file must produce a
    # CONFIG_ERROR naming the problem, not a stack trace.
    from leadpipe.config import Config
    from leadpipe.store.sheets import GoogleSheetsStore

    config = Config(
        sheet_id="sheet-123",
        calendar_id="primary",
        credentials_path="/nonexistent/leadpipe-key.json",
    )
    with pytest.raises(errors.LeadPipeError) as excinfo:
        GoogleSheetsStore(config)
    assert excinfo.value.code == errors.CONFIG_ERROR
    assert "does not exist" in excinfo.value.message
