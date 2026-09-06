# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.13", "pyyaml>=6.0"]
# ///

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal, Protocol, cast

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

# A footer's token uses "-" in place of whitespace, e.g. `Acked-by`.
# `BREAKING CHANGE` is the one exception, per the Conventional Commits spec.
COMMIT_FOOTER_RE = re.compile(
    r"^(?P<token>BREAKING CHANGE|[A-Za-z][A-Za-z0-9-]*)(?P<sep>: | #)(?P<value>.*)$"
)

# Prefixed with the comment string, this marks where `git commit --verbose`
# (or `commit.cleanup=scissors`) starts the part git drops, which it does only
# after the commit-msg hook has run.
GIT_SCISSORS_MARK = " ------------------------ >8 ------------------------"

# "type(scope)!: subject" -- the colon is followed by exactly one space.
COMMIT_HEADER_RE = re.compile(
    r"^(?P<type>[^\s(!:]+)"
    + r"(?:\((?P<scope>[^()\r\n]*)\))?"
    + r"(?P<breaking>!)?"
    + r": (?P<subject>.*)$"
)


@dataclass(frozen=True, slots=True)
class CommitFooter:
    """One footer line, e.g. `Refs: #123` or, GitHub-style, `Refs #123`."""

    token: str
    value: str
    separator: Literal[": ", " #"] = ": "

    @classmethod
    def parse(cls, footer_text: str) -> CommitFooter:
        """Parse `"Token: value"` or `"Token #value"`, as passed to `--footer`."""
        footer_match = COMMIT_FOOTER_RE.match(footer_text.strip())
        if footer_match is None:
            raise RuntimeError(
                f"malformed footer: {footer_text!r}"
                + ' (use "Token: value" or "Token #value")'
            )
        separator = cast("Literal[': ', ' #']", footer_match.group("sep"))
        return cls(
            token=footer_match.group("token"),
            value=footer_match.group("value").strip(),
            separator=separator,
        )

    def render(self) -> str:
        return f"{self.token}{self.separator}{self.value}"


@dataclass(frozen=True, slots=True)
class CommitMessage:
    """A Conventional Commits message: header, optional body, optional footers.

    Constructed directly from `create`'s arguments, or by parsing an existing
    message for `validate`, then rendered back to the text passed to
    `git commit -F -`.
    """

    type: str
    scope: str | None
    breaking: bool
    subject: str
    body: tuple[str, ...] = ()
    footers: tuple[CommitFooter, ...] = ()

    @classmethod
    def parse(cls, message_text: str) -> CommitMessage:
        """Parse an existing commit message into its parts."""
        lines = message_text.replace("\r\n", "\n").strip("\n").split("\n")
        header = lines[0] if lines else ""
        header_match = COMMIT_HEADER_RE.match(header)
        if header_match is None:
            raise RuntimeError(
                "header does not match the Conventional Commits grammar:"
                + f" {header!r} (expected: <type>[(scope)][!]: <subject>)"
            )

        if len(lines) > 1 and lines[1].strip():
            raise RuntimeError(
                f"the header must be followed by a blank line, got {lines[1]!r}"
            )
        lines_after_header = lines[2:] if len(lines) > 2 else []

        # The footer block is the trailing run of lines that all parse as
        # footers; everything before it is the body.
        footer_start_index = len(lines_after_header)
        for index in range(len(lines_after_header) - 1, -1, -1):
            line = lines_after_header[index]
            if not line.strip() or COMMIT_FOOTER_RE.match(line) is None:
                break
            footer_start_index = index

        # Blank lines separate body paragraphs, as `render` writes them.
        body_paragraphs: list[str] = []
        paragraph_lines: list[str] = []
        for line in lines_after_header[:footer_start_index]:
            if line.strip():
                paragraph_lines.append(line)
            elif paragraph_lines:
                body_paragraphs.append("\n".join(paragraph_lines))
                paragraph_lines = []
        if paragraph_lines:
            body_paragraphs.append("\n".join(paragraph_lines))
        footers = tuple(
            CommitFooter.parse(line)
            for line in lines_after_header[footer_start_index:]
            if line.strip()
        )

        return cls(
            type=header_match.group("type"),
            scope=header_match.group("scope"),
            breaking=bool(header_match.group("breaking")),
            subject=header_match.group("subject"),
            body=tuple(body_paragraphs),
            footers=footers,
        )

    def render(self) -> str:
        """Render as the text passed to `git commit -F -`."""
        scope_part = f"({self.scope})" if self.scope else ""
        breaking_marker = "!" if self.breaking else ""
        header = f"{self.type}{scope_part}{breaking_marker}: {self.subject}"

        message_sections = [header, *self.body]
        if self.footers:
            message_sections.append(
                "\n".join(footer.render() for footer in self.footers)
            )

        return "\n\n".join(message_sections) + "\n"

    def create(
        self, *, amend: bool = False, signoff: bool = False, allow_empty: bool = False
    ) -> int:
        """Commit this message via `git commit -F -`, returning its exit code."""
        if not amend and not allow_empty:
            staged_diff = subprocess.run(
                ["git", "diff", "--cached", "--quiet"], check=False
            )
            if staged_diff.returncode == 0:
                raise RuntimeError(
                    "nothing staged to commit"
                    + " (stage changes with `git add`, or pass --amend / --allow-empty)"
                )

        git_command = ["git", "commit", "-F", "-"]
        if amend:
            git_command.append("--amend")
        if signoff:
            git_command.append("--signoff")
        if allow_empty:
            git_command.append("--allow-empty")

        git_commit = subprocess.run(
            git_command, input=self.render(), text=True, check=False
        )
        return git_commit.returncode


