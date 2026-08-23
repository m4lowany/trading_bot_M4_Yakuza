#!/usr/bin/env bash
# YAKUZA Runtime V1 — stop paper bot (verify before kill; never blind PID kill).
set -euo pipefail

# shellcheck source=runtime_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/runtime_common.sh"

FORCE_MANUAL=0
DRY_RUN=0
for arg in "$@"; do
  case "${arg}" in
    --force) FORCE_MANUAL=1 ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      echo "Usage: $0 [--dry-run] [--force]"
      echo "  Default: stop only if PID file is valid and process matches this repo main.py."
      echo "  --force   allow stop of verified repo main.py when PID file missing/stale (manual start)."
      echo "  --dry-run show what would be stopped; do not send signals."
      exit 0
      ;;
    *)
      echo "Unknown arg: ${arg}" >&2
      exit 2
      ;;
  esac
done

TARGET_PID=""
SOURCE=""

file_pid="$(runtime_read_pidfile || true)"
if [[ -n "${file_pid}" ]]; then
  if runtime_is_yakuza_main "${file_pid}"; then
    TARGET_PID="${file_pid}"
    SOURCE="pidfile"
  else
    echo "Stale or mismatched PID file: ${PID_FILE} -> ${file_pid}"
    if [[ -d "/proc/${file_pid}" ]]; then
      echo "  live cmdline: $(tr '\0' ' ' < "/proc/${file_pid}/cmdline" 2>/dev/null || echo '?')"
      echo "  live cwd:     $(readlink -f "/proc/${file_pid}/cwd" 2>/dev/null || echo '?')"
      echo "  Refusing to kill — does not verify as this repo main.py."
    else
      echo "  Process not running. Removing stale PID file."
      if [[ "${DRY_RUN}" -eq 0 ]]; then
        rm -f "${PID_FILE}"
      else
        echo "  [dry-run] would remove ${PID_FILE}"
      fi
    fi
  fi
fi

if [[ -z "${TARGET_PID}" ]]; then
  matches="$(runtime_find_yakuza_pids || true)"
  if [[ -z "${matches}" ]]; then
    echo "YAKUZA stopped (no matching main.py in ${REPO_ROOT})"
    exit 0
  fi
  echo "No valid Runtime V1 PID file for a live process."
  echo "Detected matching main.py process(es) in this repo:"
  while IFS= read -r pid; do
    [[ -n "${pid}" ]] || continue
    echo "  PID ${pid}: $(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null || echo '?')"
  done <<< "${matches}"
  count="$(echo "${matches}" | grep -c . || true)"
  if [[ "${FORCE_MANUAL}" -ne 1 ]]; then
    echo "Refusing automatic stop of manually started process."
    echo "Re-run with --force to stop a single verified match, or stop after a managed start (PID file)."
    exit 1
  fi
  if [[ "${count}" -ne 1 ]]; then
    echo "ERROR: --force requires exactly one matching process (found ${count})." >&2
    exit 1
  fi
  TARGET_PID="$(echo "${matches}" | head -1)"
  SOURCE="manual-force"
fi

if ! runtime_is_yakuza_main "${TARGET_PID}"; then
  echo "ERROR: final verification failed for PID ${TARGET_PID}. Abort." >&2
  exit 1
fi

cmd="$(tr '\0' ' ' < "/proc/${TARGET_PID}/cmdline" 2>/dev/null || echo '?')"
echo "Stop target: PID ${TARGET_PID} (${SOURCE})"
echo "Command:     ${cmd}"
echo "Repo:        ${REPO_ROOT}"

if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "[dry-run] would SIGTERM then wait, SIGKILL if needed. No signals sent."
  exit 0
fi

kill -TERM "${TARGET_PID}" 2>/dev/null || true
for _ in $(seq 1 20); do
  if ! kill -0 "${TARGET_PID}" 2>/dev/null; then
    break
  fi
  sleep 0.25
done

if kill -0 "${TARGET_PID}" 2>/dev/null; then
  echo "Still running after SIGTERM timeout — sending SIGKILL"
  if runtime_is_yakuza_main "${TARGET_PID}"; then
    kill -KILL "${TARGET_PID}" 2>/dev/null || true
    sleep 0.2
  else
    echo "ERROR: PID changed identity before SIGKILL. Abort." >&2
    exit 1
  fi
fi

if kill -0 "${TARGET_PID}" 2>/dev/null; then
  echo "ERROR: process ${TARGET_PID} still alive." >&2
  exit 1
fi

rm -f "${PID_FILE}"
echo "YAKUZA stopped (PID ${TARGET_PID})"
exit 0
