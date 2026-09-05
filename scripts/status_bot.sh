#!/usr/bin/env bash
# YAKUZA Runtime V1 — concise operational status.
set -euo pipefail

# shellcheck source=runtime_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/runtime_common.sh"

pids="$(runtime_find_yakuza_pids || true)"
file_pid="$(runtime_read_pidfile || true)"
pf_status="$(runtime_pidfile_status)"

echo "=== YAKUZA Runtime V1 status ==="
echo "Repo: ${REPO_ROOT}"

if [[ -n "${pids}" ]]; then
  # WAIT / NO_SETUP is normal — not an error.
  echo "Note: WAIT / NO_SETUP means runtime is healthy but no paper trade — not an error."
  managed=0
  while IFS= read -r pid; do
    [[ -n "${pid}" ]] || continue
    cmd="$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null || echo '?')"
    exe="$(readlink -f "/proc/${pid}/exe" 2>/dev/null || echo '?')"
    etime="$(ps -p "${pid}" -o etime= 2>/dev/null | tr -d ' ' || echo '?')"
    if [[ -n "${file_pid}" && "${file_pid}" == "${pid}" && "${pf_status}" == "VALID_MANAGED" ]]; then
      echo "State: RUNNING_MANAGED"
      managed=1
      echo "PID:     ${pid}"
      echo "Uptime:  ${etime}"
      echo "Exe:     ${exe}"
      echo "Command: ${cmd}"
      echo "PID file: ${PID_FILE} (matches verified process)"
    else
      echo "State: RUNNING_MANUAL"
      echo "PID:     ${pid}"
      echo "Uptime:  ${etime}"
      echo "Exe:     ${exe}"
      echo "Command: ${cmd}"
      if [[ -n "${file_pid}" ]]; then
        echo "PID file: ${PID_FILE} -> ${file_pid} (${pf_status})"
      else
        echo "PID file: (none — manual start)"
      fi
    fi
  done <<< "${pids}"
else
  case "${pf_status}" in
    STALE_GONE|STALE_INVALID)
      echo "State: STALE_PID"
      echo "PID file: ${PID_FILE} -> ${file_pid} (${pf_status})"
      if [[ "${pf_status}" == "STALE_INVALID" && -d "/proc/${file_pid}" ]]; then
        echo "  live exe:     $(readlink -f "/proc/${file_pid}/exe" 2>/dev/null || echo '?')"
        echo "  live cmdline: $(tr '\0' ' ' < "/proc/${file_pid}/cmdline" 2>/dev/null || echo '?')"
        echo "  live cwd:     $(readlink -f "/proc/${file_pid}/cwd" 2>/dev/null || echo '?')"
        echo "  Not a verified YAKUZA python main.py — will not be treated as RUNNING."
      fi
      ;;
    *)
      echo "State: STOPPED"
      echo "PID file: (none)"
      ;;
  esac
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
