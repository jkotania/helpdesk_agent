import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent
POLICIES_DIR = DATA_DIR / "policies"
BOOKINGS_FILE = DATA_DIR / "bookings.json"

# All bookings are in June, so a fixed +02:00 is fine. Needs zoneinfo("Europe/Warsaw") once winter dates show up.
SHOP_TZ = timezone(timedelta(hours=2))
# Fixed by the task data so refunds come out the same on every run.
NOW = datetime(2026, 6, 10, 9, 0, tzinfo=SHOP_TZ)

STAFF_CONTACT = "help@citywheels.example or +48 000 000 000"

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "be",
    "can",
    "do",
    "does",
    "for",
    "how",
    "i",
    "if",
    "in",
    "is",
    "it",
    "my",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "when",
    "you",
    "your",
    "with",
    "much",
    "will",
    "get",
    "me",
    "we",
    "there",
    "this",
    "that",
    "have",
    "has",
}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    # Crude suffix stripping (bikes/bike, opening/open). Good enough for three short docs.
    return {re.sub(r"(ing|led|ed|s)$", "", w) or w for w in words if w not in STOPWORDS}


def _sections() -> list[dict]:
    sections = []
    for path in sorted(POLICIES_DIR.glob("*.md")):
        for chunk in re.split(r"\n(?=## )", path.read_text(encoding="utf-8")):
            heading = chunk.splitlines()[0].lstrip("# ").strip()
            sections.append({"source": path.name, "heading": heading, "text": chunk.strip()})
    return sections


def search_policies(query: str, limit: int = 3) -> dict:
    query_tokens = _tokens(query)
    scored = []
    for section in _sections():
        # faq.md headings are the questions themselves, so a heading hit counts twice.
        score = len(query_tokens & _tokens(section["text"])) + len(query_tokens & _tokens(section["heading"]))
        if score:
            scored.append((score, section))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    results = [section for _, section in scored[:limit]]
    if not results:
        return {"results": [], "note": "No policy section matches this question."}
    return {"results": results}


def _load_bookings() -> dict[str, dict]:
    bookings = json.loads(BOOKINGS_FILE.read_text(encoding="utf-8"))
    return {b["id"]: b for b in bookings}


def get_booking(booking_id: str) -> dict:
    booking = _load_bookings().get(booking_id.strip().upper())
    if booking is None:
        return {"found": False, "error": f"Booking {booking_id!r} was not found."}
    return {"found": True, "booking": booking}


def _parse_time(value: str | None) -> datetime:
    if not value:
        return NOW
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo else moment.replace(tzinfo=SHOP_TZ)


def calculate_refund(booking_id: str, cancel_at: str | None = None) -> dict:
    """Rules from policies/cancellations.md. cancel_at is an ISO datetime, defaults to NOW."""
    found = get_booking(booking_id)
    if not found["found"]:
        return found
    booking = found["booking"]
    try:
        moment = _parse_time(cancel_at)
    except ValueError:
        return {"error": f"cancel_at {cancel_at!r} is not an ISO date and time, e.g. 2026-06-11T09:00:00+02:00."}

    result = {"booking_id": booking["id"], "status": booking["status"], "cancel_at": moment.isoformat()}
    if booking["status"] != "confirmed":
        return result | {
            "can_cancel": False,
            "reason": f"Bookings with status '{booking['status']}' cannot be cancelled and nothing is refunded.",
            "total_refund_eur": 0.0,
        }

    start = datetime.fromisoformat(booking["start"])
    if moment >= start:
        # Policy doesn't cover cancelling after the start. Not our call, send them to the staff.
        return result | {
            "can_cancel": False,
            "reason": f"The rental has already started. Please contact the staff: {STAFF_CONTACT}.",
            "total_refund_eur": 0.0,
        }

    hours_before = (start - moment).total_seconds() / 3600
    if hours_before >= 48:
        percent = 100
    elif hours_before >= 24:
        percent = 50
    else:
        percent = 0

    rental_refund = round(booking["rental_price_eur"] * percent / 100, 2)
    deposit_refund = booking["deposit_eur"]
    if booking["paid_with"] == "voucher":
        refund_method = "as a new voucher of the same value (rental and deposit), never as money"
    else:
        refund_method = "to the same card within 5 working days"

    return result | {
        "can_cancel": True,
        "hours_before_start": round(hours_before, 2),
        "rental_refund_percent": percent,
        "rental_refund_eur": rental_refund,
        "deposit_refund_eur": deposit_refund,
        "booking_fee_refund_eur": 0.0,
        "booking_fee_kept_eur": booking["booking_fee_eur"],
        "total_refund_eur": round(rental_refund + deposit_refund, 2),
        "refund_method": refund_method,
    }


TOOLS = {
    "search_policies": search_policies,
    "get_booking": get_booking,
    "calculate_refund": calculate_refund,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_policies",
            "description": "Search the CityWheels policy documents (prices, opening hours, age limits, "
            "cancellations, payment, deposits, FAQ). Returns the most relevant sections.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Keywords or the customer's question."}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_booking",
            "description": "Get the details of one booking by its number, e.g. CW-1001.",
            "parameters": {
                "type": "object",
                "properties": {"booking_id": {"type": "string"}},
                "required": ["booking_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_refund",
            "description": "Calculate how much the customer gets back if a booking is cancelled. "
            "Always use this for refund amounts, never calculate them yourself.",
            "parameters": {
                "type": "object",
                "properties": {
                    "booking_id": {"type": "string"},
                    "cancel_at": {
                        "type": "string",
                        "description": "ISO date and time of the cancellation, e.g. 2026-06-11T09:00:00+02:00. "
                        "Leave out to cancel now.",
                    },
                },
                "required": ["booking_id"],
            },
        },
    },
]
