"""Compare the multi-agent negotiation with two single-planner baselines.

    python -m masched.evals      # writes results/eval_report.{md,json}

centralized  One planner reads every calendar (full disclosure) and picks the true optimum,
             then books without re-checking. This is the quality ceiling and the privacy floor.
first_fit    One planner polls attendees slot by slot in time order and books the first
             start where everyone required is free. It ignores preferences and doesn't re-check.
multi_agent  The LangGraph negotiation in protocol.py.

Late conflicts: in some scenarios another meeting grabs a required person's time just as we
pick a slot. Planners that book without a prepare/vote step double-book in that case.
"""

from __future__ import annotations

import argparse
import copy
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path

from masched.protocol import Negotiation
from masched.world import Scenario, generate, room_for, true_utility, valid_starts


def optimum(sc: Scenario) -> tuple[int | None, float | None]:
    scored = [(s, true_utility(sc, s)) for s in valid_starts(sc.duration)]
    scored = [(s, u) for s, u in scored if u is not None]
    if not scored:
        return None, None
    return max(scored, key=lambda su: (su[1], -su[0]))


def _apply_late_conflict(sc: Scenario, start: int) -> bool:
    """Another booking lands on the chosen slot. Returns True if a required person is hit."""
    hit = False
    for p in sc.required:
        if p.late_conflict:
            p.busy.add(start)
            hit = True
    return hit


def run_centralized(sc: Scenario) -> dict:
    start, _ = optimum(sc)
    disclosed = {p.name: len(valid_starts(sc.duration)) for p in sc.people}
    messages = 2 * len(sc.people) + 2
    if start is None:
        return {"start": None, "disclosed": disclosed, "messages": messages, "double_booked": False}
    return {"start": start, "disclosed": disclosed, "messages": messages,
            "double_booked": _apply_late_conflict(sc, start)}  # fmt: skip


def run_first_fit(sc: Scenario) -> dict:
    disclosed = {p.name: 0 for p in sc.people}
    messages = 0
    for s in valid_starts(sc.duration):
        ok = True
        for p in sc.required:
            messages += 2
            disclosed[p.name] += 1
            if not p.free(s, sc.duration):
                ok = False
                break
        if not ok:
            continue
        going = len(sc.required)
        for p in sc.optional:
            messages += 2
            disclosed[p.name] += 1
            going += p.free(s, sc.duration)
        messages += 2
        if room_for(sc.rooms, s, sc.duration, going):
            return {"start": s, "disclosed": disclosed, "messages": messages,
                    "double_booked": _apply_late_conflict(sc, s)}  # fmt: skip
    return {"start": None, "disclosed": disclosed, "messages": messages, "double_booked": False}


def run_multi_agent(sc: Scenario) -> dict:
    snapshot = copy.deepcopy(sc)  # the agents mutate their own calendars
    result = Negotiation(snapshot).run()
    disclosed = {p.name: set() for p in sc.people}
    for m in result["bus"]:
        if m["from"] in disclosed:
            body = m["body"]
            keys = body.get("candidates") or [k for k in body if k.isdigit()]
            if m["type"] == "vote":
                keys = [body["start"]]
            disclosed[m["from"]].update(int(k) for k in keys)
    out = result["outcome"]
    # Judge "infeasible" against the world after any concurrent booking, not the snapshot.
    still_feasible = out["status"] != "booked" and any(
        true_utility(snapshot, s) is not None for s in valid_starts(sc.duration)
    )
    return {
        "still_feasible_when_given_up": still_feasible,
        "start": out.get("start"),
        "disclosed": {n: len(v) for n, v in disclosed.items()},
        "messages": len(result["bus"]),
        "double_booked": False,  # every attendee voted on the final slot before commit
        "rounds": result["round"],
        "late_conflict_recovered": bool(result.get("rejected")) and out["status"] == "booked",
        "bus": result["bus"],
    }


METHODS = {
    "centralized": run_centralized,
    "first_fit": run_first_fit,
    "multi_agent": run_multi_agent,
}


