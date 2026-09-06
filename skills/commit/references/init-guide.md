# Init guide

Initialization prepares the configuration file and, when needed, registers a Git hook. Follow these steps.

## Initialization steps

### 1. Run `uv run scripts/commit.py init`

If initialization was triggered by something other than an explicit user instruction, such as an error, tell the user the repository has no commit convention yet, confirm they want to proceed, and run the command below once they approve. Otherwise, run it directly.

```bash
uv run scripts/commit.py init
```

If the command fails, do not work around it — report it to the user and stop.

### 2. Set up the convention

Ask the user whether they want to adjust it interactively or edit the file directly. If they choose direct editing, wait until they say it is ready. If they choose the interactive route, walk through the settings one by one with them, referring to the [configuration reference](configuration.md), and edit the file based on their answers.

### 3. Re-run `init`

Once the convention is settled, run `init` again. If `hook.enabled` is set, this is when the hook gets synced. Re-running has no side effects.

### 4. Propose minifying the file

Propose to the user removing the comments and the values that match the defaults from the configuration file, so that only the settings specific to this repository remain. Once they approve, run the command below.

```bash
uv run scripts/commit.py minify
```
