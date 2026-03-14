#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

find_python() {
  local candidate
  for candidate in python3.13 python3.12 python3.11; do
    if command -v "$candidate" >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

pause_on_exit() {
  printf '\nPress Enter to close this window...'
  read -r _
}

PYTHON_BIN="$(find_python)"
if [[ -z "$PYTHON_BIN" ]]; then
  printf 'No supported Python interpreter was found.\n'
  printf 'Install Python 3.11, 3.12, or 3.13, then try again.\n'
  pause_on_exit
  exit 1
fi

printf 'Using %s\n' "$PYTHON_BIN"
printf 'Building distribution...\n'
"$PYTHON_BIN" resources/scripts/build_distribution.py "$@"
build_status=$?
if (( build_status != 0 )); then
  printf '\nBuild failed with exit code %d.\n' "$build_status"
  pause_on_exit
  exit "$build_status"
fi

printf '\nStaging distribution...\n'
"$PYTHON_BIN" resources/scripts/stage_distribution.py
stage_status=$?
if (( stage_status != 0 )); then
  printf '\nStaging failed with exit code %d.\n' "$stage_status"
  pause_on_exit
  exit "$stage_status"
fi

printf '\nBuild complete. Output is in distribution/.\n'
pause_on_exit
