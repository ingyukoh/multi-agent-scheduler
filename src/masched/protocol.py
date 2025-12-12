"""Negotiation protocol between agents, as a LangGraph graph.

    call_for_proposals --Send per participant--> participant --> room_check --> decide
    decide --(feasible)--> prepare --(all vote yes)--> commit
                              \\--(someone objects)--> decide (next best)
    decide --(nothing feasible, or one improvement round)--> lead: the most constrained
        required agent offers a page of its own unasked free starts --> call_for_proposals
    lead --(a required agent has no unasked free start left)--> give_up: provably infeasible,
        because every start that agent could attend was already checked with everyone

Graph state is the shared message bus plus what the coordinator has been told. Calendars
live inside agent objects that the graph can only reach by message.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from masched.agents import ParticipantAgent, RoomAgent
from masched.world import SLOTS_PER_DAY, Scenario, label

OPENING_SLOTS = (2, 10)  # 10:00 and 14:00 each day: a public, calendar-blind first guess
LEAD_OFFER = 8
IMPROVEMENT_ROUNDS = 1


def merge_nested(a: dict, b: dict) -> dict:
    out = {k: dict(v) for k, v in a.items()}
    for k, v in b.items():
        out.setdefault(k, {}).update(v)
    return out


def merge(a: dict, b: dict) -> dict:
    return {**a, **b}


class State(TypedDict, total=False):
    bus: Annotated[list[dict], operator.add]
    round: int
    batch: list[int]
    asked: Annotated[list[int], operator.add]
    replies: Annotated[dict, merge_nested]  # start -> {agent: {"free", "pref"}}
    rooms: Annotated[dict, merge]  # start -> room name | None
    leads: Annotated[list[str], operator.add]
    rejected: Annotated[list[int], operator.add]
    dropped: Annotated[list[str], operator.add]
    proposal: int | None
    improving: int
    outcome: dict


def _keys(d: dict) -> dict:
    """Message bodies use string keys so the bus serializes cleanly."""
    return {str(k): v for k, v in d.items()}


def msg(sender: str, to: str, kind: str, body: dict) -> dict:
    return {"from": sender, "to": to, "type": kind, "body": body}


class Negotiation:
    def __init__(self, scenario: Scenario):
        self.sc = scenario
        self.participants = {p.name: ParticipantAgent(p, True) for p in scenario.required}
        self.participants |= {p.name: ParticipantAgent(p, False) for p in scenario.optional}
        self.room_agent = RoomAgent(scenario.rooms)
        self.required = [p.name for p in scenario.required]
        self.graph = self._build()

    # --- nodes -----------------------------------------------------------------------

    def call_for_proposals(self, state: State) -> dict:
        batch = [c for c in state["batch"] if c not in state.get("asked", [])]
        body = {"duration": self.sc.duration, "candidates": batch}
        return {
            "batch": batch,
            "asked": batch,
            "bus": [msg("coordinator", n, "cfp", body) for n in self.participants],
        }

    def fan_out(self, state: State) -> list[Send]:
        return [
            Send("participant", {"name": n, "batch": state["batch"]}) for n in self.participants
        ]

    def participant(self, payload: dict) -> dict:
        agent = self.participants[payload["name"]]
        answers = agent.answer_cfp(payload["batch"], self.sc.duration)
        return {
            "replies": {c: {agent.name: a} for c, a in answers.items()},
            "bus": [
                msg(agent.name, "coordinator", "cfp_reply", {str(c): a for c, a in answers.items()})
            ],
        }

    def room_check(self, state: State) -> dict:
        headcounts = {}
        for c in state["batch"]:
            r = state["replies"].get(c, {})
            if all(r.get(n, {}).get("free") for n in self.required):
                headcounts[c] = sum(1 for a in r.values() if a["free"])
        if not headcounts:
            return {}
        rooms = self.room_agent.answer_cfp(headcounts, self.sc.duration)
        return {
            "rooms": rooms,
            "bus": [
                msg("coordinator", "rooms", "room_query", {"headcounts": _keys(headcounts)}),
                msg("rooms", "coordinator", "room_reply", _keys(rooms)),
            ],
        }

    def _value(self, replies: dict) -> int:
        """Coordinator's estimate from disclosed buckets only."""
        return sum(a["pref"] + 1 for a in replies.values() if a["free"])

    def decide(self, state: State) -> dict:
        rejected = set(state.get("rejected", []))
        feasible = [
            c for c, room in state.get("rooms", {}).items()
            if room and c not in rejected
            and all(state["replies"][c].get(n, {}).get("free") for n in self.required)
        ]  # fmt: skip
        if feasible:
            best = max(feasible, key=lambda c: (self._value(state["replies"][c]), -c))
            return {"proposal": best}
        return {"proposal": None}

    def route_decide(self, state: State) -> str:
        if state.get("proposal") is None:
            return "lead"
        if state.get("improving", 0) < IMPROVEMENT_ROUNDS:
            return "improve"
        return "prepare"

    def _next_lead(self, state: State) -> str:
        """Round-robin over required agents, most constrained (most 'busy' replies) first."""
        led = state.get("leads", [])
        busy = {
            n: sum(1 for r in state["replies"].values() if not r.get(n, {}).get("free", True))
            for n in self.required
        }
        return min(self.required, key=lambda n: (led.count(n), -busy[n], n))

    def _offer(self, state: State, name: str) -> dict:
        exclude = set(state.get("asked", []))
        offer = self.participants[name].propose(self.sc.duration, exclude, LEAD_OFFER)
        return {
            "leads": [name],
            "round": state["round"] + 1,
            "batch": offer,
            "bus": [
                msg("coordinator", name, "lead_request", {"already_checked": len(exclude)}),
                msg(name, "coordinator", "lead_offer", {"candidates": offer}),
            ],
        }

    def lead(self, state: State) -> dict:
        return self._offer(state, self._next_lead(state))

    def route_lead(self, state: State) -> str:
        # An empty offer from a required agent means every start it can attend was already
        # checked with everyone and failed: the meeting is infeasible, not merely unfound.
        return "call_for_proposals" if state["batch"] else "give_up"

    def improve(self, state: State) -> dict:
        """One extra page from the next lead, to look for a better slot than the first found."""
        update = self._offer(state, self._next_lead(state))
        return update | {"improving": state.get("improving", 0) + 1}

    def route_improve(self, state: State) -> str:
        return "call_for_proposals" if state["batch"] else "prepare"

    def prepare(self, state: State) -> dict:
        c = state["proposal"]
        attendees = [n for n, a in state["replies"][c].items() if a["free"]]
        bus = [msg("coordinator", n, "prepare", {"start": c}) for n in attendees]
        votes = {n: self.participants[n].prepare(c, self.sc.duration) for n in attendees}
        bus += [msg(n, "coordinator", "vote", {"start": c, "ok": ok}) for n, ok in votes.items()]
        blocked_required = [n for n, ok in votes.items() if not ok and n in self.required]
        if blocked_required:
            return {"rejected": [c], "proposal": None, "bus": bus}
        dropped = [n for n, ok in votes.items() if not ok]
        going = [n for n in attendees if n not in dropped]
        room = self.room_agent.prepare(c, self.sc.duration, len(going))
        bus.append(msg("rooms", "coordinator", "vote", {"start": c, "room": room}))
        if room is None:
            return {"rejected": [c], "proposal": None, "bus": bus}
        for n in going:
            self.participants[n].commit(c, self.sc.duration)
        self.room_agent.commit(room, c, self.sc.duration)
        bus += [msg("coordinator", n, "commit", {"start": c, "room": room}) for n in going]
        return {
            "dropped": dropped,
            "bus": bus,
            "outcome": {
                "status": "booked",
                "start": c,
                "room": room,
                "attendees": going,
                "when": label(c, self.sc.duration),
            },  # fmt: skip
        }

    def route_prepare(self, state: State) -> str:
        return END if state.get("outcome") else "decide"

    def give_up(self, state: State) -> dict:
        proof = f"{state['leads'][-1]} has no unchecked free start"
        return {"outcome": {"status": "infeasible", "rounds": state["round"], "proof": proof}}

    # --- wiring ----------------------------------------------------------------------

    def _build(self):
        g = StateGraph(State)
        for name in ["call_for_proposals", "participant", "room_check", "decide", "lead",
                     "improve", "prepare", "give_up"]:  # fmt: skip
            g.add_node(name, getattr(self, name))
        g.add_edge(START, "call_for_proposals")
        g.add_conditional_edges("call_for_proposals", self.fan_out, ["participant"])
        g.add_edge("participant", "room_check")
        g.add_edge("room_check", "decide")
        g.add_conditional_edges("decide", self.route_decide, ["prepare", "lead", "improve"])
        g.add_conditional_edges("lead", self.route_lead, ["call_for_proposals", "give_up"])
        g.add_conditional_edges("improve", self.route_improve, ["call_for_proposals", "prepare"])
        g.add_conditional_edges("prepare", self.route_prepare, [END, "decide"])
        g.add_edge("give_up", END)
        return g.compile()

    def run(self) -> dict:
        opening = [
            d * SLOTS_PER_DAY + s
            for d in range(5)
            for s in OPENING_SLOTS
            if s + self.sc.duration <= SLOTS_PER_DAY
        ]
        return self.graph.invoke({"round": 1, "batch": opening}, {"recursion_limit": 1000})
