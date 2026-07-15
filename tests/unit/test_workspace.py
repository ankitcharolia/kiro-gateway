"""Unit tests for :mod:`kiro.workspace` (harness cwd resolution).

The gateway anchors each ACP session in the harness's working directory by
recovering it from the request — the ``X-Kiro-Workspace`` header, explicit
``filesystem_roots``, or a ``Working directory:`` line embedded in the system
prompt (the ``<env>`` block convention used by OpenCode and Claude Code).

All candidates must be an absolute, existing directory to be honoured, so a
bogus value in untrusted prompt text is ignored rather than used.
"""
from __future__ import annotations

from kiro.acp_models import PromptMessage
from kiro.workspace import (
    build_filesystem_roots,
    parse_working_dir,
    resolve_workspace_cwd,
)


def _env_system(path: str) -> PromptMessage:
    """Build a system message mimicking OpenCode/Claude Code's <env> block."""
    return PromptMessage(
        role="system",
        content=(
            "You are a helpful agent.\n"
            "<env>\n"
            f"  Working directory: {path}\n"
            "  Workspace root folder: /\n"
            "  Is directory a git repo: no\n"
            "  Platform: linux\n"
            "</env>\n"
        ),
    )


class TestParseWorkingDirSuccess:
    """The <env> ``Working directory:`` line is recovered and validated."""

    def test_parses_env_block_working_directory(self, tmp_path):
        messages = [_env_system(str(tmp_path)), PromptMessage(role="user", content="hi")]
        assert parse_working_dir(messages) == str(tmp_path)

    def test_case_insensitive_label(self, tmp_path):
        msg = PromptMessage(role="system", content=f"working DIRECTORY: {tmp_path}")
        assert parse_working_dir([msg]) == str(tmp_path)

    def test_finds_path_in_block_list_content(self, tmp_path):
        msg = PromptMessage(
            role="system",
            content=[
                {"type": "text", "text": "preamble"},
                {"type": "text", "text": f"<env>\n  Working directory: {tmp_path}\n</env>"},
            ],
        )
        assert parse_working_dir([msg]) == str(tmp_path)

    def test_strips_file_scheme(self, tmp_path):
        msg = PromptMessage(role="system", content=f"Working directory: file://{tmp_path}")
        assert parse_working_dir([msg]) == str(tmp_path)

    def test_first_valid_match_wins(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        msg = PromptMessage(
            role="system",
            content=(
                f"Working directory: {sub}\n"
                f"Working directory: {tmp_path}\n"
            ),
        )
        assert parse_working_dir([msg]) == str(sub)

    def test_oh_my_pi_quoted_is_phrasing(self, tmp_path):
        """Oh My Pi: 'the current working directory is '<path>'.' (verified live)."""
        msg = PromptMessage(
            role="system",
            content=f"Today is 2026-07-15, and the current working directory is '{tmp_path}'.\n",
        )
        assert parse_working_dir([msg]) == str(tmp_path)

    def test_hermes_current_working_directory_colon(self, tmp_path):
        """Hermes: 'Current working directory: <path>' next to a Home directory line."""
        msg = PromptMessage(
            role="system",
            content=f"Home directory: /root\nCurrent working directory: {tmp_path}\n",
        )
        assert parse_working_dir([msg]) == str(tmp_path)

    def test_kilo_environment_details_colon(self, tmp_path):
        """Kilo Code: 'Working directory: <path>' inside <environment_details>."""
        msg = PromptMessage(
            role="system",
            content=f"<environment_details>\nWorking directory: {tmp_path}\nWorkspace root folder: /\n</environment_details>",
        )
        assert parse_working_dir([msg]) == str(tmp_path)

    def test_double_quoted_is_phrasing(self, tmp_path):
        msg = PromptMessage(role="system", content=f'working directory is "{tmp_path}"')
        assert parse_working_dir([msg]) == str(tmp_path)


class TestParseWorkingDirRejects:
    """Invalid / unusable candidates are ignored (fall through to fallback)."""

    def test_nonexistent_path_ignored(self):
        msg = PromptMessage(role="system", content="Working directory: /no/such/dir/xyz123")
        assert parse_working_dir([msg]) is None

    def test_relative_path_ignored(self):
        msg = PromptMessage(role="system", content="Working directory: ./relative/dir")
        assert parse_working_dir([msg]) is None

    def test_file_path_not_a_directory_ignored(self, tmp_path):
        f = tmp_path / "a_file.txt"
        f.write_text("x")
        msg = PromptMessage(role="system", content=f"Working directory: {f}")
        assert parse_working_dir([msg]) is None

    def test_no_marker_returns_none(self):
        msgs = [PromptMessage(role="user", content="just a normal question")]
        assert parse_working_dir(msgs) is None

    def test_empty_messages_returns_none(self):
        assert parse_working_dir([]) is None


class TestResolveWorkspaceCwd:
    """Header takes precedence over the parsed prompt directory."""

    def test_header_wins_over_prompt(self, tmp_path):
        header_dir = tmp_path / "from_header"
        header_dir.mkdir()
        prompt_dir = tmp_path / "from_prompt"
        prompt_dir.mkdir()
        messages = [_env_system(str(prompt_dir))]
        assert resolve_workspace_cwd(str(header_dir), messages) == str(header_dir)

    def test_falls_back_to_prompt_when_header_absent(self, tmp_path):
        assert resolve_workspace_cwd(None, [_env_system(str(tmp_path))]) == str(tmp_path)

    def test_invalid_header_falls_through_to_prompt(self, tmp_path):
        assert resolve_workspace_cwd("/no/such/dir", [_env_system(str(tmp_path))]) == str(tmp_path)

    def test_returns_none_when_nothing_usable(self):
        assert resolve_workspace_cwd(None, [PromptMessage(role="user", content="hi")]) is None


class TestBuildFilesystemRoots:
    """The precedence chain: header > body filesystem_roots > parsed prompt."""

    def test_header_produces_single_root(self, tmp_path):
        roots = build_filesystem_roots(str(tmp_path), None, [])
        assert len(roots) == 1
        assert roots[0].path == str(tmp_path)

    def test_body_roots_win_over_prompt(self, tmp_path):
        body_dir = tmp_path / "body"
        body_dir.mkdir()
        prompt_dir = tmp_path / "prompt"
        prompt_dir.mkdir()
        roots = build_filesystem_roots(
            None, [{"path": str(body_dir)}], [_env_system(str(prompt_dir))]
        )
        assert [r.path for r in roots] == [str(body_dir)]

    def test_header_wins_over_body_roots(self, tmp_path):
        header_dir = tmp_path / "hdr"
        header_dir.mkdir()
        roots = build_filesystem_roots(
            str(header_dir), [{"path": str(tmp_path)}], []
        )
        assert [r.path for r in roots] == [str(header_dir)]

    def test_prompt_used_when_no_header_or_body(self, tmp_path):
        roots = build_filesystem_roots(None, None, [_env_system(str(tmp_path))])
        assert [r.path for r in roots] == [str(tmp_path)]

    def test_empty_when_nothing_present(self):
        roots = build_filesystem_roots(None, [], [PromptMessage(role="user", content="hi")])
        assert roots == []
