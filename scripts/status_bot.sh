#!/usr/bin/env bash
# YAKUZA Runtime V1 — concise operational status.
set -euo pipefail

# shellcheck source=runtime_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/runtime_common.sh"

pids="$(runtime_find_yakuza_pids || true)"
file_pid="$(runtime_read_pidfile || true)"

echo "=== YAKUZA Runtime V1 status ==="
echo "Repo: ${REPO_ROOT}"

if [[ -n "${pids}" ]]; then
  echo "State: RUNNING"
  # WAIT / NO_SETUP is normal — not an error.
  echo "Note: WAIT / NO_SETUP means runtime is healthy but no paper trade — not an error."
  while IFS= read -r pid; do
    [[ -n "${pid}" ]] || continue
    cmd="$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null || echo '?')"
    etime="$(ps -p "${pid}" -o etime= 2>/dev/null | tr -d ' ' || echo '?')"
    echo "PID:     ${pid}"
    echo "Uptime:  ${etime}"
    echo "Command: ${cmd}"
    if [[ -n "${file_pid}" && "${file_pid}" == "${pid}" ]]; then
      echo "PID file: ${PID_FILE} (matches)"
    elif [[ -n "${file_pid}" ]]; then
      echo "PID file: ${PID_FILE} -> ${file_pid} (mismatch / stale vs live)"
    else
      echo "PID file: (none — likely manual start)"
    fi
  done <<< "${pids}"
else
  echo "State: STOPPED"
  if [[ -n "${file_pid}" ]]; then
    if [[ -d "/proc/${file_pid}" ]]; then
      echo "PID file: ${PID_FILE} -> ${file_pid} (LIVE but NOT verified as this repo main.py — stale risk)"
    else
      echo "PID file: ${PID_FILE} -> ${file_pid} (stale — process gone)"
    fi
  else
    echo "PID file: (none)"
  fi
fi

echo "---"
active="$(runtime_active_log 2>/dev/null || true)"
if [[ -n "${active}" ]]; then
  echo "Active log: ${active}"
  echo "Log mtime:  $(runtime_mtime "${active}")"
else
  echo "Active log: (none)"
fi
echo "Managed log:${MANAGED_LOG} mtime=$(runtime_mtime "${MANAGED_LOG}")"
echo "Legacy log: ${LEGACY_LOG} mtime=$(runtime_mtime "${LEGACY_LOG}")"
echo "market_log: $(runtime_mtime "${REPO_ROOT}/logs/market_log.txt")"
echo "setup_hist: $(runtime_mtime "${REPO_ROOT}/logs/setup_history.jsonl")"
echo "paper_trds: $(runtime_mtime "${REPO_ROOT}/logs/paper_trades.json")"
echo "---"
echo "Newest iteration:"
runtime_last_iteration
echo "==============================="
exit 0
