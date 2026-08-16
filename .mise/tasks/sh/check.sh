#!/usr/bin/env bash
#MISE description="Verify formatting and lint of the shell scripts without changing any file"
#USAGE arg "[files]" var=#true help="Scripts to check; all of them when omitted"
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
      echo "no shell scripts to check"
      return 0
    fi
  fi

  echo "target shell scripts: ${scripts[*]}"

  echo "running shfmt..."
  shfmt --indent 2 --diff "${scripts[@]}"

  echo "running shellcheck..."
  shellcheck --external-sources --source-path=SCRIPTDIR "${scripts[@]}"

  echo "shell scripts checked: ${#scripts[@]}"
}

main "$@"
