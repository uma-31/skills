# Configuration reference

## The configuration file

The file is named `git-commit`, and can be hidden by prefixing it with `.`. Its extension is `.yaml` or `.yml`.
A file with `.local` before the extension, such as `git-commit.local.yaml`, can hold settings kept out of version control.
When both exist they are merged, and `.local` wins on conflicting keys. Mappings are merged key by key, recursively, but a list is replaced as a whole rather than element by element.

The files are searched for from the current directory up to the root of the current worktree.
In a linked worktree, if none is found there, the search repeats from the matching directory of the main worktree.

## Settings

Keys left out take their values from `assets/git-commit.default.yaml`.
A list, once given, replaces the default list as a whole.

For each key's type, default and basic meaning, see the comments in `assets/git-commit.default.yaml`.

### Notes

- Changes to `hook.enabled` take effect only after `init` is run again.
- For a `language` without letter case, such as Japanese, set `subject.case` to `any`. `lower` would reject a subject that opens with a proper noun like `Python`.
