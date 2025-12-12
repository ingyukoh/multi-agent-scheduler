# Multi-Agent Scheduler

**Agents that book a meeting without sharing their calendars.** Each person has their own agent that holds their private calendar and preferences. A room agent manages rooms. A coordinator agent runs the negotiation over a message bus and never sees a calendar. It's built on LangGraph and measured against two single-planner baselines.

[![CI](https://github.com/ingyukoh/multi-agent-scheduler/actions/workflows/ci.yml/badge.svg)](https://github.com/ingyukoh/multi-agent-scheduler/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

The classic reason to build a *multi*-agent system is information that is private and spread across parties. No single planner should be able to read it all, yet the parties still need a joint decision. Scheduling makes this concrete:

- Nobody wants to hand their whole calendar to a bot.
- Calendars change while you negotiate.
- A naive planner that books from a stale snapshot double-books people.

## Measured result

40 seeded scenarios (26 feasible), 2-8 people, a 5-day week in 30-minute slots, and 2 rooms:

| Metric | Multi-agent (LangGraph) | Centralized (reads all calendars) | First-fit poller |
|---|---:|---:|---:|
| Feasible meetings booked with no double-booking | **22/26** | 17/26 | 17/26 |
| Mean utility vs true optimum | 90.8% | 100.0% | 83.1% |
| Mean share of private calendar disclosed | 41.8% | 100.0% | 15.3% |
| Mean messages | 61.0 | 11.6 | 110.8 |
| Double bookings | **0** | 9 | 9 |
| Feasible scenarios wrongly reported infeasible | 0 | 0 | 0 |

In 9 feasible scenarios, another meeting grabbed a required person's time just as a slot was chosen (a "late conflict"):
- The multi-agent two-phase commit caught all 9. It rebooked 5 elsewhere.
- In the other 4, the concurrent booking had taken the only feasible slot, so the agents correctly reported the meeting infeasible. Both baselines double-booked those.

This explains 22/26: every meeting that was still achievable got booked.

Numbers come from `python -m masched.evals` ([report](results/eval_report.md), [JSON](results/eval_report.json)). CI re-runs it and fails if they are stale.

**How to read it honestly:**
- The centralized planner finds the best slot, but only by reading 100% of everyone's calendar.
- First-fit reveals less, but costs about 2x the messages and ignores preferences.
- Neither baseline re-checks before booking.
- The multi-agent protocol sits between them on quality and disclosure, and is the only one that never double-books.
- Its disclosure is highest in *infeasible* cases, because proving "no slot exists" requires checking every slot some required person could attend.
- The scenarios are synthetic and seeded.

## The agents and the protocol

```mermaid
sequenceDiagram
    participant C as Coordinator (no calendars)
    participant P as Person agents (private calendar + preferences)
    participant R as Room agent (private room calendars)
    C->>P: call for proposals: candidate starts (sent in parallel)
    P-->>C: free / busy + coarse preference 0-2 (no reasons)
    C->>R: headcount for each start where every required person is free
    R-->>C: room or none
    alt nothing feasible
        C->>P: most-constrained required agent: "lead"
        P-->>C: a page of its own unchecked free starts
        Note over C,P: repeat; if a required agent has no unchecked free start left, the meeting is provably infeasible
    end
    C->>P: prepare(best start)
    P-->>C: vote ok / NO (calendar changed meanwhile)
    alt any required NO
        C->>C: reject that start, try the next best
    else all ok
        C->>P: commit
        C->>R: commit
    end
```

| Multi-agent concern | How it is handled | Code |
|---|---|---|
| Private state | Calendars live inside `ParticipantAgent` and `RoomAgent` objects. Graph state holds only the message bus and what agents chose to reply, and a test asserts no calendar data reaches it | [`agents.py`](src/masched/agents.py) |
| Parallel agents | The coordinator's call for proposals fans out with LangGraph `Send`, and all person agents answer in one superstep | [`protocol.py`](src/masched/protocol.py) `fan_out` |
| Minimal disclosure | Replies are free/busy per candidate plus a 0/1/2 preference bucket, never reasons ("focus time", "avoid Friday") | `ParticipantAgent.answer_cfp` |
| Role switching | When the coordinator's guesses fail, the most constrained required agent *leads* by offering its own free starts, taking turns with the others | `lead`, `_next_lead` |
| Completeness | The protocol stops only when it books, or when a required agent has no unchecked free start left, which proves infeasibility. The eval shows 0 false "infeasible" answers | `route_lead`, `give_up` |
| Concurrency | Two-phase commit: every attendee and the room vote on the final slot before anyone books it | `prepare` |
| Natural-language intake | Each agent reads its owner's stated preferences ("I prefer mornings; please avoid Wed"). It's rule-based by default; with `MASCHED_LLM=anthropic`, Claude extracts them with structured output | `parse_preferences` |

## Try it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
masched list
masched demo S23        # full message transcript: offers, a late-conflict "NO" vote, rebooking
pytest -q
python -m masched.evals # regenerates results/
```

An excerpt of `masched demo S23`:

```
          Fay -> coordinator free for 3/10 (reasons withheld)
  coordinator -> Fay         lead_request {'already_checked': 10}
          Fay -> coordinator offers Mon 09:00-10:30, Mon 09:30-11:00, ...
  coordinator -> Fay         prepare Tue 09:00-10:30
          Fay -> coordinator vote on Tue 09:00-10:30: NO (conflict)
  coordinator -> Fay         prepare Tue 12:30-14:00
          Fay -> coordinator vote on Tue 12:30-14:00: ok
```

## Known limitations

- The agents' negotiation policies are deterministic and hand-designed, so privacy, optimality and completeness can be measured exactly. The LLM is used only for natural-language preference intake, and that Claude path is not covered by the checked-in results.
- Disclosure is counted as the share of (person, candidate start) facts revealed. It doesn't model what an observer could infer across many meetings.
- Only one meeting is negotiated at a time. Concurrency is simulated as one competing booking per affected scenario.
