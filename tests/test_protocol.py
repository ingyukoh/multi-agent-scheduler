import copy

from masched.agents import ParticipantAgent, parse_preferences
from masched.evals import evaluate, optimum
from masched.protocol import Negotiation
from masched.world import Person, Room, Scenario, generate, true_utility, valid_starts

SCENARIOS = {s.id: s for s in generate()}


def run(sc):
    snap = copy.deepcopy(sc)
    return Negotiation(snap).run(), snap


def test_coordinator_state_never_contains_a_calendar():
    result, _ = run(SCENARIOS["S23"])
    for m in result["bus"]:
        assert "busy" not in m["body"] and "focus" not in m["body"]
        if m["type"] == "cfp_reply":
            assert all(set(v) == {"free", "pref"} for v in m["body"].values())


def test_participants_answer_in_parallel_superstep():
    n = Negotiation(copy.deepcopy(SCENARIOS["S04"]))
    steps = [list(u) for u in n.graph.stream({"round": 1, "batch": [2, 10]}, stream_mode="updates")]
    assert steps[1] == ["participant"] and steps.count(["participant"]) >= len(n.participants)


def test_booked_slot_is_valid_for_every_attendee_and_room():
    for sc in SCENARIOS.values():
        result, snap = run(sc)
        out = result["outcome"]
        if out["status"] != "booked":
            continue
        assert true_utility(sc, out["start"]) is not None


def test_infeasible_claims_are_proven():
    for sc in SCENARIOS.values():
        result, snap = run(sc)
        if result["outcome"]["status"] == "infeasible":
            assert all(true_utility(snap, s) is None for s in valid_starts(sc.duration))


def test_late_conflict_triggers_rebook_not_double_booking():
    result, snap = run(SCENARIOS["S23"])
    assert result["rejected"]  # first proposal voted down
    out = result["outcome"]
    assert out["status"] == "booked" and out["start"] not in result["rejected"]


def test_tiny_world_matches_optimum():
    a = Person("A", busy=set(range(0, 80)) - {33, 34}, prefers_mornings=True)
    b = Person("B", busy=set())
    sc = Scenario("T", 1, [a, b], [], [Room("R", 4, set())])
    result, _ = run(sc)
    assert result["outcome"]["start"] == optimum(sc)[0] == 33


def test_agent_discloses_only_coarse_preference():
    agent = ParticipantAgent(Person("A", busy=set(), prefers_mornings=True, avoid_days={4}), True)
    ans = agent.answer_cfp([0, 64], 1)
    assert ans[0] == {"free": True, "pref": 2} and ans[64] == {"free": True, "pref": 0}


def test_rule_based_preference_parser():
    assert parse_preferences("I prefer mornings; please avoid Mon and Fri") == {
        "prefers_mornings": True,
        "avoid_days": [0, 4],
    }


def test_evaluation_headline():
    s = evaluate()["summary"]
    ma, ce, ff = s["multi_agent"], s["centralized"], s["first_fit"]
    assert ma["double_bookings"] == 0 and ma["false_infeasible"] == 0
    assert ce["double_bookings"] > 0 and ff["double_bookings"] > 0
    assert ma["mean_disclosure"] < ce["mean_disclosure"]
    assert ma["mean_utility_vs_optimum"] > ff["mean_utility_vs_optimum"]
