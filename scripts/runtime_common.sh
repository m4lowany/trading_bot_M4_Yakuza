#!/usr/bin/env bash
# Shared helpers for YAKUZA Runtime V1 (sourced by start/stop/status/logs).
# shellcheck shell=bash

set -euo pipefail

runtime_repo_root() {
  local here
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  cd "${here}/.." && pwd
}

REPO_ROOT="$(runtime_repo_root)"
RUNS_DIR="${REPO_ROOT}/logs/runs"
PID_FILE="${RUNS_DIR}/yakuza_paper.pid"
MANAGED_LOG="${RUNS_DIR}/live_run.log"
LEGACY_LOG="${REPO_ROOT}/live_run.log"
MAIN_PY="${REPO_ROOT}/main.py"

runtime_python() {
  if [[ -x "${REPO_ROOT}/venv/bin/python" ]]; then
    echo "${REPO_ROOT}/venv/bin/python"
  elif [[ -x "${REPO_ROOT}/venv/bin/python3" ]]; then
    echo "${REPO_ROOT}/venv/bin/python3"
  else
    echo "python3"
  fi
}

# True if PID is this repo's main.py (cmdline + cwd). Never trust PID alone.
runtime_is_yakuza_main() {
  local pid="${1:-}"
  [[ -n "${pid}" && "${pid}" =~ ^[0-9]+$ ]] || return 1
  [[ -d "/proc/${pid}" ]] || return 1
  local cmdline cwd
  cmdline="$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null || true)"
  cwd="$(readlink -f "/proc/${pid}/cwd" 2>/dev/null || true)"
  [[ "${cwd}" == "${REPO_ROOT}" ]] || return 1
  # Accept "python3 main.py", "python main.py", ".../venv/bin/python main.py"
  [[ "${cmdline}" == *main.py* ]] || return 1
  return 0
}

# Print matching PIDs (one per line), empty if none.
runtime_find_yakuza_pids() {
  local pid cmdline cwd
  for pid in /proc/[0-9]*; do
    pid="${pid#/proc/}"
    [[ "${pid}" =~ ^[0-9]+$ ]] || continue
    cmdline="$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null || true)"
    [[ "${cmdline}" == *main.py* ]] || continue
    cwd="$(readlink -f "/proc/${pid}/cwd" 2>/dev/null || true)"
    [[ "${cwd}" == "${REPO_ROOT}" ]] || continue
    echo "${pid}"
  done
}

runtime_read_pidfile() {
  if [[ ! -f "${PID_FILE}" ]]; then
    return 1
  fi
  local raw
  raw="$(tr -d '[:space:]' < "${PID_FILE}" || true)"
  [[ "${raw}" =~ ^[0-9]+$ ]] || return 1
  echo "${raw}"
}

# Echo path to active run log (managed preferred if newer/nonempty, else legacy).
runtime_active_log() {
  if [[ -f "${MANAGED_LOG}" && -s "${MANAGED_LOG}" ]]; then
    if [[ -f "${LEGACY_LOG}" && -s "${LEGACY_LOG}" ]]; then
      # Prefer whichever was written more recently while a process is live.
      if [[ "${MANAGED_LOG}" -nt "${LEGACY_LOG}" ]]; then
        echo "${MANAGED_LOG}"
        return 0
      fi
      echo "${LEGACY_LOG}"
      return 0
    fi
    echo "${MANAGED_LOG}"
    return 0
  fi
  if [[ -f "${LEGACY_LOG}" ]]; then
    echo "${LEGACY_LOG}"
    return 0
  fi
  return 1
}

runtime_mtime() {
  local f="${1:-}"
  if [[ -n "${f}" && -e "${f}" ]]; then
    stat -c '%y' "${f}" 2>/dev/null || stat -f '%Sm' "${f}" 2>/dev/null || echo "unknown"
  else
    echo "(missing)"
  fi
}

runtime_last_iteration() {
  local log=""
  log="$(runtime_active_log 2>/dev/null || true)"
  if [[ -z "${log}" || ! -f "${log}" ]]; then
    if [[ -f "${REPO_ROOT}/logs/market_log.txt" ]]; then
      log="${REPO_ROOT}/logs/market_log.txt"
    else
      echo "(none)"
      return 0
    fi
  fi
  # Prefer last ITERATION line from active/run or market log.
  local line
  line="$(rg -n '\[ITERATION [0-9]+\]' "${log}" 2>/dev/null | tail -1 || true)"
  if [[ -z "${line}" ]]; then
    line="$(grep -E '\[ITERATION [0-9]+\]' "${log}" 2>/dev/null | tail -1 || true)"
  fi
  if [[ -n "${line}" ]]; then
    echo "${line}"
  else
    echo "(no ITERATION line yet)"
  fi
}

runtime_ensure_runs_dir() {
  mkdir -p "${RUNS_DIR}"
}
