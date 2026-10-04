import datetime as dt

from app import nlu

T = dt.date(2026, 10, 1)  # a Thursday


def run(msg):
    s = nlu.extract_slots(msg, T)
    return nlu.classify(msg, s)["intent"], s


def test_pto_request_slots():
    intent, s = run("Can I take 3 days of PTO next week?")
    assert intent == "pto_request" and s["days"] == 3 and s["start_date"] == "2026-10-05"


def test_remote_six_weeks_is_30_business_days():
    intent, s = run("Can I work remotely from Spain for six weeks?")
    assert intent == "remote_work" and s["business_days"] == 30 and s["destination_country"] == "Spain"


def test_date_range_counts_working_days():
    _, s = run("Can I take Dec 22 to Dec 24 off?")
    assert s["days"] == 3 and s["start_date"] == "2026-12-22"


def test_intents():
    assert run("How many PTO days do I have left?")[0] == "pto_balance"
    assert run("My manager is harassing me")[0] == "hr_case"
    assert run("What is the PTO carryover limit?")[0] == "policy_qa"
    assert run("I need some time off")[0] == "ambiguous"
    assert run("help")[0] == "ambiguous"
    assert run("What is the weather in Paris today?")[0] == "out_of_scope"


def test_generic_multi_topic_question_is_policy_qa_not_personal_expense():
    intent, _ = run("Can a new hire still in the 90-day introductory period take PTO, work from another state, or claim the home office stipend?")
    assert intent == "policy_qa"
