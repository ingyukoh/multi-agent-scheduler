"""masched CLI: list scenarios or replay one negotiation as a message transcript."""

from __future__ import annotations

import argparse
import copy

from masched.protocol import Negotiation
from masched.world import generate, label


def _fmt(m: dict, duration: int) -> str:
    b = m["body"]
    if m["type"] == "cfp":
        return f"call for proposals: {len(b['candidates'])} candidate starts"
    if m["type"] == "cfp_reply":
        free = [int(k) for k, v in b.items() if v["free"]]
        return f"free for {len(free)}/{len(b)} (reasons withheld)"
    if m["type"] == "lead_offer":
        return "offers " + ", ".join(label(c, duration) for c in b["candidates"])
    if m["type"] in ("prepare", "commit"):
        return f"{m['type']} {label(b['start'], duration)}" + (
            f" in {b['room']}" if "room" in b else ""
        )
    if m["type"] == "vote":
        return f"vote on {label(b['start'], duration)}: " + (
            "ok" if b.get("ok", b.get("room")) else "NO (conflict)"
        )
    return f"{m['type']} {b}"


def main() -> None:
    p = argparse.ArgumentParser(prog="masched")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    d = sub.add_parser("demo")
    d.add_argument("scenario", nargs="?", default="S23")
    args = p.parse_args()
    scenarios = {s.id: s for s in generate()}
    if args.cmd == "list":
        for s in scenarios.values():
            late = " late-conflict" if any(x.late_conflict for x in s.required) else ""
            print(f"{s.id}  {len(s.required)} required + {len(s.optional)} optional, "
                  f"{s.duration * 30} min{late}")  # fmt: skip
        return
    sc = scenarios[args.scenario]
    print(f"{sc.id}: {sc.duration * 30}-minute meeting")
    for x in sc.people:
        role = "required" if x in sc.required else "optional"
        print(f'  {x.name:<6} ({role}) says: "{x.preference_text()}"')
    result = Negotiation(copy.deepcopy(sc)).run()
    print(f"\nMessage bus ({len(result['bus'])} messages):")
    for m in result["bus"]:
        print(f"  {m['from']:>11} -> {m['to']:<11} {_fmt(m, sc.duration)}")
    print(f"\nOutcome: {result['outcome']}")


if __name__ == "__main__":
    main()
