#!/usr/bin/env python3
"""
Read-only historical backfill into training_samples_v1.jsonl.

Does NOT invent MAE/MFE for old trades (left null).
Does NOT modify logs/paper_trades.json or setup_history.jsonl.
"""

from __future__ import annotations

import argparse
import os
import sys

# Allow running from repo root or scripts/
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from setup_stats import _match_snapshot_for_trade, load_paper_trades, load_setup_history
from training_data import (
    append_training_sample,
    build_training_sample,
    load_training_samples,
    sample_id_exists,
    training_dataset_path,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill V1 training samples from paper history")
    parser.add_argument("--log-dir", default=os.path.join(REPO_ROOT, "logs"))
    parser.add_argument("--out", default=training_dataset_path(REPO_ROOT))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    trades = load_paper_trades(args.log_dir)
    snaps = load_setup_history(args.log_dir)
    existing = {r.get("sample_id") for r in load_training_samples(args.out) if r.get("sample_id")}

    written = 0
    skipped = 0
    for trade in trades:
        sample = build_training_sample(
            trade,
            snapshot=_match_snapshot_for_trade(trade, snaps),
            path_metrics=None,  # historical: no path → MAE/MFE null
            source="backfill_historical",
        )
        # Force path labels null for historical unless trade already has them
        if trade.get("mae_percent") is None and not trade.get("path_tracker"):
            sample["mae_percent"] = None
            sample["mfe_percent"] = None
            sample["max_adverse_price"] = None
            sample["max_favorable_price"] = None
            sample["time_to_mae_seconds"] = None
            sample["time_to_mfe_seconds"] = None
            sample["path_lowest_price"] = None
            sample["path_highest_price"] = None
            sample["path_updates"] = None

        sid = sample["sample_id"]
        if sid in existing or sample_id_exists(args.out, sid):
            skipped += 1
            continue
        if args.dry_run:
            written += 1
            continue
        append_training_sample(args.out, sample)
        existing.add(sid)
        written += 1

    print(f"backfill done: written={written} skipped_existing={skipped} out={args.out} dry_run={args.dry_run}")
    print("note: historical MAE/MFE left null (not fabricated)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
