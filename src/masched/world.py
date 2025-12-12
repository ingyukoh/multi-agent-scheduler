"""Calendar model and a seeded scenario generator.

A week has 5 days x 16 half-hour slots (09:00-17:00). A meeting of `duration` slots starts
at `start` and must end on the same day. Each person's calendar and preferences are private
to that person's agent; only the generator and the evaluator see them all.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
SLOTS_PER_DAY = 16
WEEK = len(DAYS) * SLOTS_PER_DAY


def span(start: int, duration: int) -> range:
    return range(start, start + duration)


def valid_starts(duration: int) -> list[int]:
    return [
        d * SLOTS_PER_DAY + s for d in range(len(DAYS)) for s in range(SLOTS_PER_DAY - duration + 1)
    ]


def label(start: int, duration: int = 1) -> str:
    day, slot = divmod(start, SLOTS_PER_DAY)
    h, m = divmod(9 * 60 + 30 * slot, 60)
    eh, em = divmod(9 * 60 + 30 * (slot + duration), 60)
    return f"{DAYS[day]} {h:02d}:{m:02d}-{eh:02d}:{em:02d}"


@dataclass
class Person:
    name: str
    busy: set[int]
    prefers_mornings: bool = False
    avoid_days: set[int] = field(default_factory=set)
    focus: set[int] = field(default_factory=set)
    # A slot someone else books concurrently while negotiation is under way.
    late_conflict: bool = False

    def free(self, start: int, duration: int) -> bool:
        return not any(s in self.busy for s in span(start, duration))

    def score(self, start: int, duration: int) -> int:
        """Private preference in [-3, 1]."""
        day, slot = divmod(start, SLOTS_PER_DAY)
        value = 0
        if self.prefers_mornings and slot < 6:
            value += 1
        if day in self.avoid_days:
            value -= 2
        if any(s in self.focus for s in span(start, duration)):
            value -= 1
        return value

    def preference_text(self) -> str:
        """How a person would state their preferences in natural language."""
        parts = []
        if self.prefers_mornings:
            parts.append("I prefer mornings")
        if self.avoid_days:
            parts.append("please avoid " + " and ".join(DAYS[d] for d in sorted(self.avoid_days)))
        if self.focus:
            day, slot = divmod(min(self.focus), SLOTS_PER_DAY)
            parts.append(f"I keep focus time on {DAYS[day]} from {label(min(self.focus))[4:9]}")
        return "; ".join(parts) or "no preferences"


@dataclass
class Room:
    name: str
    capacity: int
    busy: set[int]


@dataclass
class Scenario:
    id: str
    duration: int
    required: list[Person]
    optional: list[Person]
    rooms: list[Room]

    @property
    def people(self) -> list[Person]:
        return self.required + self.optional


def _busy(rng: random.Random, density: float) -> set[int]:
    busy: set[int] = set()
    while len(busy) < density * WEEK:
        start, length = rng.randrange(WEEK), rng.choice([1, 2, 2, 3, 4])
        day = start // SLOTS_PER_DAY
        busy.update(s for s in span(start, length) if s // SLOTS_PER_DAY == day)
    return busy


def generate(n: int = 40, seed: int = 7) -> list[Scenario]:
    rng = random.Random(seed)
    names = ["Ana", "Ben", "Chloe", "Dev", "Eli", "Fay", "Gus", "Hana", "Ivan", "Jun", "Kai",
             "Lea"]  # fmt: skip
    scenarios = []
    for i in range(n):
        n_req, n_opt = rng.randint(2, 5), rng.randint(0, 3)
        density = rng.choice([0.35, 0.5, 0.6, 0.7, 0.8])
        people = []
        for name in rng.sample(names, n_req + n_opt):
            focus_day, focus_slot = rng.randrange(5), rng.randrange(0, 12)
            people.append(Person(
                name=name,
                busy=_busy(rng, density),
                prefers_mornings=rng.random() < 0.5,
                avoid_days={rng.randrange(5)} if rng.random() < 0.4 else set(),
                focus=set(span(focus_day * SLOTS_PER_DAY + focus_slot, 4))
                if rng.random() < 0.5 else set(),
            ))  # fmt: skip
        if rng.random() < 0.25:
            people[0].late_conflict = True
        rooms = [
            Room("Atlas", 4, _busy(rng, 0.4)),
            Room("Borealis", 8, _busy(rng, 0.5)),
        ]
        scenarios.append(Scenario(f"S{i + 1:02d}", rng.choice([1, 2, 2, 3]),
                                  people[:n_req], people[n_req:], rooms))  # fmt: skip
    return scenarios


def room_for(rooms: list[Room], start: int, duration: int, attendees: int) -> str | None:
    for room in sorted(rooms, key=lambda r: r.capacity):
        if room.capacity >= attendees and not any(s in room.busy for s in span(start, duration)):
            return room.name
    return None


def true_utility(sc: Scenario, start: int) -> float | None:
    """Ground-truth value of a start, or None if a required person or every room is blocked."""
    if not all(p.free(start, sc.duration) for p in sc.required):
        return None
    attending = sc.required + [p for p in sc.optional if p.free(start, sc.duration)]
    if room_for(sc.rooms, start, sc.duration, len(attending)) is None:
        return None
    # Each attendee contributes 0..4, so optional attendance always adds value.
    return float(sum(p.score(start, sc.duration) + 3 for p in attending))