class BaseCommitConfigSchema(BaseModel):
    """Base of `CommitConfig`'s schema: read-only, and no keys beyond the known."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)


class AllowedCommitType(BaseCommitConfigSchema):
    """One allowed commit type (e.g. `feat`), with the description shown alongside it."""

    name: str
    description: str = ""

    @model_validator(mode="before")
    @classmethod
    def accept_bare_name(cls, raw_value: object) -> object:
        """Accept both `feat` and `{name: feat, description: ...}`."""
        return {"name": raw_value} if isinstance(raw_value, str) else raw_value


class AllowedCommitScope(BaseCommitConfigSchema):
    """One allowed commit scope, with the description shown alongside it."""

    name: str
    description: str = ""

    @model_validator(mode="before")
    @classmethod
    def accept_bare_name(cls, raw_value: object) -> object:
        """Accept both `cli` and `{name: cli, description: ...}`."""
        return {"name": raw_value} if isinstance(raw_value, str) else raw_value


class CommitMsgHookConfig(BaseCommitConfigSchema):
    enabled: bool


class CommitHeaderRule(BaseCommitConfigSchema):
    max_length: int


class CommitSubjectRule(BaseCommitConfigSchema):
    case: Literal["lower", "sentence", "any"]
    end_with_period: bool


class CommitBodyRule(BaseCommitConfigSchema):
    required: bool


class CommitScopeRule(BaseCommitConfigSchema):
    required: bool
    allow_custom: bool
    values: tuple[AllowedCommitScope, ...]


class CommitBreakingRule(BaseCommitConfigSchema):
    style: Literal["bang", "footer", "both"]


class CommitFooterRule(BaseCommitConfigSchema):
    required: tuple[str, ...]
    required_for_coding_agent: tuple[str, ...]


class CommitConfig(BaseCommitConfigSchema):
    """The commit convention loaded from `.git-commit.yaml`."""

    hook: CommitMsgHookConfig
    language: str
    header: CommitHeaderRule
    subject: CommitSubjectRule
    body: CommitBodyRule
    types: tuple[AllowedCommitType, ...]
    scopes: CommitScopeRule
    breaking: CommitBreakingRule
    footers: CommitFooterRule
    ignored_headers: tuple[re.Pattern[str], ...]

    def describe_rules(self) -> str:
        """Render this convention as instructions for whoever writes a commit message."""
        lines = [f"Language: {self.language} -- write the subject and body in it."]

        subject_constraints = [
            f"at most {self.header.max_length} columns including the type and scope"
        ]
        if self.subject.case == "lower":
            subject_constraints.append(
                "starting with a lowercase word unless it is a proper noun or identifier"
            )
        elif self.subject.case == "sentence":
            subject_constraints.append(
                "starting with a capitalized word unless it is a proper noun or identifier"
            )
        subject_constraints.append(
            "ending with a period"
            if self.subject.end_with_period
            else "with no trailing period"
        )
        lines.append(f"Subject: {', '.join(subject_constraints)}.")

        lines.append(
            "Body: required. Say why the change was made, not what the diff shows."
            if self.body.required
            else "Body: optional. Add one unless the motivation is self-evident."
        )

        lines.append("")
        lines.append("Type -- choose exactly one:")
        type_column_width = max(len(commit_type.name) for commit_type in self.types)
        lines.extend(
            f"  {commit_type.name:<{type_column_width}}  {commit_type.description}".rstrip()
            for commit_type in self.types
        )

        scope_rule = self.scopes
        scope_requirement = "required" if scope_rule.required else "optional"
        lines.append("")
        if scope_rule.values and scope_rule.allow_custom:
            lines.append(
                f"Scope -- {scope_requirement}. Choose one of these, or another if none fits:"
            )
        elif scope_rule.values:
            lines.append(f"Scope -- {scope_requirement}, choose exactly one:")
        else:
            lines.append(
                f"Scope: {scope_requirement}. Use a noun naming the part of the codebase affected."
            )
        if scope_rule.values:
            scope_column_width = max(
                len(commit_scope.name) for commit_scope in scope_rule.values
            )
            lines.extend(
                f"  {commit_scope.name:<{scope_column_width}}  {commit_scope.description}".rstrip()
                for commit_scope in scope_rule.values
            )

        if self.footers.required:
            lines.append("")
            lines.append(f"Required footers: {', '.join(self.footers.required)}")

        lines.append("")
        lines.append(
            "Breaking change: mark it per this repository's convention"
            + f" (`breaking.style: {self.breaking.style}`)."
        )

        return "\n".join(lines)


def resolve_git_path(
    *rev_parse_args: str, working_directory: Path | None = None
) -> Path | None:
    """Run `git rev-parse <rev_parse_args>` from `working_directory` (or the cwd).

    Returns `None` on failure, otherwise the result resolved against `working_directory`
    (`rev-parse` sometimes answers with a path relative to it).
    """
    git_command = ["git"]
    if working_directory is not None:
        git_command += ["-C", str(working_directory)]
    git_command += ["rev-parse", *rev_parse_args]

    git_rev_parse = subprocess.run(
        git_command, capture_output=True, text=True, check=False
    )
    if git_rev_parse.returncode != 0:
        return None

    rev_parse_path = Path(git_rev_parse.stdout.strip())
    if not rev_parse_path.is_absolute():
        rev_parse_path = (working_directory or Path.cwd()) / rev_parse_path
    return rev_parse_path.resolve()


def find_main_worktree_root(working_directory: Path) -> Path | None:
    """Return the main worktree's root, or `None` if it is bare or git fails."""
    git_worktree_list = subprocess.run(
        ["git", "-C", str(working_directory), "worktree", "list", "--porcelain", "-z"],
        capture_output=True,
        text=True,
        check=False,
    )
    if git_worktree_list.returncode != 0:
        return None

    # The main worktree is always listed first. With `-z`, each attribute ends
    # in NUL and each worktree in an extra NUL; `bare` means no working tree.
    main_worktree_attributes = git_worktree_list.stdout.split("\0\0", 1)[0].split("\0")
    if "bare" in main_worktree_attributes:
        return None
    if not main_worktree_attributes[0].startswith("worktree "):
        return None
    main_worktree_path = Path(
        main_worktree_attributes[0].removeprefix("worktree ")
    ).resolve()

    # A submodule's main worktree is listed as its git directory, whose
    # `core.worktree` points at the actual checkout.
    git_common_directory = resolve_git_path(
        "--git-common-dir", working_directory=working_directory
    )
    if main_worktree_path == git_common_directory:
        return resolve_git_path(
            "--show-toplevel", working_directory=git_common_directory
        )
    return main_worktree_path


