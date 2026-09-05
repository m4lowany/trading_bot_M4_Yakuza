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

# True if basename looks like a Python interpreter (python, python3, python3.12, ...).
runtime_is_python_basename() {
  local base="${1:-}"
  [[ "${base}" =~ ^python([0-9]+(\.[0-9]+)*)?$ ]]
}

# Resolve script path relative to cwd (absolute paths unchanged).
runtime_resolve_script() {
  local cwd="${1:-}"
  local script="${2:-}"
  if [[ -z "${script}" ]]; then
    return 1
  fi
  if [[ "${script}" == /* ]]; then
    readlink -f "${script}" 2>/dev/null || echo "${script}"
    return 0
  fi
  if [[ -n "${cwd}" && -d "${cwd}" ]]; then
    readlink -f "${cwd}/${script}" 2>/dev/null || echo "${cwd}/${script}"
    return 0
  fi
  return 1
}

# Core identity check — pure inputs (testable without /proc).
# Args: exe_path cwd argv0 [argv1 ...]
# MATCH only if:
#   - exe basename is python/python3/pythonX.Y
#   - a real script argument is main.py (not -c payload / shell string)
#   - resolved script path equals this repo's MAIN_PY
runtime_match_bot_identity() {
  local exe="${1:-}"
  local cwd="${2:-}"
  shift 2 || true
  local -a argv=("$@")

  local base
  base="$(basename "${exe}" 2>/dev/null || echo "")"
  runtime_is_python_basename "${base}" || return 1

  if [[ ${#argv[@]} -eq 0 ]]; then
    return 1
  fi

  local i=1
  local arg
  # Skip argv[0] (interpreter). Walk flags until first non-option = script.
  while [[ ${i} -lt ${#argv[@]} ]]; do
    arg="${argv[$i]}"
    if [[ "${arg}" == "-c" || "${arg}" == "-m" ]]; then
      # -c/-m means not executing main.py as a file script.
      return 1
    fi
    if [[ "${arg}" == "--" ]]; then
      i=$((i + 1))
      break
    fi
    if [[ "${arg}" == -* ]]; then
      # Common interpreter flags: -u -O -B -S -I -E -X...
      i=$((i + 1))
      continue
    fi
    break
  done

  if [[ ${i} -ge ${#argv[@]} ]]; then
    return 1
  fi

  arg="${argv[$i]}"
  # Require script token to be main.py or */main.py (not a larger string).
  if [[ "${arg}" != "main.py" && "${arg}" != */main.py ]]; then
    return 1
  fi

  local resolved
  resolved="$(runtime_resolve_script "${cwd}" "${arg}")" || return 1
  [[ "${resolved}" == "${MAIN_PY}" ]] || return 1
  return 0
}

# Read /proc identity and validate. Never trust PID alone or substring grep.
runtime_is_yakuza_main() {
  local pid="${1:-}"
  [[ -n "${pid}" && "${pid}" =~ ^[0-9]+$ ]] || return 1
  [[ -d "/proc/${pid}" ]] || return 1
  [[ -r "/proc/${pid}/cmdline" ]] || return 1

  local exe cwd
  exe="$(readlink -f "/proc/${pid}/exe" 2>/dev/null || true)"
  cwd="$(readlink -f "/proc/${pid}/cwd" 2>/dev/null || true)"
  [[ -n "${exe}" ]] || return 1

  local -a argv=()
  # mapfile -d '' reads NUL-separated cmdline into argv entries.
  if ! mapfile -d '' -t argv < "/proc/${pid}/cmdline" 2>/dev/null; then
    return 1
  fi
  # Drop empty trailing element some bash versions append.
  if [[ ${#argv[@]} -gt 0 && -z "${argv[-1]:-}" ]]; then
    unset 'argv[-1]'
  fi
  [[ ${#argv[@]} -gt 0 ]] || return 1

  runtime_match_bot_identity "${exe}" "${cwd}" "${argv[@]}"
}

# Print matching PIDs (one per line), empty if none. Strict identity only.
runtime_find_yakuza_pids() {
  local pid
  for pid in /proc/[0-9]*; do
    pid="${pid#/proc/}"
    [[ "${pid}" =~ ^[0-9]+$ ]] || continue
    if runtime_is_yakuza_main "${pid}"; then
      echo "${pid}"
    fi
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

# Classify PID file vs live identity.
# Prints one of: MISSING | VALID_MANAGED | STALE_GONE | STALE_INVALID
runtime_pidfile_status() {
  local file_pid
  file_pid="$(runtime_read_pidfile || true)"
  if [[ -z "${file_pid}" ]]; then
    echo "MISSING"
    return 0
  fi
  if ! [[ -d "/proc/${file_pid}" ]]; then
    echo "STALE_GONE"
    return 0
  fi
  if runtime_is_yakuza_main "${file_pid}"; then
    echo "VALID_MANAGED"
    return 0
  fi
  echo "STALE_INVALID"
  return 0
}

# Echo path to active run log (managed preferred if newer/nonempty, else legacy).
runtime_active_log() {
  if [[ -f "${MANAGED_LOG}" && -s "${MANAGED_LOG}" ]]; then
    if [[ -f "${LEGACY_LOG}" && -s "${LEGACY_LOG}" ]]; then
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
