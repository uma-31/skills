#!/usr/bin/env bash
# Called from .git/hooks/commit-msg's hook block, inserted there by
# `commit.py init` when `hook.enabled: true`. Degrades to a no-op when `uv`
# is unavailable, since a missing optional dependency should not block every
# commit in an environment this skill does not control (a GUI git client, a
# minimal PATH, ...).
set -euo pipefail

script_directory="$(cd "$(dirname "$0")" && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "commit-msg: uv not found on PATH, skipping the commit convention check" >&2
  exit 0
fi

# Run through `uv run` rather than executing commit.py directly: installers
# like `gh skill install` don't preserve its executable bit either.
exec uv run "$script_directory/commit.py" validate --from-hook --file "$1"