@dataclass(frozen=True, slots=True)
class CommitConfigFiles:
    """Where a repository's `.git-commit.yaml` file(s) were found.

    `shared_path` and `local_path` are computed, not stored: the shared and local
    files are assumed to sit in the same directory and follow the same
    naming convention (extension, and whether the name is dot-prefixed).
    """

    directory: Path
    extension: Literal["yml", "yaml"]
    hidden: bool

    @property
    def shared_path(self) -> Path:
        name_prefix = "." if self.hidden else ""
        return self.directory / f"{name_prefix}git-commit.{self.extension}"

    @property
    def local_path(self) -> Path:
        name_prefix = "." if self.hidden else ""
        return self.directory / f"{name_prefix}git-commit.local.{self.extension}"

    @classmethod
    def find(cls, start_directory: Path) -> CommitConfigFiles:
        """Search upward from `start_directory`, stopping at this worktree's root.

        In a linked worktree with nothing found, search the main worktree the
        same way, from the directory matching `start_directory`.
        """
        start_directory = start_directory.resolve()
        worktree_root = resolve_git_path(
            "--show-toplevel", working_directory=start_directory
        )

        config_files = cls.search_upward(start_directory, worktree_root)
        if config_files is not None:
            return config_files

        searched_extent = "up to the worktree root"
        if worktree_root is not None and start_directory.is_relative_to(worktree_root):
            main_worktree_root = find_main_worktree_root(start_directory)
            if main_worktree_root is not None and main_worktree_root != worktree_root:
                config_files = cls.search_upward(
                    main_worktree_root / start_directory.relative_to(worktree_root),
                    main_worktree_root,
                )
                if config_files is not None:
                    return config_files
                searched_extent += (
                    f", then likewise in the main worktree {main_worktree_root}"
                )

        raise FileNotFoundError(
            "no commit convention found (searched for .git-commit[.local].yaml"
            + f" from {start_directory} {searched_extent})"
        )

    @classmethod
    def search_upward(
        cls, start_directory: Path, stop_directory: Path | None
    ) -> CommitConfigFiles | None:
        """Search from `start_directory` up to `stop_directory`.

        With `stop_directory` `None`, or not an ancestor, search up to the
        filesystem root.
        """
        # Most preferred combination first.
        naming_conventions: tuple[tuple[bool, Literal["yml", "yaml"]], ...] = (
            (True, "yml"),
            (True, "yaml"),
            (False, "yml"),
            (False, "yaml"),
        )

        for directory in (start_directory, *start_directory.parents):
            for hidden, extension in naming_conventions:
                candidate = cls(directory=directory, extension=extension, hidden=hidden)
                if candidate.shared_path.is_file() or candidate.local_path.is_file():
                    return candidate
            if directory == stop_directory:
                break
        return None

    def load_config(self) -> CommitConfig:
        """Load, merge and validate this convention's files into a `CommitConfig`."""
        default_config_path = (
            Path(__file__).resolve().parent.parent
            / "assets"
            / "git-commit.default.yaml"
        )
        merged_data: dict[str, object] = {}
        for layer_path in (default_config_path, self.shared_path, self.local_path):
            if not layer_path.is_file():
                continue
            layer_data = cast(
                "object", yaml.safe_load(layer_path.read_text(encoding="utf-8"))
            )
            if layer_data is None:
                layer_data = {}
            if not isinstance(layer_data, dict):
                raise TypeError(f"{layer_path} must contain a mapping at the top level")

            # Overlay this layer onto `merged_data`, descending into nested mappings.
            # Lists and scalars are replaced as a whole. A key left empty in a
            # layer (`values:` with nothing after it) is treated as omitted.
            pending_merges: list[tuple[dict[str, object], dict[str, object]]] = [
                (merged_data, cast("dict[str, object]", layer_data))
            ]
            while pending_merges:
                merge_target, merge_source = pending_merges.pop()
                for key, value in merge_source.items():
                    existing_value = merge_target.get(key)
                    if value is None:
                        continue
                    if isinstance(value, dict) and isinstance(existing_value, dict):
                        pending_merges.append(
                            (
                                cast("dict[str, object]", existing_value),
                                cast("dict[str, object]", value),
                            )
                        )
                    else:
                        merge_target[key] = value

        return CommitConfig.model_validate(merged_data)


