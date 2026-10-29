import pytest

from helpdesk.tools import calculate_refund, get_booking, search_policies

# NOW is 2026-06-10 09:00 +02:00, hours below are counted from there.


def test_get_booking_found():
    result = get_booking("CW-1001")
    assert result["found"] is True
    assert result["booking"]["rental_price_eur"] == 40.0


def test_get_booking_is_forgiving_about_case_and_spaces():
    assert get_booking("  cw-1002 ")["found"] is True


@pytest.mark.parametrize("booking_id", ["CW-9999", "", "1001", "DROP TABLE"])
def test_get_booking_not_found(booking_id):
    result = get_booking(booking_id)
    assert result["found"] is False
    assert "not found" in result["error"]


def test_refund_48_hours_or_more_gives_full_rental():
    # starts 06-13 10:00, 73h ahead
    result = calculate_refund("CW-1001")
    assert result["rental_refund_percent"] == 100
    assert result["rental_refund_eur"] == 40.0
    assert result["deposit_refund_eur"] == 50.0
    assert result["total_refund_eur"] == 90.0


def test_refund_exactly_48_hours_is_still_full():
    # starts 06-12 09:00, exactly 48h ahead: boundary belongs to the 100% tier
    result = calculate_refund("CW-1007")
    assert result["rental_refund_percent"] == 100
    assert result["total_refund_eur"] == 36.0 + 150.0


def test_refund_between_24_and_48_hours_gives_half():
    # starts 06-11 18:00, 33h ahead
    result = calculate_refund("CW-1002")
    assert result["rental_refund_percent"] == 50
    assert result["rental_refund_eur"] == 40.0
    assert result["total_refund_eur"] == 340.0


def test_refund_exactly_24_hours_is_half():
    # starts 06-11 09:00, exactly 24h ahead
    result = calculate_refund("CW-1010")
    assert result["rental_refund_percent"] == 50
    assert result["total_refund_eur"] == 20.0 + 150.0


def test_refund_under_24_hours_gives_no_rental_but_deposit():
    # starts today 15:00, 6h ahead
    result = calculate_refund("CW-1003")
    assert result["rental_refund_percent"] == 0
    assert result["rental_refund_eur"] == 0.0
    assert result["deposit_refund_eur"] == 50.0
    assert result["total_refund_eur"] == 50.0


def test_booking_fee_is_never_refunded():
    result = calculate_refund("CW-1001")
    assert result["booking_fee_refund_eur"] == 0.0
    assert result["booking_fee_kept_eur"] == 2.0


def test_card_refund_goes_back_to_card():
    assert "card within 5 working days" in calculate_refund("CW-1001")["refund_method"]


def test_voucher_refund_is_a_voucher():
    # paid with a voucher, 10 days ahead
    result = calculate_refund("CW-1004")
    assert result["total_refund_eur"] == 23.0 + 50.0
    assert "voucher" in result["refund_method"]
    assert "never as money" in result["refund_method"]


@pytest.mark.parametrize("booking_id", ["CW-1005", "CW-1006", "CW-1008"])
def test_not_confirmed_bookings_cannot_be_cancelled(booking_id):
    result = calculate_refund(booking_id)
    assert result["can_cancel"] is False
    assert result["total_refund_eur"] == 0.0


def test_cancel_at_a_later_time_moves_to_a_lower_tier():
    # CW-1001 starts 06-13 10:00: 49h, exactly 24h and one minute before
    assert calculate_refund("CW-1001", "2026-06-11T09:00:00+02:00")["rental_refund_percent"] == 100
    assert calculate_refund("CW-1001", "2026-06-12T10:00:00+02:00")["rental_refund_percent"] == 50
    assert calculate_refund("CW-1001", "2026-06-13T09:59:00+02:00")["rental_refund_percent"] == 0


def test_cancel_at_without_timezone_uses_shop_time():
    assert calculate_refund("CW-1001", "2026-06-12T10:00")["rental_refund_percent"] == 50


def test_cancel_after_start_is_refused():
    result = calculate_refund("CW-1003", "2026-06-10T16:00:00+02:00")
    assert result["can_cancel"] is False
    assert "contact the staff" in result["reason"]


def test_refund_for_unknown_booking():
    assert calculate_refund("CW-0000")["found"] is False


def test_refund_with_bad_date():
    assert "error" in calculate_refund("CW-1001", "next friday")


@pytest.mark.parametrize(
    ("query", "heading"),
    [
        ("What time do you open on Saturday?", "When are you open?"),
        ("How much is an e-bike for a whole day?", "Bike rental"),
        ("Can my 14-year-old rent an e-bike?", "Are there age limits?"),
        ("deposit for a kids bike", "Deposit"),
        ("cancel booking refund", "Cancelling a booking"),
    ],
)
def test_search_policies_finds_the_right_section(query, heading):
    headings = [section["heading"] for section in search_policies(query)["results"]]
    assert heading in headings


def test_search_policies_with_nothing_relevant():
    result = search_policies("capital of Australia")
    assert result["results"] == []
