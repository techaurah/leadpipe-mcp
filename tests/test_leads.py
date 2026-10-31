"""get_lead and list_hot_leads (SPEC 2.2, 2.3)."""

from leadpipe import errors
from leadpipe.tools import dispatch


def test_get_lead_by_id(demo_ctx):
    lead = dispatch(demo_ctx, "get_lead", lead_id="LP-2026-00002")["lead"]
    assert lead["name"] == "Diego Ramirez"
    assert lead["score_total"] == 92
    assert lead["band"] == "HOT"
    assert lead["score_components"]["problem"] == 20


def test_get_lead_by_email_and_phone(demo_ctx):
    by_email = dispatch(demo_ctx, "get_lead", email="PRIYA@GlowClinic.example")["lead"]
    assert by_email["lead_id"] == "LP-2026-00003"
    by_phone = dispatch(demo_ctx, "get_lead", phone="+1 (312) 555-0143")["lead"]
    assert by_phone["lead_id"] == "LP-2026-00004"


def test_get_lead_identifier_exclusivity(demo_ctx):
    none = dispatch(demo_ctx, "get_lead")
    assert none["error"]["code"] == errors.VALIDATION_ERROR
    two = dispatch(demo_ctx, "get_lead", lead_id="LP-2026-00001", email="a@b.example")
    assert two["error"]["code"] == errors.VALIDATION_ERROR


def test_get_lead_not_found(demo_ctx):
    result = dispatch(demo_ctx, "get_lead", lead_id="LP-2026-99999")
    assert result["ok"] is False
    assert result["error"]["code"] == errors.LEAD_NOT_FOUND
    result = dispatch(demo_ctx, "get_lead", email="ghost@example.com")
    assert result["error"]["code"] == errors.LEAD_NOT_FOUND


def test_get_lead_unscored_has_null_total(demo_ctx):
    lead = dispatch(demo_ctx, "get_lead", lead_id="LP-2026-00009")["lead"]
    assert lead["score_total"] is None
    assert lead["band"] is None


def test_get_lead_recomputes_total_from_components(demo_ctx):
    # A hand-edited Sheet cannot produce an inconsistent total: corrupt
    # the stored total and confirm the read recomputes it.
    demo_ctx.store.update_lead("LP-2026-00002", {"score_total": "3", "band": "LOW"})
    lead = dispatch(demo_ctx, "get_lead", lead_id="LP-2026-00002")["lead"]
    assert lead["score_total"] == 92
    assert lead["band"] == "HOT"


def test_list_hot_leads_filters_and_excludes_booked(demo_ctx):
    result = dispatch(demo_ctx, "list_hot_leads")
    ids = [lead["lead_id"] for lead in result["leads"]]
    # Seeded HOT: 00002 (92), 00003 (81); 00001 (88) is booked already.
    assert ids == ["LP-2026-00002", "LP-2026-00003"]
    assert result["count"] == 2


def test_list_hot_leads_include_booked_and_sort(demo_ctx):
    result = dispatch(demo_ctx, "list_hot_leads", include_booked=True)
    ids = [lead["lead_id"] for lead in result["leads"]]
    # Score desc: 92, 88, 81.
    assert ids == ["LP-2026-00002", "LP-2026-00001", "LP-2026-00003"]
    scores = [lead["score_total"] for lead in result["leads"]]
    assert scores == sorted(scores, reverse=True)


def test_list_hot_leads_limit_bounds(demo_ctx):
    assert (
        dispatch(demo_ctx, "list_hot_leads", limit=0)["error"]["code"]
        == errors.VALIDATION_ERROR
    )
    assert (
        dispatch(demo_ctx, "list_hot_leads", limit=101)["error"]["code"]
        == errors.VALIDATION_ERROR
    )
    one = dispatch(demo_ctx, "list_hot_leads", limit=1)
    assert one["count"] == 1