def check_commit_message(config: CommitConfig, message: CommitMessage) -> list[str]:
    """Return every violation of `config` found in `message`; empty if none."""
    violations: list[str] = []

    allowed_types = [commit_type.name for commit_type in config.types]
    if message.type not in allowed_types:
        violations.append(
            f"type '{message.type}' is not allowed (allowed: {', '.join(allowed_types)})"
        )

    scope_rule = config.scopes
    allowed_scopes = [commit_scope.name for commit_scope in scope_rule.values]
    if message.scope is None and scope_rule.required:
        violations.append("scope is required")
    elif (
        message.scope is not None
        and not scope_rule.allow_custom
        and message.scope not in allowed_scopes
    ):
        violations.append(
            f"scope '{message.scope}' is not allowed"
            + f" (allowed: {', '.join(allowed_scopes)})"
        )

    if not message.subject.strip():
        violations.append("subject is empty")
    else:
        scope_part = f"({message.scope})" if message.scope else ""
        breaking_marker = "!" if message.breaking else ""
        header = f"{message.type}{scope_part}{breaking_marker}: {message.subject}"
        header_width = sum(
            2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
            for char in header
        )
        if header_width > config.header.max_length:
            violations.append(
                f"header is {header_width} columns wide, limit is {config.header.max_length}"
            )

        ends_with_period = message.subject.rstrip().endswith((".", "。"))
        if not config.subject.end_with_period and ends_with_period:
            violations.append("subject must not end with a period")
        if config.subject.end_with_period and not ends_with_period:
            violations.append("subject must end with a period")

        # Only a plain word is checked, so that proper nouns and identifiers
        # like `README.md`, `GitHub` or `iOS` can lead the subject as written.
        first_word = next(iter(message.subject.split()), "")
        subject_case = config.subject.case
        first_word_tail = first_word[1:]
        if (
            subject_case == "lower"
            and first_word[:1].isupper()
            and first_word_tail == first_word_tail.lower()
        ):
            violations.append(
                f"subject must start with a lowercase word, got '{first_word}'"
            )
        if (
            subject_case == "sentence"
            and first_word[:1].islower()
            and first_word.islower()
        ):
            violations.append(
                f"subject must start with a capitalized word, got '{first_word}'"
            )

    if config.body.required and not message.body:
        violations.append("body is required but missing")

    present_footer_tokens = {footer.token for footer in message.footers}
    for required_token in config.footers.required:
        if required_token not in present_footer_tokens:
            violations.append(f"the `{required_token}` footer is required but missing")

    breaking_style = config.breaking.style
    has_breaking_marker = message.breaking
    has_breaking_footer = any(
        footer.token in ("BREAKING CHANGE", "BREAKING-CHANGE")
        for footer in message.footers
    )
    if breaking_style == "footer" and has_breaking_marker and not has_breaking_footer:
        violations.append(
            "`breaking.style: footer` requires a BREAKING CHANGE footer, not '!'"
        )
    if breaking_style == "both" and has_breaking_marker != has_breaking_footer:
        violations.append(
            "`breaking.style: both` requires '!' in the header and a BREAKING CHANGE footer"
        )

    return violations


