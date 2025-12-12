"""Fail CI if checked-in eval results differ from a fresh run (timestamp excluded)."""

import json
import sys


def load(path: str) -> dict:
    report = json.loads(open(path).read())
    report.pop("generated_at", None)
    return report


if load(sys.argv[1]) != load(sys.argv[2]):
    print("Checked-in results are stale; run `python -m masched.evals`.")
    sys.exit(1)
print("Checked-in eval results match a fresh run.")
