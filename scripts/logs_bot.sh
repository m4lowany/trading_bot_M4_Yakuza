#!/usr/bin/env bash
# YAKUZA Runtime V1 — tail active run log (Ctrl+C stops tail only, never the bot).
set -euo pipefail

# shellcheck source=runtime_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/runtime_common.sh"

LINES=50
if [[ "${1:-}" == "-n" && -n "${2:-}" ]]; then
  LINES="${2}"
elif [[ "${1:-}" =~ ^-n[0-9]+$ ]]; then
  LINES="${1#-n}"
elif [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  echo "Usage: $0 [-n LINES]"
  echo "Tails the active run log. Ctrl+C exits tail only — does not stop the bot."
  exit 0
fi

if log="$(runtime_active_log)"; then
  echo "Tailing: ${log}"
  echo "(Ctrl+C stops this tail only — bot keeps running)"
  echo "----"
  # exec replaces shell; SIGINT goes to tail, not a wrapper that might kill children oddly.
  exec tail -n "${LINES}" -f "${log}"
fi

echo "No run log found."
echo "Looked for:"
echo "  - ${MANAGED_LOG}"
echo "  - ${LEGACY_LOG}"
echo "Start the bot or create a log via ./scripts/start_bot.sh"
exit 1