class InitCommandArgs(Protocol):
    force: bool


# Marks the block this skill inserts into `commit-msg`, so a later run can
# find it again to update or remove it, and so a hand-written hook survives
# alongside it.
HOOK_MARKER_BEGIN = "# BEGIN COMMIT SKILL HOOK"
HOOK_MARKER_END = "# END COMMIT SKILL HOOK"


def is_commit_msg_hook_installed(hook_path: Path) -> bool:
    """Whether `hook_path` already contains this skill's hook block."""
    return hook_path.is_file() and HOOK_MARKER_BEGIN in hook_path.read_text(
        encoding="utf-8"
    )


def install_commit_msg_hook(hook_path: Path) -> None:
    """Insert or refresh this skill's hook block in `hook_path`, creating it if needed."""
    hook_content = hook_path.read_text(encoding="utf-8") if hook_path.is_file() else ""
    hook_content = re.sub(
        rf"{re.escape(HOOK_MARKER_BEGIN)}\n.*?{re.escape(HOOK_MARKER_END)}\n",
        "",
        hook_content,
        flags=re.DOTALL,
    )
    hook_script_path = Path(__file__).resolve().parent / "commit-msg-hook.sh"
    # Invoked via `bash` rather than executed directly: `gh skill install`
    # and similar installers don't preserve the executable bit on the hook
    # script, and that shouldn't block every commit for everyone who installs
    # this skill that way.
    hook_block = (
        f"{HOOK_MARKER_BEGIN}\n"
        + f'bash "{hook_script_path}" "$@" || exit 1\n'
        + f"{HOOK_MARKER_END}\n"
    )

    hook_lines = hook_content.splitlines(keepends=True)
    updated_hook_content = (
        hook_lines[0] + hook_block + "".join(hook_lines[1:])
        if hook_lines and hook_lines[0].startswith("#!")
        else "#!/bin/sh\n" + hook_block + hook_content
    )

    hook_path.parent.mkdir(parents=True, exist_ok=True)
    _ = hook_path.write_text(updated_hook_content, encoding="utf-8")
    hook_path.chmod(hook_path.stat().st_mode | 0o111)


def uninstall_commit_msg_hook(hook_path: Path) -> None:
    """Remove this skill's hook block from `hook_path`, deleting a now-empty file."""
    hook_content = hook_path.read_text(encoding="utf-8")
    remaining_hook_content = re.sub(
        rf"{re.escape(HOOK_MARKER_BEGIN)}\n.*?{re.escape(HOOK_MARKER_END)}\n",
        "",
        hook_content,
        flags=re.DOTALL,
    )
    if remaining_hook_content.strip() in ("", "#!/bin/sh"):
        hook_path.unlink()
    else:
        _ = hook_path.write_text(remaining_hook_content, encoding="utf-8")


