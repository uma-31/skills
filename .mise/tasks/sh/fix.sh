#!/usr/bin/env bash
#MISE description="Format the shell scripts"
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
      echo "no shell scripts to format"
      return 0
    fi
  fi

  echo "target shell scripts: ${scripts[*]}"

  echo "running shfmt..."
  shfmt --indent 2 --write "${scripts[@]}"

  echo "shell scripts formatted: ${#scripts[@]}"
}

main "$@"
