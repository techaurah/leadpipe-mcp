"""Demo dataset (SPEC Section 5).

Twelve leads across every stage and band, five seeded busy blocks over
the next three business days, and audit entries for the seeded captures,
including one capture that was deduplicated. Everything is generated
relative to a supplied ``now`` so tests are deterministic; demo mode
passes the real current time.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

from .models import normalise_phone
from .store import schema

# name, email, phone, company, source, service, stage,
# components (problem, fit, value, size, pay, access, urgency, activity) or None,
# created_days_ago, next_action, next_action_in_days (relative, None = none)
_LEADS = [
    (
        "Amara Chen",
        "amara@brightpathlegal.com",
        "+1 415-555-0132",
        "Brightpath Legal",
        "website",
        "AI lead automation",
        "BOOKED",
        (18, 19, 14, 9, 9, 10, 6, 3),
        6,
        "Prepare for discovery call",
        1,
    ),
    (
        "Diego Ramirez",
        "diego@ramirezrealty.com",
        "+1 512-555-0176",
        "Ramirez Realty",
        "instagram",
        "AI lead automation",
        "QUALIFIED",
        (20, 20, 15, 9, 10, 9, 5, 4),
        5,
        "Send qualification summary",
        -1,
    ),
    (
        "Priya Nair",
        "priya@glowclinic.example",
        "+44 20 7946 0311",
        "Glow Clinic",
        "referral",
        "Booking automation",
        "NEW",
        (17, 18, 13, 8, 8, 9, 5, 3),
        1,
        "First reply",
        1,
    ),
    (
        "Tom Becker",
        "tom@beckerplumbing.com",
        "+1 312-555-0143",
        "Becker Plumbing",
        "call",
        "Missed-call follow-up",
        "CONTACTED",
        (15, 16, 11, 7, 7, 8, 5, 3),
        4,
        "Second follow-up",
        0,
    ),
    (
        "Sofia Marino",
        "sofia@marinodental.example",
        "+39 06 5550 118",
        "Marino Dental",
        "website",
        "AI receptionist",
        "NEGOTIATION",
        (14, 15, 10, 6, 6, 7, 5, 3),
        9,
        "Confirm package terms",
        2,
    ),
    (
        "James O'Neill",
        "james@oneillroofing.example",
        "+1 617-555-0119",
        "O'Neill Roofing",
        "facebook",
        "Quote follow-up automation",
        "NURTURE",
        (12, 13, 8, 5, 5, 6, 3, 3),
        12,
        "Monthly check-in",
        20,
    ),
    (
        "Lena Fischer",
        "lena@fischerconsulting.example",
        "+49 30 5550 207",
        "Fischer Consulting",
        "email",
        "Pipeline cleanup",
        "DISCOVERY",
        (11, 12, 7, 5, 4, 5, 4, 2),
        3,
        "Book discovery call",
        3,
    ),
    (
        "Omar Haddad",
        "omar@haddadhomes.example",
        "+971 4 555 0148",
        "Haddad Homes",
        "whatsapp",
        "Lead capture",
        "NEW",
        (8, 9, 4, 3, 3, 3, 2, 2),
        2,
        "First reply",
        0,
    ),
    (
        "Grace Liu",
        "grace@liuwellness.example",
        "+1 206-555-0164",
        "Liu Wellness",
        "walk_in",
        "Appointment reminders",
        "NEW",
        None,
        0,
        "Qualify",
        1,
    ),
    (
        "Karl Jensen",
        "karl@jensensolar.example",
        "+45 33 5550 92",
        "Jensen Solar",
        "website",
        "AI lead automation",
        "LOST",
        (16, 15, 10, 6, 7, 8, 5, 3),
        15,
        "",
        None,
    ),
    (
        "Mia Kowalski",
        "mia@kowalskilaw.example",
        "+48 22 555 0137",
        "Kowalski Law",
        "referral",
        "Intake automation",
        "PROPOSAL",
        (17, 17, 12, 8, 8, 8, 5, 3),
        7,
        "Proposal review call",
        4,
    ),
    (
        "Noah Smith",
        "noah@smithagency.example",
        "+1 646-555-0128",
        "Smith Agency",
        "other",
        "AI lead automation",
        "WON",
        (17, 18, 12, 8, 8, 8, 5, 3),
        20,
        "",
        None,
    ),
]

_COMPONENT_KEYS = (
    "problem",
    "fit",
    "value",
    "size",
    "pay",
    "access",
    "urgency",
    "activity",
)


def _band(total: int) -> str:
    if total >= 80:
        return "HOT"
    if total >= 65:
        return "WARM"
    if total >= 50:
        return "NURTURE"
    return "LOW"


def seed_demo_dataset(client, now: datetime | None = None) -> dict:
    """Seed the dataset into a bootstrapped client (fake or Sheets).

    Only runs against an empty Leads tab, so bootstrap --demo stays
    idempotent. Returns a summary of what was seeded.
    """
    if client.list_leads():
        return {"seeded": False, "reason": "Leads tab is not empty"}
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    year = moment.year
    today = moment.date()

    lead_ids: list[str] = []
    for idx, lead in enumerate(_LEADS, start=1):
        (
            name,
            email,
            phone,
            company,
            source,
            service,
            stage,
            components,
            created_days_ago,
            next_action,
            next_in_days,
        ) = lead
        lead_id = f"LP-{year}-{idx:05d}"
        lead_ids.append(lead_id)
        created = moment - timedelta(days=created_days_ago)
        row = {h: "" for h in schema.LEADS_HEADERS}
        row.update(
            {
                "lead_id": lead_id,
                "created_at": created.isoformat().replace("+00:00", "Z"),
                "updated_at": created.isoformat().replace("+00:00", "Z"),
                "name": name,
                "email": email.strip().lower(),
                "phone": normalise_phone(phone),
                "company": company,
                "source": source,
                "service_interest": service,
                "stage": stage,
                "owner": "unassigned",
                "next_action": next_action,
                "next_action_date": (
                    (today + timedelta(days=next_in_days)).isoformat()
                    if next_in_days is not None
                    else ""
                ),
            }
        )
        if components is not None:
            total = sum(components)
            for key, value in zip(_COMPONENT_KEYS, components, strict=False):
                row[f"score_{key}"] = str(value)
            row["score_total"] = str(total)
            row["band"] = _band(total)
        client.append_lead(row)
        client.append_audit(
            {
                "timestamp": row["created_at"],
                "action": "capture_lead",
                "lead_id": lead_id,
                "detail": '{"created": true, "seeded": true}',
                "mode": "direct",
                "actor": schema.ACTOR,
            }
        )
        if components is not None:
            client.append_audit(
                {
                    "timestamp": row["created_at"],
                    "action": "score_lead",
                    "lead_id": lead_id,
                    "detail": f'{{"new_total": {sum(components)}, "seeded": true}}',
                    "mode": "direct",
                    "actor": schema.ACTOR,
                }
            )

    # The deliberate duplicate: Tom Becker was captured again by email two
    # days after the first capture and deduped onto the same lead.
    becker_id = lead_ids[3]
    client.append_audit(
        {
            "timestamp": (moment - timedelta(days=2))
            .isoformat()
            .replace("+00:00", "Z"),
            "action": "capture_lead",
            "lead_id": becker_id,
            "detail": '{"deduped": true, "matched_on": "email", "seeded": true}',
            "mode": "direct",
            "actor": schema.ACTOR,
        }
    )

    # Five busy blocks over the next three business days (skipping
    # weekends relative to the seed moment), plus Amara Chen's booked
    # appointment on the first business day.
    business_days: list = []
    cursor = today
    while len(business_days) < 3:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            business_days.append(cursor)
    blocks = [
        (0, time(9, 0), time(10, 0), "Team standup (seeded busy)"),
        (0, time(13, 0), time(14, 30), "Client workshop (seeded busy)"),
        (1, time(11, 0), time(12, 0), "Site visit (seeded busy)"),
        (1, time(15, 0), time(16, 0), "Supplier call (seeded busy)"),
        (2, time(9, 30), time(10, 30), "Admin block (seeded busy)"),
    ]
    for day_idx, start_t, end_t, title in blocks:
        day = business_days[day_idx]
        client.create_event(
            start=datetime.combine(day, start_t, tzinfo=UTC),
            end=datetime.combine(day, end_t, tzinfo=UTC),
            title=title,
            description="Seeded demo busy block.",
            lead_id="",
            idempotency_key=f"seed-busy-{day_idx}-{start_t.hour}",
        )
    amara_day = business_days[0]
    appt_start = datetime.combine(amara_day, time(10, 0), tzinfo=UTC)
    appt_end = datetime.combine(amara_day, time(10, 30), tzinfo=UTC)
    from .models import idempotency_key

    key = idempotency_key(
        lead_ids[0],
        appt_start.isoformat().replace("+00:00", "Z"),
        appt_end.isoformat().replace("+00:00", "Z"),
    )
    event = client.create_event(
        start=appt_start,
        end=appt_end,
        title="AI lead automation — Amara Chen",
        description=f"LeadPipe lead: {lead_ids[0]}",
        lead_id=lead_ids[0],
        idempotency_key=key,
    )
    client.update_lead(
        lead_ids[0],
        {
            "appointment_id": event["id"],
            "appointment_start": appt_start.isoformat().replace("+00:00", "Z"),
            "appointment_status": "confirmed",
        },
    )
    client.set_meta("next_lead_seq", str(len(_LEADS) + 1))
    return {
        "seeded": True,
        "leads": len(lead_ids),
        "lead_ids": lead_ids,
        "busy_blocks": len(blocks),
        "business_days": [d.isoformat() for d in business_days],
    }