def describe_commit_msg_hook_mismatch(config: CommitConfig) -> str | None:
    """Return a warning if the commit-msg hook doesn't match `hook.enabled`; else None.

    `.git/hooks/` isn't part of the repository, so a fresh clone never has the
    hook installed even when `hook.enabled: true`. There's no way to notice
    this other than checking on every run, since the hook itself can't fire
    if it was never installed.
    """
    hooks_directory = resolve_git_path("--git-path", "hooks")
    if hooks_directory is None:
        return None
    is_hook_installed = is_commit_msg_hook_installed(hooks_directory / "commit-msg")

    if config.hook.enabled and not is_hook_installed:
        return "the commit-msg hook is not installed; run `commit.py init` to enable it"
    if not config.hook.enabled and is_hook_installed:
        return (
            "the commit-msg hook is installed, but `hook.enabled` is false;"
            + " run `commit.py init` to remove it"
        )
    return None


def handle_init_command(args: InitCommandArgs) -> int:
    worktree_root = resolve_git_path("--show-toplevel")
    if worktree_root is None:
        raise RuntimeError("not inside a git repository")

    default_config_path = (
        Path(__file__).resolve().parent.parent / "assets" / "git-commit.default.yaml"
    )
    existing_config_path = next(
        (
            worktree_root / f"{name_prefix}git-commit.{extension}"
            for name_prefix in (".", "")
            for extension in ("yml", "yaml")
            if (worktree_root / f"{name_prefix}git-commit.{extension}").is_file()
        ),
        None,
    )
    if existing_config_path is None or args.force:
        config_path = (
            existing_config_path
            if existing_config_path is not None
            else worktree_root / ".git-commit.yaml"
        )
        _ = config_path.write_text(
            default_config_path.read_text(encoding="utf-8"), encoding="utf-8"
        )
        print(f"created {config_path}")
        print("  edit `language`, `types` and `scopes.values` to match this repository")
    else:
        print(f"{existing_config_path} already exists, leaving it as is")

    config = CommitConfigFiles.find(worktree_root).load_config()

    hooks_directory = resolve_git_path(
        "--git-path", "hooks", working_directory=worktree_root
    )
    if hooks_directory is None:
        if config.hook.enabled:
            raise RuntimeError("could not determine the git hooks directory")
        return 0
    hook_path = hooks_directory / "commit-msg"

    if hook_path.is_symlink():
        raise RuntimeError(f"{hook_path} is a symlink to something else")

    if config.hook.enabled:
        was_hook_installed = is_commit_msg_hook_installed(hook_path)
        install_commit_msg_hook(hook_path)
        print(
            f"{'updated' if was_hook_installed else 'added'} the commit-msg check in {hook_path}"
        )
    elif is_commit_msg_hook_installed(hook_path):
        uninstall_commit_msg_hook(hook_path)
        print(f"removed the commit-msg check from {hook_path}")

    return 0


class MinifyCommandArgs(Protocol):
    pass


def handle_minify_command(_args: MinifyCommandArgs) -> int:
    config_files = CommitConfigFiles.find(Path.cwd())
    # Found through the main-worktree fallback, the file belongs to another
    # checkout, where it may be tracked; rewriting it from here would be a
    # surprise.
    worktree_root = resolve_git_path("--show-toplevel")
    if worktree_root is not None and not config_files.directory.is_relative_to(
        worktree_root
    ):
        raise RuntimeError(
            f"{config_files.shared_path} is outside this worktree;"
            + " run `minify` from the worktree it belongs to"
        )
    if not config_files.shared_path.is_file():
        raise FileNotFoundError(f"{config_files.shared_path} does not exist")
    # Refuse to rewrite a file that does not load in the first place.
    _ = config_files.load_config()

    default_config_path = (
        Path(__file__).resolve().parent.parent / "assets" / "git-commit.default.yaml"
    )
    default_config_data = cast(
        "object", yaml.safe_load(default_config_path.read_text(encoding="utf-8"))
    )
    shared_config_data = cast(
        "object", yaml.safe_load(config_files.shared_path.read_text(encoding="utf-8"))
    )

    def strip_defaults(config_value: object, default_value: object) -> object:
        """Drop what `config_value` shares with `default_value`.

        Returns `None` when nothing is left.
        """
        if not isinstance(config_value, dict):
            return None if config_value == default_value else config_value
        default_mapping = cast(
            "dict[str, object]",
            default_value if isinstance(default_value, dict) else {},
        )
        kept_data = {
            key: stripped_item
            for key, config_item in cast("dict[str, object]", config_value).items()
            if (stripped_item := strip_defaults(config_item, default_mapping.get(key)))
            is not None
        }
        return kept_data or None

    minified_config_data = strip_defaults(shared_config_data, default_config_data)
    _ = config_files.shared_path.write_text(
        yaml.safe_dump(minified_config_data, allow_unicode=True, sort_keys=False)
        if minified_config_data is not None
        else "",
        encoding="utf-8",
    )
    print(f"removed comments and default values from {config_files.shared_path}")
    return 0


