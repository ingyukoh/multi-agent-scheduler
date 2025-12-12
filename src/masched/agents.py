"""The agents. Each owns private state; the only way to learn anything from one is a message.

ParticipantAgent  one per person: answers calls for proposals with free/busy plus a coarse
                  preference bucket, proposes its own free starts when asked to lead,
                  and votes in the two-phase commit.
RoomAgent         owns room calendars: answers which room fits a candidate.
The coordinator lives in graph.py and never sees a calendar.
"""

from __future__ import annotations

import os
import re

from masched.world import DAYS, Person, Room, room_for, valid_starts


def parse_preferences(text: str) -> dict:
    """Natural-language preference intake. Rule-based by default, Claude when configured."""
    if os.getenv("MASCHED_LLM") == "anthropic":
        return _parse_with_claude(text)
    low = text.lower()
    return {
        "prefers_mornings": "morning" in low,
        "avoid_days": sorted(
            DAYS.index(d) for d in DAYS if re.search(rf"avoid[^;]*\b{d.lower()}\b", low)
        ),
    }


def _parse_with_claude(text: str) -> dict:
    from langchain_anthropic import ChatAnthropic
    from pydantic import BaseModel

    class Prefs(BaseModel):
        prefers_mornings: bool
        avoid_days: list[int]  # 0=Mon .. 4=Fri

    model = ChatAnthropic(model="claude-sonnet-5", temperature=0).with_structured_output(Prefs)
    return model.invoke(f"Extract scheduling preferences (0=Mon..4=Fri): {text}").model_dump()


class ParticipantAgent:
    def __init__(self, person: Person, required: bool):
        self._person = person  # private
        self.name = person.name
        self.required = required
        stated = parse_preferences(person.preference_text())
        self._prefers_mornings = stated["prefers_mornings"]
        self._avoid_days = set(stated["avoid_days"])
        self._late_conflict_pending = person.late_conflict

    def _score(self, start: int, duration: int) -> int:
        """The agent's own understanding: stated preferences plus calendar focus blocks."""
        day, slot = divmod(start, 16)
        value = 1 if self._prefers_mornings and slot < 6 else 0
        value -= 2 if day in self._avoid_days else 0
        value -= 1 if any(s in self._person.focus for s in range(start, start + duration)) else 0
        return value

    def _bucket(self, start: int, duration: int) -> int:
        """Disclose only a coarse 0/1/2 preference, never the reasons behind it."""
        score = self._score(start, duration)
        return 2 if score > 0 else 1 if score == 0 else 0

    def answer_cfp(self, candidates: list[int], duration: int) -> dict[int, dict]:
        out = {}
        for c in candidates:
            free = self._person.free(c, duration)
            out[c] = {"free": free, "pref": self._bucket(c, duration) if free else None}
        return out

    def propose(self, duration: int, exclude: set[int], k: int) -> list[int]:
        """Lead a round: offer own best free starts (reveals only these k)."""
        options = [
            s for s in valid_starts(duration) if s not in exclude and self._person.free(s, duration)
        ]
        options.sort(key=lambda s: (-self._bucket(s, duration), s))
        return options[:k]

    def prepare(self, start: int, duration: int) -> bool:
        """Two-phase commit vote. A concurrent booking may have taken the slot meanwhile."""
        if self._late_conflict_pending:
            self._late_conflict_pending = False
            self._person.busy.add(start)
        return self._person.free(start, duration)

    def commit(self, start: int, duration: int) -> None:
        self._person.busy.update(range(start, start + duration))


class RoomAgent:
    def __init__(self, rooms: list[Room]):
        self._rooms = rooms  # private

    def answer_cfp(self, headcounts: dict[int, int], duration: int) -> dict[int, str | None]:
        return {c: room_for(self._rooms, c, duration, n) for c, n in headcounts.items()}

    def prepare(self, start: int, duration: int, headcount: int) -> str | None:
        return room_for(self._rooms, start, duration, headcount)

    def commit(self, name: str, start: int, duration: int) -> None:
        next(r for r in self._rooms if r.name == name).busy.update(range(start, start + duration))
