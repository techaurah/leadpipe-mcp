"""capture_lead dedup behaviour (SPEC 2.1, Section 7 list)."""

from leadpipe import errors
from leadpipe.tools import dispatch


def capture(ctx, **kwargs):
    kwargs.setdefault("source", "website")
    return dispatch(ctx, "capture_lead", **kwargs)


def test_create_assigns_leadpipe_id(empty_ctx):
    result = capture(empty_ctx, name="First", email="first@example.com")
    assert result["ok"] is True
    assert result["created"] is True
    assert result["deduped"] is False
    assert result["lead_id"].startswith("LP-")
    assert result["lead_id"].endswith("00001")
    assert result["stage"] == "NEW"


def test_exact_email_match_dedupes(empty_ctx):
    first = capture(empty_ctx, name="A", email="dup@example.com")
    second = capture(empty_ctx, name="A Again", email="dup@example.com")
    assert second["created"] is False
    assert second["deduped"] is True
    assert second["matched_on"] == "email"
    assert second["lead_id"] == first["lead_id"]
    assert len(empty_ctx.store.list_leads()) == 1


def test_email_match_is_case_insensitive(empty_ctx):
    capture(empty_ctx, name="Case", email="Mixed@Example.COM")
    second = capture(empty_ctx, name="Case", email="mixed@example.com")
    assert second["deduped"] is True
    assert second["matched_on"] == "email"


def test_phone_match_with_different_formatting(empty_ctx):
    first = capture(empty_ctx, name="Phone", phone="+92 300-1234567")
    second = capture(empty_ctx, name="Phone", phone="00923001234567")
    assert second["deduped"] is True
    assert second["matched_on"] == "phone"
    assert second["lead_id"] == first["lead_id"]


def test_email_miss_phone_hit_precedence(empty_ctx):
    capture(empty_ctx, name="P", email="p@example.com", phone="+1 415-555-0100")
    second = capture(
        empty_ctx, name="P", email="other@example.com", phone="+14155550100"
    )
    assert second["deduped"] is True
    assert second["matched_on"] == "phone"


def test_email_wins_over_phone_when_both_could_match(empty_ctx):
    a = capture(empty_ctx, name="A", email="a@example.com", phone="+14155550111")
    capture(empty_ctx, name="B", email="b@example.com", phone="+14155550222")
    # Matches A's email and B's phone: email is searched first.
    result = capture(empty_ctx, name="C", email="a@example.com", phone="+14155550222")
    assert result["lead_id"] == a["lead_id"]
    assert result["matched_on"] == "email"


def test_duplicate_fills_only_empty_fields(empty_ctx):
    first = capture(empty_ctx, name="Fill", email="fill@example.com")
    second = capture(
        empty_ctx,
        name="Fill",
        email="fill@example.com",
        phone="+1 415-555-0177",
        company="Fill Co",
        location="Austin",
    )
    assert second["deduped"] is True
    lead = dispatch(empty_ctx, "get_lead", lead_id=first["lead_id"])["lead"]
    assert lead["phone"] == "+14155550177"
    assert lead["company"] == "Fill Co"
    assert lead["location"] == "Austin"


def test_duplicate_never_changes_stage_or_score(empty_ctx):
    first = capture(empty_ctx, name="Keep", email="keep@example.com")
    lead_id = first["lead_id"]
    dispatch(empty_ctx, "update_stage", lead_id=lead_id, stage="CONTACTED")
    dispatch(
        empty_ctx,
        "score_lead",
        lead_id=lead_id,
        scores={
            "problem": 10,
            "fit": 10,
            "value": 5,
            "size": 5,
            "pay": 5,
            "access": 5,
            "urgency": 5,
            "activity": 5,
        },
    )
    capture(empty_ctx, name="Keep", email="keep@example.com", company="New Co")
    lead = dispatch(empty_ctx, "get_lead", lead_id=lead_id)["lead"]
    assert lead["stage"] == "CONTACTED"
    assert lead["score_total"] == 50
    assert lead["company"] == "New Co"


def test_missing_both_contact_keys_rejected(empty_ctx):
    result = capture(empty_ctx, name="NoContact")
    assert result["ok"] is False
    assert result["error"]["code"] == errors.VALIDATION_ERROR


def test_validation_errors(empty_ctx):
    assert (
        capture(empty_ctx, name="  ", email="x@example.com")["error"]["code"]
        == errors.VALIDATION_ERROR
    )
    assert (
        capture(empty_ctx, name="Bad", email="not-an-email")["error"]["code"]
        == errors.VALIDATION_ERROR
    )
    bad_source = dispatch(
        empty_ctx,
        "capture_lead",
        name="Src",
        email="s@example.com",
        source="carrier_pigeon",
    )
    assert bad_source["error"]["code"] == errors.VALIDATION_ERROR


def test_ids_increment_and_are_never_reused(empty_ctx):
    a = capture(empty_ctx, name="One", email="one@example.com")
    b = capture(empty_ctx, name="Two", email="two@example.com")
    assert a["lead_id"].endswith("00001")
    assert b["lead_id"].endswith("00002")
    assert empty_ctx.store.get_meta("next_lead_seq") == "3"