class ShowRulesCommandArgs(Protocol):
    pass


def handle_show_rules_command(_args: ShowRulesCommandArgs) -> int:
    config = CommitConfigFiles.find(Path.cwd()).load_config()
    warning = describe_commit_msg_hook_mismatch(config)
    if warning:
        print(f"warning: {warning}", file=sys.stderr)
    print(config.describe_rules())
    return 0


class CreateCommandArgs(Protocol):
    type: str
    scope: str | None
    subject: str
    body: list[str] | None
    body_file: str | None
    breaking: bool
    breaking_description: str | None
    footer: list[str] | None
    signoff: bool
    amend: bool
    allow_empty: bool
    dry_run: bool


def handle_create_command(args: CreateCommandArgs) -> int:
    config = CommitConfigFiles.find(Path.cwd()).load_config()
    warning = describe_commit_msg_hook_mismatch(config)
    if warning:
        print(f"warning: {warning}", file=sys.stderr)

    body_paragraphs: list[str] = [
        paragraph.strip() for paragraph in (args.body or []) if paragraph.strip()
    ]
    if args.body_file:
        body_from_file = (
            sys.stdin.read()
            if args.body_file == "-"
            else Path(args.body_file).read_text(encoding="utf-8")
        ).strip()
        if body_from_file:
            body_paragraphs.append(body_from_file)

    footers: list[CommitFooter] = []
    if args.breaking and config.breaking.style in ("footer", "both"):
        if not args.breaking_description:
            raise RuntimeError(
                f"`breaking.style: {config.breaking.style}` requires a description"
                + " for the BREAKING CHANGE footer (pass --breaking-description)"
            )
        footers.append(
            CommitFooter(
                token="BREAKING CHANGE", value=args.breaking_description.strip()
            )
        )
    footers.extend(CommitFooter.parse(footer_text) for footer_text in args.footer or [])

    message = CommitMessage(
        type=args.type,
        scope=args.scope or None,
        breaking=args.breaking and config.breaking.style in ("bang", "both"),
        subject=args.subject.strip(),
        body=tuple(body_paragraphs),
        footers=tuple(footers),
    )

    violations = check_commit_message(config, message)
    if violations:
        raise RuntimeError(
            "the assembled message violates the configuration:\n"
            + "\n".join(f"  - {violation}" for violation in violations)
        )

    if args.dry_run:
        print(message.render(), end="")
        return 0

    return message.create(
        amend=args.amend, signoff=args.signoff, allow_empty=args.allow_empty
    )


class ValidateCommandArgs(Protocol):
    message: str | None
    file: str | None
    from_hook: bool


def read_git_comment_prefix() -> str:
    """Return what git starts comment lines with here (`#` unless configured).

    `core.commentChar` and `core.commentString` set the same thing, the one
    set last winning. With `auto`, git picks a character per message that
    can't be recovered afterward, so `#` is assumed.
    """
    git_config = subprocess.run(
        ["git", "config", "--get-regexp", r"^core\.comment(char|string)$"],
        capture_output=True,
        text=True,
        check=False,
    )
    comment_settings = git_config.stdout.splitlines()
    if git_config.returncode != 0 or not comment_settings:
        return "#"
    _, _, comment_prefix = comment_settings[-1].partition(" ")
    if not comment_prefix or comment_prefix == "auto":
        return "#"
    return comment_prefix


