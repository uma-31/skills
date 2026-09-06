# Commit message guide

Compose the commit message using both the constraints `show-rules` shows and the judgment criteria below.

## Using the command

Specify each flag as follows:

```bash
uv run scripts/commit.py create --dry-run \
  --type feat \
  --scope skills \
  --subject "add commit skill" \
  --body "Explain why the change was needed, not what the diff already shows."
```

## `type`

Follow `show-rules`'s description for what each type means. If none fits, don't substitute one with a different meaning just to have one.

## `subject`

Use the imperative mood when writing in English ("add", not "added" or "adds"). Describe the change, not the file touched: `fix(auth): reject expired tokens` beats `fix(auth): update auth.py`.

## `body`

Write why the change was made. Leave out what the diff already shows and how it was implemented.
Mention rejected alternatives or background a reviewer would otherwise have to ask about only when they matter for the reader's judgment — don't pad the body to fill these in.
Skip the body entirely for changes whose motivation is self-evident, unless `show-rules` says one is required.
Pass `--body` once per paragraph. A long body can be passed via `--body-file PATH` (`-` for stdin).
Don't start a body line with `#`: the commit-msg hook ignores such lines as comments. Put issue references in a footer instead.

## `breaking`

Pass `--breaking` when the change removes or alters existing behaviour that callers depend on, together with `--breaking-description` explaining what broke and what to do instead. The script applies whichever notation the repository requires.

## `footer`

Use `--footer "Refs: #123"` for issue references or metadata. Tokens use `-` in place of spaces (`Reviewed-by`, not `Reviewed by`).
