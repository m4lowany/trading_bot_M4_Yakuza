#!/usr/bin/env python3
"""Print setup and paper-trading analytics from logs/."""

from setup_stats import format_stats_report, generate_stats


def main():
    stats = generate_stats("logs")
    print(format_stats_report(stats))


if __name__ == "__main__":
    main()
