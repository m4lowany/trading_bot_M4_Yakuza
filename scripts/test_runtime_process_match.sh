#!/usr/bin/env bash
# Regression tests for Runtime V1 strict process identity matching.
# Does not start/stop the live bot.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=runtime_common.sh
source "${ROOT}/scripts/runtime_common.sh"

pass=0
fail=0

assert_match() {
  local name="$1"
  shift
  if runtime_match_bot_identity "$@"; then
    echo "PASS: ${name}"
    pass=$((pass + 1))
  else
    echo "FAIL: ${name} (expected MATCH)"
    fail=$((fail + 1))
  fi
}

assert_no_match() {
  local name="$1"
  shift
  if runtime_match_bot_identity "$@"; then
    echo "FAIL: ${name} (expected NO MATCH)"
    fail=$((fail + 1))
  else
    echo "PASS: ${name}"
    pass=$((pass + 1))
  fi
}

MAIN="${MAIN_PY}"
REPO="${REPO_ROOT}"

# --- MUST MATCH ---
assert_match "managed python3 main.py" \
  "/usr/bin/python3" "${REPO}" "python3" "main.py"

assert_match "manual venv python main.py" \
  "${REPO}/venv/bin/python" "${REPO}" "${REPO}/venv/bin/python" "main.py"

assert_match "python3 -u main.py" \
  "/usr/bin/python3" "${REPO}" "python3" "-u" "main.py"

assert_match "absolute main.py from other cwd" \
  "/usr/bin/python3" "/tmp" "python3" "${MAIN}"

# --- MUST NOT MATCH ---
assert_no_match "Cursor cursorsandbox with main.py text" \
  "/home/malowany/.cursor/cursorsandbox" "${REPO}" \
  "cursorsandbox" "--" "cd" "${REPO}" "&&" "python3" "<<" "PYEND" "main.py"

assert_no_match "bash -c string containing main.py" \
  "/bin/bash" "${REPO}" "bash" "-c" "cd ${REPO} && python3 main.py"

assert_no_match "grep main.py" \
  "/usr/bin/grep" "${REPO}" "grep" "main.py"

assert_no_match "python -c payload mentioning main.py" \
  "/usr/bin/python3" "${REPO}" "python3" "-c" "print('main.py')"

assert_no_match "python -m something" \
  "/usr/bin/python3" "${REPO}" "python3" "-m" "http.server"

assert_no_match "wrong cwd relative main.py" \
  "/usr/bin/python3" "/tmp" "python3" "main.py"

assert_no_match "unrelated python script in repo cwd" \
  "/usr/bin/python3" "${REPO}" "python3" "training_data.py"

assert_no_match "empty argv" \
  "/usr/bin/python3" "${REPO}"

assert_no_match "sh wrapper heredoc" \
  "/bin/sh" "${REPO}" "sh" "-c" "python3 <<'EOF'\nopen('main.py')\nEOF"

echo "----"
echo "Runtime match tests: pass=${pass} fail=${fail}"
if [[ "${fail}" -ne 0 ]]; then
  exit 1
fi
echo "All runtime process match tests passed."
exit 0
