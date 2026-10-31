#!/usr/bin/env python3
"""LeadPipe demo walkthrough: the full SPEC Section 5 sequence, offline.

Runs entirely against the in-memory fake client. No Google account, no
credentials, no MCP client needed:

    pip install -e .
    python examples/demo_walkthrough.py

It captures a lead, captures the same contact again (deduped), scores
it HOT, lists hot leads, checks availability on the seeded calendar,
books in approval mode (preview first, then confirm), re-books the
same slot (no duplicate), and prints the daily pipeline summary.
"""

from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from leadpipe.config import Config  # noqa: E402
from leadpipe.demo_data import seed_demo_dataset  # noqa: E402
from leadpipe.models import WriteMode  # noqa: E402
from leadpipe.store.fake import FakeGoogleClient  # noqa: E402
from leadpipe.store.schema import bootstrap_store  # noqa: E402
from leadpipe.tools import ToolContext, dispatch  # noqa: E402


def show(title: str, result: dict) -> None:
    print(f"\n== {title} ==")
    print(json.dumps(result, indent=2))


def main() -> int:
    client = FakeGoogleClient()
    bootstrap_store(client)
    seed = seed_demo_dataset(client)
    # Approval mode, to demonstrate the preview-then-confirm flow.
    ctx = ToolContext(
        store=client,
        calendar=client,
        config=Config(demo=True, write_mode=WriteMode.APPROVAL),
    )
    print("LeadPipe demo walkthrough (fake client, approval mode)")
    print(f"Seeded {seed['leads']} leads; business days: {seed['business_days']}")

    created = dispatch(
        ctx,
        "capture_lead",
        name="Walkthrough Wendy",
        email="wendy@wendysalon.example",
        phone="+1 415-555-0199",
        company="Wendy's Salon",
        source="website",
        service_interest="Booking automation",
        confirm=True,
    )
    show("1. capture_lead (new lead)", created)
    lead_id = created["lead_id"]

    dupe = dispatch(
        ctx,
        "capture_lead",
        name="Walkthrough Wendy",
        email="WENDY@wendysalon.example",
        phone="+14155550199",
        source="instagram",
        confirm=True,
    )
    show("2. capture_lead again (same contact, deduped)", dupe)

    scored = dispatch(
        ctx,
        "score_lead",
        lead_id=lead_id,
        scores={
            "problem": 18,
            "fit": 19,
            "value": 13,
            "size": 8,
            "pay": 9,
            "access": 9,
            "urgency": 6,
            "activity": 3,
        },
        confirm=True,
    )
    show("3. score_lead (total computed server-side)", scored)

    hot = dispatch(ctx, "list_hot_leads", limit=5)
    show("4. list_hot_leads", hot)

    day = seed["business_days"][0]
    avail = dispatch(
        ctx,
        "check_availability",
        start=f"{day}T00:00:00Z",
        end=f"{day}T23:59:59Z",
        slot_minutes=30,
    )
    show("5. check_availability (seeded calendar)", avail)
    slot = next(s for s in avail["slots"] if s["start"] >= f"{day}T10:30")
    start = slot["start"]
    from datetime import datetime

    end_dt = datetime.fromisoformat(start.replace("Z", "+00:00")) + timedelta(
        minutes=30
    )
    end = end_dt.isoformat().replace("+00:00", "Z")

    preview = dispatch(ctx, "book_appointment", lead_id=lead_id, start=start, end=end)
    show("6. book_appointment without confirm (approval preview)", preview)

    booked = dispatch(
        ctx,
        "book_appointment",
        lead_id=lead_id,
        start=start,
        end=end,
        confirm=True,
    )
    show("7. book_appointment with confirm=true", booked)

    again = dispatch(
        ctx,
        "book_appointment",
        lead_id=lead_id,
        start=start,
        end=end,
        confirm=True,
    )
    show("8. book_appointment again (idempotent, no duplicate)", again)

    summary = dispatch(ctx, "daily_pipeline_summary")
    show("9. daily_pipeline_summary", summary)
    print("\nWalkthrough complete: every step ran offline against the fake client.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
