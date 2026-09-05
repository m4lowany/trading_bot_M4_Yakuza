#!/usr/bin/env python3
"""Validator / report for training_samples_v1.jsonl — no ML."""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from training_data import load_training_samples, training_dataset_path, validate_training_sample


def _pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 2) if d else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Training dataset V1 report")
    parser.add_argument("--path", default=training_dataset_path(REPO_ROOT))
    args = parser.parse_args()

    rows = load_training_samples(args.path)
    print(f"=== TRAINING DATASET REPORT ===")
    print(f"path: {args.path}")
    print(f"total_rows: {len(rows)}")
    if not rows:
        print("empty dataset")
        return 0

    malformed = []
    ids = []
    for i, row in enumerate(rows):
        if "_malformed_line" in row:
            malformed.append((i, ["json_decode"]))
            continue
        errs = validate_training_sample(row)
        if errs:
            malformed.append((i, errs))
        ids.append(row.get("sample_id"))

    dup_ids = [k for k, v in Counter(ids).items() if k and v > 1]
    print(f"malformed_samples: {len(malformed)}")
    if malformed[:5]:
        for i, errs in malformed[:5]:
            print(f"  row {i}: {errs}")
    print(f"duplicate_sample_ids: {len(dup_ids)}")

    valid = [r for r in rows if "_malformed_line" not in r and not validate_training_sample(r)]
    n = len(valid)
    print(f"valid_samples: {n}")

    def completeness(field: str) -> None:
        present = sum(1 for r in valid if r.get(field) is not None)
        print(f"  {field}: {present}/{n} ({_pct(present, n)}%)")

    print("\n--- field completeness (selected) ---")
    for f in [
        "sample_id",
        "label",
        "pnl_percent",
        "setup_type",
        "paper_source",
        "paper_confidence",
        "signal_confidence",
        "raw_score",
        "ma60",
        "structure_event_bos",
        "mae_percent",
        "mfe_percent",
        "duration_seconds",
    ]:
        completeness(f)

    print("\n--- distributions ---")
    print("label:", dict(Counter(r.get("label") for r in valid)))
    print("side:", dict(Counter(r.get("side") for r in valid)))
    print("setup_type:", dict(Counter(r.get("setup_type") for r in valid)))
    print("tf_alignment:", dict(Counter(r.get("tf_alignment") for r in valid)))
    print("paper_source:", dict(Counter(r.get("paper_source") for r in valid)))
    print("paper_confidence:", dict(Counter(r.get("paper_confidence") for r in valid)))

    mae_n = sum(1 for r in valid if r.get("mae_percent") is not None)
    mfe_n = sum(1 for r in valid if r.get("mfe_percent") is not None)
    print(f"\nMAE coverage: {mae_n}/{n} ({_pct(mae_n, n)}%)")
    print(f"MFE coverage: {mfe_n}/{n} ({_pct(mfe_n, n)}%)")
    print("===============================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
