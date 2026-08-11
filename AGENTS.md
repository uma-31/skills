# skills

A repository for developing and distributing skills for coding agents.

## Skills

Write skills to the [Agent Skills specification](https://agentskills.io/specification). Each skill is a directory under `skills/`:

```
skills/<skill-name>/
├── SKILL.md          # Frontmatter and instructions (required)
├── SKILL.ja.md       # Japanese translation of SKILL.md (required)
├── scripts/          # Executable code
├── references/       # Documentation read on demand
└── assets/           # Templates and data
```

### Constraints

- Frontmatter must include `name` and `description`
  - Add other fields as needed, following the [specification](https://agentskills.io/specification)
- `name` must match the parent directory name
- `description` states what the skill does and when to use it
- Keep the body under 500 lines and 5000 tokens
  - Split the details into `references/` and link to them by paths relative to the skill root
- Every Markdown file needs a `.ja.md` Japanese translation, with the original written in English
  - Agents using the skill read only the English
- Keep a skill self-contained, referring to nothing outside its own directory
  - Consumers place it wherever their tool expects, by symlink, copy or submodule

## Commits

Use the `commit` skill under `skills/commit/` to write the message. If it isn't installed, install it before committing.

## Scripts

Write scripts that accompany a skill in Bash when they are simple, and in Python when they are complex.

A skill can't rely on its scripts keeping the executable bit once installed, so it must invoke its scripts through their interpreter — `bash scripts/<name>.sh` or `uv run scripts/<name>.py` — never directly.

### Python scripts

Declare dependencies with [PEP 723](https://peps.python.org/pep-0723/) inline metadata and keep each script to a single self-contained file.

## Development environment

Tooling and the task runner are managed with [mise](https://mise.jdx.dev/). Everything mise owns lives under `.mise/`, with its configuration in `.mise/config.toml`.

### Tasks

Operations this repository performs often — quality checks and formatting, for instance — are defined as tasks. `mise tasks` lists what is currently available.

Always use an existing task when one covers what you are doing. When none does, consider adding one if the operation is likely to recur.