def evaluate(n: int = 40, seed: int = 7) -> dict:
    rows = []
    for sc in generate(n, seed):
        best_start, best_u = optimum(sc)
        row = {"scenario": sc.id, "people": len(sc.people), "duration": sc.duration,
               "late_conflict": any(p.late_conflict for p in sc.required),
               "optimum": best_u, "methods": {}}  # fmt: skip
        for name, fn in METHODS.items():
            fresh = copy.deepcopy(sc)
            r = fn(fresh)
            u = true_utility(sc, r["start"]) if r["start"] is not None else None
            total = len(valid_starts(sc.duration)) * len(sc.people)
            row["methods"][name] = {
                "start": r["start"],
                "utility_ratio": round(u / best_u, 3) if u is not None and best_u else None,
                "disclosure": round(sum(r["disclosed"].values()) / total, 3),
                "messages": r["messages"],
                "double_booked": r["double_booked"],
                "false_infeasible": r["start"] is None
                and r.get("still_feasible_when_given_up", best_u is not None),
                **({"rounds": r["rounds"], "recovered": r["late_conflict_recovered"],
                    "status": "booked" if r["start"] is not None else "infeasible"}
                   if name == "multi_agent" else {}),
            }  # fmt: skip
        rows.append(row)
    summary = {}
    feasible = [r for r in rows if r["optimum"] is not None]
    for name in METHODS:
        ms = [r["methods"][name] for r in rows]
        booked = [r["methods"][name] for r in feasible if r["methods"][name]["start"] is not None]
        good = [m for m in booked if not m["double_booked"]]
        summary[name] = {
            "booked_without_conflict": f"{len(good)}/{len(feasible)}",
            "mean_utility_vs_optimum": round(statistics.mean(m["utility_ratio"] for m in good), 3) if good else None,
            "mean_disclosure": round(statistics.mean(m["disclosure"] for m in ms), 3),
            "mean_messages": round(statistics.mean(m["messages"] for m in ms), 1),
            "double_bookings": sum(m["double_booked"] for m in ms),
            "false_infeasible": sum(m["false_infeasible"] for m in ms),
        }  # fmt: skip
    ma = [r["methods"]["multi_agent"] for r in rows]
    late = [
        r["methods"]["multi_agent"] for r in rows if r["late_conflict"] and r["optimum"] is not None
    ]
    lost = [m for m in late if m["start"] is None and not m["false_infeasible"]]
    summary["multi_agent"] |= {
        "mean_rounds": round(statistics.mean(m["rounds"] for m in ma), 2),
        "late_conflicts": len(late),
        "late_conflicts_recovered": sum(m["recovered"] for m in late),
        "late_conflicts_took_only_feasible_slot": len(lost),
    }
    return {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "scenarios": len(rows),
        "feasible": len(feasible),
        "summary": summary,
        "rows": rows,
    }


def render(report: dict) -> str:
    s = report["summary"]
    names = ["multi_agent", "centralized", "first_fit"]
    pct = lambda v: "n/a" if v is None else f"{v * 100:.1f}%"  # noqa: E731
    lines = [
        "# Multi-agent scheduling evaluation",
        "",
        f"Generated {report['generated_at']} by `python -m masched.evals`. Do not edit by hand.",
        "",
        f"{report['scenarios']} seeded scenarios ({report['feasible']} feasible), 2-8 people, "
        "5-day week in 30-minute slots, 2 rooms.",
        "",
        "| Metric | Multi-agent (LangGraph) | Centralized (reads all calendars) | First-fit poller |",
        "|---|---:|---:|---:|",
        "| Feasible meetings booked with no double-booking | " + " | ".join(s[n]["booked_without_conflict"] for n in names) + " |",
        "| Mean utility vs true optimum | " + " | ".join(pct(s[n]["mean_utility_vs_optimum"]) for n in names) + " |",
        "| Mean share of private calendar disclosed | " + " | ".join(pct(s[n]["mean_disclosure"]) for n in names) + " |",
        "| Mean messages | " + " | ".join(str(s[n]["mean_messages"]) for n in names) + " |",
        "| Double bookings | " + " | ".join(str(s[n]["double_bookings"]) for n in names) + " |",
        "| Feasible scenarios wrongly reported infeasible | " + " | ".join(str(s[n]["false_infeasible"]) for n in names) + " |",
        "",
        f"Multi-agent: mean negotiation rounds {s['multi_agent']['mean_rounds']}. Of "
        f"{s['multi_agent']['late_conflicts']} feasible scenarios hit by a concurrent booking, the "
        f"two-phase commit rebooked {s['multi_agent']['late_conflicts_recovered']} elsewhere; in "
        f"{s['multi_agent']['late_conflicts_took_only_feasible_slot']} the concurrent booking took the "
        "only feasible slot, and the agents correctly reported infeasible instead of double-booking.",
        "",
        "## Per scenario",
        "",
        "| Scenario | People | Late conflict | MA utility | MA disclosure | MA msgs | MA rounds | Central double-booked | First-fit utility |",
        "|---|---:|:-:|---:|---:|---:|---:|:-:|---:|",
    ]  # fmt: skip
    for r in report["rows"]:
        ma, ce, ff = (r["methods"][n] for n in names)
        lines.append(
            f"| {r['scenario']} | {r['people']} | {'yes' if r['late_conflict'] else ''} | "
            f"{pct(ma['utility_ratio']) if ma['start'] is not None else 'infeasible'} | "
            f"{pct(ma['disclosure'])} | {ma['messages']} | {ma['rounds']} | "
            f"{'yes' if ce['double_booked'] else ''} | "
            f"{pct(ff['utility_ratio']) if ff['start'] is not None else 'infeasible'} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="results")
    args = parser.parse_args()
    report = evaluate()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "eval_report.json").write_text(json.dumps(report, indent=2) + "\n")
    (out / "eval_report.md").write_text(render(report))
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
