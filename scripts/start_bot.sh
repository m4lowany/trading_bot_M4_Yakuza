#!/usr/bin/env bash
# YAKUZA Runtime V1 — start paper bot (safe; refuses double-start).
set -euo pipefail

# shellcheck source=runtime_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/runtime_common.sh"

runtime_ensure_runs_dir

existing="$(runtime_find_yakuza_pids || true)"
if [[ -n "${existing}" ]]; then
  echo "YAKUZA already running"
  echo "PID(s): $(echo "${existing}" | tr '\n' ' ')"
  echo "Repo:   ${REPO_ROOT}"
  while IFS= read -r pid; do
    [[ -n "${pid}" ]] || continue
    cmd="$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null || echo '?')"
    echo "  - ${pid}: ${cmd}"
  done <<< "${existing}"
  echo "Refusing double-start. Collection continues uninterrupted."
  exit 1
fi

if [[ ! -f "${MAIN_PY}" ]]; then
  echo "ERROR: main.py not found at ${MAIN_PY}" >&2
  exit 1
fi

PY="$(runtime_python)"
# Next managed start uses Runtime V1 log (do not touch legacy live_run.log of a prior manual run).
LOG_FILE="${MANAGED_LOG}"
TS="$(date '+%Y-%m-%d %H:%M:%S')"

cd "${REPO_ROOT}"
nohup "${PY}" main.py >>"${LOG_FILE}" 2>&1 &
NEW_PID=$!
sleep 0.3

if ! runtime_is_yakuza_main "${NEW_PID}"; then
  echo "ERROR: started PID ${NEW_PID} but cmdline/cwd verification failed." >&2
  echo "Check log: ${LOG_FILE}" >&2
  exit 1
fi

echo "${NEW_PID}" >"${PID_FILE}"
echo "YAKUZA started"
echo "PID:     ${NEW_PID}"
echo "Python:  ${PY}"
echo "Log:     ${LOG_FILE}"
echo "PID file:${PID_FILE}"
echo "Started: ${TS}"
exit 0
