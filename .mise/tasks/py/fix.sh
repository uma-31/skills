#!/usr/bin/env bash
#MISE description="Format the Python scripts and apply lint fixes"
#USAGE arg "[files]" var=#true help="Scripts to fix; all of them when omitted"
set -euo pipefail

# shellcheck source=./lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

function main() {
  local scripts=("$@")

  if [ ${#scripts[@]} -eq 0 ]; then
    local script
    while read -r script; do
      scripts+=("$script")
    done < <(ls_scripts)

    if [ ${#scripts[@]} -eq 0 ]; then
      echo "no Python scripts to fix"
      return 0
    fi
  fi

  echo "target Python scripts: ${scripts[*]}"

  echo "running ruff format..."
  ruff format "${scripts[@]}"

  echo "running ruff check --fix..."
  ruff check --fix "${scripts[@]}"

  echo "Python scripts fixed: ${#scripts[@]}"
}

main "$@"
