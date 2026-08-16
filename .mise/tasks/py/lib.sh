# shellcheck shell=bash

function ls_scripts() {
  git ls-files --cached --others --exclude-standard '*.py'
}