def handle_validate_command(args: ValidateCommandArgs) -> int:
    if args.message is not None:
        message_text = args.message
    elif args.file is not None:
        message_text = (
            sys.stdin.read()
            if args.file == "-"
            else Path(args.file).read_text(encoding="utf-8")
        )
    else:
        git_log = subprocess.run(
            ["git", "log", "-1", "--pretty=%B"],
            capture_output=True,
            text=True,
            check=False,
        )
        if git_log.returncode != 0:
            raise RuntimeError(
                f"could not read the last commit message: {git_log.stderr.strip()}"
            )
        message_text = git_log.stdout

    comment_prefix = read_git_comment_prefix()
    message_lines = message_text.replace("\r\n", "\n").split("\n")
    # Git follows its own scissors line with a comment; without one, the line
    # was typed into the message (`-m`, `-F`) and git keeps it.
    scissors_line = comment_prefix + GIT_SCISSORS_MARK
    for index, line in enumerate(message_lines[:-1]):
        if line == scissors_line and message_lines[index + 1].startswith(
            comment_prefix
        ):
            message_lines = message_lines[:index]
            break
    # Strip comment lines so commit-msg hook templates validate cleanly.
    message_text = "\n".join(
        line for line in message_lines if not line.startswith(comment_prefix)
    )

    # The hook is shared by every worktree, so it can fire where no convention
    # applies; there it steps aside instead of blocking the commit.
    try:
        config_files = CommitConfigFiles.find(Path.cwd())
    except FileNotFoundError:
        if not args.from_hook:
            raise
        print(
            "commit-msg: no configuration file found here, skipping the commit convention check",
            file=sys.stderr,
        )
        return 0
    config = config_files.load_config()
    if args.from_hook and not config.hook.enabled:
        print(
            "commit-msg: `hook.enabled` is false here, skipping the commit convention check",
            file=sys.stderr,
        )
        return 0

    header = message_text.lstrip("\n").split("\n", 1)[0]
    if any(pattern.search(header) for pattern in config.ignored_headers):
        print("ok (matches `ignored_headers`, skipped)")
        return 0

    message = CommitMessage.parse(message_text)
    violations = check_commit_message(config, message)
    if violations:
        for violation in violations:
            print(f"error: {violation}", file=sys.stderr)
        return 1

    print("ok")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="commit.py",
        description="Create Conventional Commits from a repository-local configuration file.",
    )
    subparsers = parser.add_subparsers(
        title="commands", metavar="<command>", required=True
    )

    init_parser = subparsers.add_parser(
        "init", help="write the default configuration and sync the commit-msg hook"
    )
    init_parser.set_defaults(handler=handle_init_command)
    _ = init_parser.add_argument(
        "--force", action="store_true", help="overwrite an existing configuration"
    )

    minify_parser = subparsers.add_parser(
        "minify",
        help="remove comments and default values from the configuration",
    )
    minify_parser.set_defaults(handler=handle_minify_command)

    show_rules_parser = subparsers.add_parser(
        "show-rules", help="print how to write a commit message here"
    )
    show_rules_parser.set_defaults(handler=handle_show_rules_command)

    create_parser = subparsers.add_parser(
        "create", help="assemble, validate and commit a message"
    )
    create_parser.set_defaults(handler=handle_create_command)
    _ = create_parser.add_argument(
        "--type", required=True, help="commit type, e.g. feat"
    )
    _ = create_parser.add_argument("--scope", help="commit scope")
    _ = create_parser.add_argument(
        "--subject", required=True, help="short summary line"
    )
    _ = create_parser.add_argument(
        "--body",
        action="append",
        help="body paragraph; repeat for multiple paragraphs",
    )
    _ = create_parser.add_argument(
        "--body-file", help="read the body from a file ('-' for stdin)"
    )
    _ = create_parser.add_argument(
        "--breaking", action="store_true", help="mark this commit as a breaking change"
    )
    _ = create_parser.add_argument(
        "--breaking-description", help="text for the BREAKING CHANGE footer"
    )
    _ = create_parser.add_argument(
        "--footer", action="append", help='footer such as "Refs: #123"; repeatable'
    )
    _ = create_parser.add_argument(
        "--signoff", action="store_true", help="pass --signoff to git commit"
    )
    _ = create_parser.add_argument(
        "--amend", action="store_true", help="amend the previous commit"
    )
    _ = create_parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="allow a commit with no staged changes",
    )
    _ = create_parser.add_argument(
        "--dry-run", action="store_true", help="print the message instead of committing"
    )

    validate_parser = subparsers.add_parser(
        "validate", help="validate a commit message"
    )
    validate_parser.set_defaults(handler=handle_validate_command)
    validate_message_source = validate_parser.add_mutually_exclusive_group()
    _ = validate_message_source.add_argument(
        "--message", help="message text to validate"
    )
    _ = validate_message_source.add_argument(
        "--file", help="read the message from a file ('-' for stdin)"
    )
    _ = validate_parser.add_argument(
        "--from-hook",
        action="store_true",
        help="skip, rather than fail, where no convention"
        + " or `hook.enabled: false` applies",
    )

    parsed_args = parser.parse_args(argv)
    handler = cast(Callable[[argparse.Namespace], int], parsed_args.handler)

    try:
        return handler(parsed_args)
    except (
        RuntimeError,
        FileNotFoundError,
        TypeError,
        yaml.YAMLError,
        ValidationError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    exit_code = main(sys.argv[1:])
    sys.exit(exit_code)
