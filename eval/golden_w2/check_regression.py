"""PR-blocking regression gate for the Week 2 golden eval.

Reads `baseline.json` (committed pass-rates) and the current run's
pass-rates, then fails if ANY category:
  - drops by more than `--max-drop` percentage points (default 5pt), OR
  - falls below `--min-pass` absolute (default 80%).

Exit code 1 on regression, 0 on pass. Designed to be the failing step
of the `golden-w2` CI job — when it exits non-zero, ci-success goes
red, the deploy gate stays closed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow `python eval/golden_w2/check_regression.py` from project root
# without needing PYTHONPATH set externally.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from eval.golden_w2.rubric import aggregate_pass_rates  # noqa: E402
from eval.golden_w2.runner import BASELINE_PATH, run  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--baseline",
        default=str(BASELINE_PATH),
        help="Path to baseline.json (default: committed baseline)",
    )
    parser.add_argument(
        "--max-drop",
        type=float,
        default=0.05,
        help="Max allowed drop in pass-rate per category (default 0.05 = 5pt)",
    )
    parser.add_argument(
        "--min-pass",
        type=float,
        default=0.80,
        help="Minimum absolute pass-rate per category (default 0.80)",
    )
    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    if not baseline_path.is_file():
        print(f"baseline file not found: {baseline_path}", file=sys.stderr)
        return 2
    baseline = json.loads(baseline_path.read_text())

    print(f"Running 50-case golden suite against baseline {baseline_path.name}...")
    scores = run()
    rates = aggregate_pass_rates(scores)

    print()
    print(f"{'Category':<24} {'Baseline':>10} {'Current':>10} {'Delta':>10}")
    print("-" * 58)
    failures: list[str] = []
    for cat, current in rates.items():
        if cat.startswith("_"):
            continue
        base = baseline.get(cat)
        if base is None:
            print(f"  {cat:<22} {'(new)':>10} {current:>10.3f}    -")
            continue
        delta = current - base
        marker = "  "
        if current < args.min_pass:
            marker = "X "
            failures.append(
                f"{cat}: {current:.1%} below absolute floor {args.min_pass:.0%}"
            )
        elif delta < -args.max_drop:
            marker = "X "
            failures.append(
                f"{cat}: dropped {(-delta):.1%} (> {args.max_drop:.0%} max)"
            )
        print(f"{marker}{cat:<22} {base:>10.3f} {current:>10.3f} {delta:>+10.3f}")

    print()
    if failures:
        print("REGRESSION DETECTED. Eval gate is BLOCKING this PR:")
        for f in failures:
            print(f"  - {f}")
        print()
        print(
            "Investigate the agent change in this PR. If the new pass-rate "
            "is intentional (a real improvement OR an accepted tradeoff), "
            "update baseline.json and re-commit."
        )
        return 1

    print("All categories within tolerance. Eval gate is OPEN.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
