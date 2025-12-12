# Multi-agent scheduling evaluation

Generated 2026-09-25 23:24 UTC by `python -m masched.evals`. Do not edit by hand.

40 seeded scenarios (26 feasible), 2-8 people, 5-day week in 30-minute slots, 2 rooms.

| Metric | Multi-agent (LangGraph) | Centralized (reads all calendars) | First-fit poller |
|---|---:|---:|---:|
| Feasible meetings booked with no double-booking | 22/26 | 17/26 | 17/26 |
| Mean utility vs true optimum | 90.8% | 100.0% | 83.1% |
| Mean share of private calendar disclosed | 41.8% | 100.0% | 15.3% |
| Mean messages | 61.0 | 11.6 | 110.8 |
| Double bookings | 0 | 9 | 9 |
| Feasible scenarios wrongly reported infeasible | 0 | 0 | 0 |

Multi-agent: mean negotiation rounds 4.7. Of 9 feasible scenarios hit by a concurrent booking, the two-phase commit rebooked 5 elsewhere; in 4 the concurrent booking took the only feasible slot, and the agents correctly reported infeasible instead of double-booking.

## Per scenario

| Scenario | People | Late conflict | MA utility | MA disclosure | MA msgs | MA rounds | Central double-booked | First-fit utility |
|---|---:|:-:|---:|---:|---:|---:|:-:|---:|
| S01 | 5 |  | infeasible | 53.3% | 72 | 7 |  | infeasible |
| S02 | 5 | yes | 70.6% | 22.5% | 49 | 2 | yes | 64.7% |
| S03 | 4 |  | infeasible | 22.9% | 40 | 5 |  | infeasible |
| S04 | 4 |  | 100.0% | 45.3% | 55 | 4 |  | 100.0% |
| S05 | 6 | yes | infeasible | 14.3% | 14 | 2 |  | infeasible |
| S06 | 5 |  | 100.0% | 22.5% | 42 | 2 |  | 100.0% |
| S07 | 2 |  | 100.0% | 24.0% | 21 | 2 |  | 57.1% |
| S08 | 5 |  | 100.0% | 24.0% | 42 | 2 |  | 43.8% |
| S09 | 7 |  | infeasible | 27.1% | 64 | 5 |  | infeasible |
| S10 | 2 | yes | 100.0% | 22.5% | 25 | 2 | yes | 100.0% |
| S11 | 3 |  | 100.0% | 61.3% | 58 | 6 |  | 100.0% |
| S12 | 5 |  | 56.2% | 32.5% | 46 | 3 |  | 56.2% |
| S13 | 5 |  | 100.0% | 34.7% | 49 | 3 |  | 100.0% |
| S14 | 3 |  | 100.0% | 25.7% | 28 | 2 |  | 50.0% |
| S15 | 6 |  | 75.0% | 32.5% | 55 | 3 |  | 75.0% |
| S16 | 3 |  | infeasible | 51.4% | 40 | 6 |  | infeasible |
| S17 | 3 |  | 100.0% | 34.7% | 38 | 3 |  | 100.0% |
| S18 | 5 | yes | infeasible | 78.7% | 118 | 10 | yes | 100.0% |
| S19 | 5 |  | 100.0% | 24.0% | 36 | 2 |  | 54.5% |
| S20 | 4 |  | 100.0% | 45.3% | 53 | 4 |  | 100.0% |
| S21 | 6 |  | infeasible | 22.9% | 56 | 5 |  | infeasible |
| S22 | 2 |  | 100.0% | 52.0% | 39 | 5 |  | 100.0% |
| S23 | 5 | yes | 46.2% | 37.1% | 55 | 3 | yes | 100.0% |
| S24 | 5 |  | infeasible | 45.7% | 48 | 5 |  | infeasible |
| S25 | 4 | yes | 75.0% | 24.0% | 40 | 2 | yes | 83.3% |
| S26 | 4 | yes | infeasible | 31.4% | 30 | 4 |  | infeasible |
| S27 | 5 | yes | infeasible | 70.7% | 96 | 8 | yes | 100.0% |
| S28 | 5 |  | infeasible | 72.0% | 96 | 9 |  | infeasible |
| S29 | 2 |  | 100.0% | 22.5% | 21 | 2 |  | 100.0% |
| S30 | 8 |  | infeasible | 73.3% | 144 | 9 |  | infeasible |
| S31 | 5 | yes | infeasible | 83.8% | 132 | 12 |  | infeasible |
| S32 | 7 |  | infeasible | 91.2% | 162 | 11 |  | infeasible |
| S33 | 7 | yes | infeasible | 88.0% | 142 | 9 | yes | 100.0% |
| S34 | 6 | yes | infeasible | 28.0% | 50 | 4 | yes | 100.0% |
| S35 | 7 |  | 100.0% | 45.3% | 85 | 4 |  | 100.0% |
| S36 | 4 |  | 92.3% | 24.0% | 35 | 2 |  | 76.9% |
| S37 | 7 |  | infeasible | 48.0% | 96 | 7 |  | infeasible |
| S38 | 5 |  | infeasible | 50.0% | 60 | 6 |  | infeasible |
| S39 | 5 | yes | 83.3% | 32.5% | 61 | 3 | yes | 83.3% |
| S40 | 5 |  | 100.0% | 31.4% | 46 | 3 |  | 100.0% |
