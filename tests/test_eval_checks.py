from eval.run_eval import check


def test_passing_case():
    case = {"expect_tools": ["calculate_refund"], "must_contain": ["340"]}
    assert check(case, "You get 340.00 EUR back.", ["get_booking", "calculate_refund"]) == []


def test_missing_tool_and_amount():
    case = {"expect_tools": ["calculate_refund"], "must_contain": ["340"]}
    assert len(check(case, "You get about 300 EUR back.", [])) == 2


def test_any_of_tools():
    case = {"expect_any_tool": ["get_booking", "calculate_refund"]}
    assert check(case, "", ["get_booking"]) == []
    assert len(check(case, "", ["search_policies"])) == 1


def test_unicode_hyphen_and_apostrophe_are_normalized():
    case = {"must_contain": ["cw-7777", "couldn't"]}
    assert check(case, "I couldn’t find CW‑7777.", []) == []


def test_refusal_needs_staff_contact_and_no_forbidden_text():
    case = {"must_refuse": True, "must_not_contain": ["Canberra"]}
    assert check(case, "I can't help. Contact help@citywheels.example.", []) == []
    assert len(check(case, "It is Canberra.", [])) == 2
