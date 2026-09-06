---
name: commit
description: Creates commit messages that follow the repository's commit convention, based on Conventional Commits v1.0.0. Use before running `git commit` (including `--amend`) in any repository, or whenever asked to write or fix a commit message.
---

# Commit

Create commits that follow [Conventional Commits v1.0.0](https://www.conventionalcommits.org/en/v1.0.0/), according to the rules defined in the repository's own configuration file.

If asked to initialize the commit convention or create the configuration file, follow the [init guide](references/init-guide.md).
If asked to adjust the existing convention — adding a scope, for example — consult the [configuration reference](references/configuration.md).

## Commit steps

Create commits by following the steps below.
If a script invocation fails, do not work around it on your own judgment unless told to — report it to the user and stop.

### 1. Ask how to write

Run the following command to check the rules for writing a commit message.

```bash
uv run scripts/commit.py show-rules
```

Follow this command's output when composing the commit message.
Handle a failure here as follows.

| Error | Response |
| :-- | :-- |
| `uv` is not found (`command not found: uv` or similar) | Tell the user this skill needs [uv](https://docs.astral.sh/uv/), and stop. Do not install it yourself. |
| `error: no commit convention found ...` | Follow the [init guide](references/init-guide.md), then continue to the next step. |
| Any other configuration error | Consult the [configuration reference](references/configuration.md) and adjust the configuration accordingly. |

### 2. Identify what to commit

When no commit target is specified, determine it as follows.

#### If files are staged

Confirm with the user that the staged files are what should be committed. If not, ask which files should be the target instead.

#### If no files are staged

If exactly one file has changed, ask the user whether to stage and commit it.
Otherwise, ask the user which files should be committed.

### 3. Decide the type and scope

Decide the commit's type and scope based on the target diff and the rules from step 1.

If the type or scope can't be narrowed down, stop and propose splitting the change into separate commits, presenting the type, scope and content of each resulting commit. If the user agrees to split, repeat step 4 onward for each commit in turn.

### 4. Compose and propose the message

Read the [commit message guide](references/creation-guide.md), then compose the message with `--dry-run`.

If validation fails, fix the message and retry. Never work around a rejection by calling `git commit` directly, and never rewrite the convention itself.

### 5. Commit once approved

Show the user the message composed in step 4, and confirm whether it's fine to commit with that content. Never proceed without their explicit approval. If they raise any concern about the message, restart from step 4 — a request for changes is not approval.

Once approved, run the same command from step 4 again with `--dry-run` removed. For an operation not covered here, such as `--amend`, check `uv run scripts/commit.py create --help`.
