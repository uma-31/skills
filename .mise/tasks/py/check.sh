#!/usr/bin/env bash
#MISE description="Verify formatting, lint and types of the Python scripts without changing any file"
#USAGE arg "[files]" var=#true help="Scripts to check; all of them when omitted"
set -euo pipefail

# shellcheck source=./lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

function check_by_basedpyright() {
  local script
  for script in "$@"; do
    echo "type-checking $script..."
    uv sync --quiet --script "$script"
    basedpyright --pythonpath "$(uv python find --script "$script")" "$script"
  done
}

function main() {
  local scripts=("$@")

  if [ ${#scripts[@]} -eq 0 ]; then
    local script
    while read -r script; do
      scripts+=("$script")
    done < <(ls_scripts)

    if [ ${#scripts[@]} -eq 0 ]; then
      echo "no Python scripts to check"
      return 0
    fi
  fi

  echo "target Python scripts: ${scripts[*]}"

  echo "running ruff format..."
  ruff format --check "${scripts[@]}"

  echo "running ruff check..."
  ruff check "${scripts[@]}"

  check_by_basedpyright "${scripts[@]}"

  echo "Python scripts checked: ${#scripts[@]}"
}

main "$@"
