"""Unit tests for :mod:`kiro.tool_permissions` (declarative tool gating).

kiro-cli runs its own tools and asks the gateway for approval via
``session/request_permission``. Historically the gateway answered with the single
``ACP_TRUST_TOOLS`` boolean; these tests cover the policy that lets some calls be
allowed and others refused.

Ground truth comes from a live kiro-cli 2.17.0 probe: the request carries
``toolCall.title`` (``"Running: echo PERMPROBE_OK"``, ``"Reading README.md:1-5"``,
``"Running: @server/tool"``), an ``options`` array of
``allow_once``/``allow_always``/``reject_once``, and ``_meta.trustOptions``
entries whose ``display`` holds a clean command form. Answering ``reject_once``
genuinely blocks execution, and decisions are per call.

**The default must remain allow-everything** for every harness — a gateway with
no rules configured behaves exactly as before.
"""
from __future__ import annotations

import pytest

from kiro.tool_permissions import (
    DECISION_ALLOW,
    DECISION_DEFAULT,
    DECISION_DENY,
    PermissionRule,
    ToolPermissionPolicy,
    canonical_tool,
    describe_tool_call,
    parse_rule,
    parse_rules,
    select_option_id,
)

# The options kiro-cli actually offers (verified live).
LIVE_OPTIONS = [
    {"optionId": "allow_once", "name": "Yes", "kind": "allow_once"},
    {"optionId": "allow_always", "name": "Always", "kind": "allow_always"},
    {"optionId": "reject_once", "name": "No", "kind": "reject_once"},
]


def _request(title: str, kind: str = None, displays: list = None) -> dict:
    """Build a ``session/request_permission`` params object.

    Args:
        title: kiro-cli's prose title for the tool call.
        kind: Optional ACP tool kind.
        displays: Optional ``_meta.trustOptions`` display strings.

    Returns:
        The params dict.
    """
    tool_call = {"toolCallId": "tooluse_x", "title": title}
    if kind:
        tool_call["kind"] = kind
    params = {"sessionId": "s1", "toolCall": tool_call, "options": LIVE_OPTIONS}
    if displays:
        params["_meta"] = {"trustOptions": [
            {"label": "Base command", "display": d,
             "setting_key": "allowedCommands", "patterns": [d]}
            for d in displays
        ]}
    return params


# ---------------------------------------------------------------------------
# Default behaviour — must stay allow-everything
# ---------------------------------------------------------------------------

class TestDefaultAllowsEverything:
    """With no rules the policy defers, so every tool stays allowed."""

    @pytest.mark.parametrize("title", [
        "Running: echo hi",
        "Running: rm -rf /tmp/scratch",
        "Reading README.md:1-5",
        "Editing src/app.py",
        "Running: @github/create_issue",
        "Fetching https://example.com",
        "Some unrecognised activity",
    ])
    def test_no_rules_defers_for_every_tool(self, title):
        policy = ToolPermissionPolicy.from_config("", "", default_allow=True)
        assert policy.has_rules is False
        assert policy.decide(_request(title)) == DECISION_DEFAULT

    def test_empty_policy_selects_allow_once(self):
        assert select_option_id(LIVE_OPTIONS, approve=True) == "allow_once"

    def test_default_deny_posture_still_available(self):
        policy = ToolPermissionPolicy.from_config("", "", default_allow=False)
        assert policy.default_allow is False
        assert policy.decide(_request("Running: echo hi")) == DECISION_DEFAULT


# ---------------------------------------------------------------------------
# Rule parsing
# ---------------------------------------------------------------------------

class TestCanonicalTool:
    """Harness and kiro-cli tool spellings collapse to one category."""

    @pytest.mark.parametrize("name", ["Bash", "bash", "shell", "execute", "run"])
    def test_execute_aliases(self, name):
        assert canonical_tool(name) == "execute"

    @pytest.mark.parametrize("name,expected", [
        ("Read", "read"), ("Write", "edit"), ("Edit", "edit"),
        ("Grep", "search"), ("Glob", "search"), ("WebFetch", "fetch"),
    ])
    def test_other_categories(self, name, expected):
        assert canonical_tool(name) == expected

    def test_unknown_and_empty(self):
        assert canonical_tool("Frobnicate") is None
        assert canonical_tool(None) is None
        assert canonical_tool("") is None


class TestParseRule:
    """Rules use the Claude Code ``permissions`` spelling."""

    def test_tool_with_pattern(self):
        rule = parse_rule("Bash(git status*)")
        assert rule.tool == "execute"
        assert rule.pattern == "git status*"

    def test_bare_tool_matches_all_of_that_tool(self):
        rule = parse_rule("Edit")
        assert rule.tool == "edit"
        assert rule.pattern is None

    def test_bare_glob_is_tool_agnostic(self):
        rule = parse_rule("rm -rf *")
        assert rule.tool is None
        assert rule.pattern == "rm -rf *"

    def test_claude_code_mcp_spelling(self):
        rule = parse_rule("mcp__github__create_issue")
        assert rule.tool == "mcp"
        assert rule.pattern == "github/create_issue"

    def test_kiro_mcp_spelling(self):
        rule = parse_rule("@github/create_issue")
        assert rule.tool == "mcp"
        assert rule.pattern == "github/create_issue"

    def test_unknown_tool_name_becomes_glob(self):
        rule = parse_rule("Frobnicate(x)")
        assert rule.tool is None
        assert rule.pattern == "Frobnicate(x)"

    def test_empty_and_non_string(self):
        assert parse_rule("") is None
        assert parse_rule("   ") is None
        assert parse_rule(None) is None
        assert parse_rule(42) is None


class TestParseRules:
    """Rule lists accept JSON, delimited strings, and real lists."""

    def test_json_array(self):
        rules = parse_rules('["Bash(git *)", "Read"]')
        assert [r.tool for r in rules] == ["execute", "read"]

    def test_comma_separated(self):
        rules = parse_rules("Bash(git *), Read, Edit")
        assert [r.tool for r in rules] == ["execute", "read", "edit"]

    def test_newline_separated(self):
        rules = parse_rules("Bash(git *)\nRead\n")
        assert len(rules) == 2

    def test_comma_inside_pattern_is_not_a_separator(self):
        rules = parse_rules("Bash(echo a,b)")
        assert len(rules) == 1
        assert rules[0].pattern == "echo a,b"

    def test_real_list_accepted(self):
        rules = parse_rules(["Bash", "Read"])
        assert len(rules) == 2

    def test_empty_inputs(self):
        assert parse_rules("") == []
        assert parse_rules(None) == []
        assert parse_rules([]) == []

    def test_invalid_json_falls_back_to_plain_parsing(self):
        rules = parse_rules('["Bash(git *)"')  # malformed JSON
        assert rules  # parsed as plain text rather than dropped


# ---------------------------------------------------------------------------
# Describing the incoming request
# ---------------------------------------------------------------------------

class TestDescribeToolCall:
    """The prose title is turned back into a structured view."""

    def test_running_command(self):
        tool, target, title, extra = describe_tool_call(
            _request("Running: echo PERMPROBE_OK"))
        assert tool == "execute"
        assert target == "echo PERMPROBE_OK"
        assert title == "Running: echo PERMPROBE_OK"

    def test_reading_file(self):
        tool, target, _, _ = describe_tool_call(_request("Reading README.md:1-5"))
        assert tool == "read"
        assert target == "README.md:1-5"

    def test_mcp_tool(self):
        tool, target, _, _ = describe_tool_call(
            _request("Running: @stdioprobe/stdio_probe_tool"))
        assert tool == "mcp"
        assert target == "stdioprobe/stdio_probe_tool"

    def test_explicit_kind_is_honoured(self):
        tool, _, _, _ = describe_tool_call(
            _request("Anything at all", kind="edit"))
        assert tool == "edit"

    def test_trust_option_displays_collected(self):
        _, _, _, extra = describe_tool_call(
            _request("Running: echo hi", displays=["echo *"]))
        assert "echo *" in extra

    def test_unparseable_title_falls_back_to_title_as_target(self):
        tool, target, _, _ = describe_tool_call(_request("Mystery activity"))
        assert tool is None
        assert target == "Mystery activity"

    def test_missing_tool_call_does_not_raise(self):
        tool, target, title, extra = describe_tool_call({"options": []})
        assert tool is None and title == ""


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------

class TestPolicyDecisions:
    """Precedence is deny -> allow -> default."""

    def test_deny_blocks_matching_command(self):
        policy = ToolPermissionPolicy.from_config("", "Bash(rm -rf *)")
        assert policy.decide(_request("Running: rm -rf /data")) == DECISION_DENY

    def test_deny_does_not_affect_other_commands(self):
        policy = ToolPermissionPolicy.from_config("", "Bash(rm -rf *)")
        assert policy.decide(_request("Running: ls -la")) == DECISION_DEFAULT

    def test_allow_matches_specific_command(self):
        policy = ToolPermissionPolicy.from_config("Bash(git status*)", "")
        assert policy.decide(_request("Running: git status")) == DECISION_ALLOW

    def test_deny_wins_over_allow(self):
        policy = ToolPermissionPolicy.from_config("Bash", "Bash(rm *)")
        assert policy.decide(_request("Running: rm x")) == DECISION_DENY
        assert policy.decide(_request("Running: ls")) == DECISION_ALLOW

    def test_bare_tool_rule_scopes_by_category(self):
        policy = ToolPermissionPolicy.from_config("", "Edit")
        assert policy.decide(_request("Editing src/app.py")) == DECISION_DENY
        assert policy.decide(_request("Reading src/app.py")) == DECISION_DEFAULT

    def test_tool_agnostic_glob_matches_any_tool(self):
        policy = ToolPermissionPolicy.from_config("", "*secrets*")
        assert policy.decide(_request("Reading config/secrets.yml")) == DECISION_DENY
        assert policy.decide(
            _request("Running: cat config/secrets.yml")) == DECISION_DENY

    def test_mcp_rule_matches_mcp_call(self):
        policy = ToolPermissionPolicy.from_config("", "mcp__github__create_issue")
        assert policy.decide(
            _request("Running: @github/create_issue")) == DECISION_DENY
        assert policy.decide(
            _request("Running: @github/list_issues")) == DECISION_DEFAULT

    def test_trust_option_display_enables_match(self):
        """kiro-cli's clean command form is also matched against."""
        policy = ToolPermissionPolicy.from_config("", "Bash(echo *)")
        assert policy.decide(
            _request("Running: echo hi", displays=["echo *"])) == DECISION_DENY

    def test_exact_command_matches_trailing_wildcard_rule(self):
        policy = ToolPermissionPolicy.from_config("Bash(git status*)", "")
        assert policy.decide(_request("Running: git status")) == DECISION_ALLOW

    def test_read_path_rule(self):
        policy = ToolPermissionPolicy.from_config("", "Read(/etc/*)")
        assert policy.decide(_request("Reading /etc/shadow")) == DECISION_DENY
        assert policy.decide(_request("Reading ./README.md")) == DECISION_DEFAULT


class TestSelectOptionId:
    """The chosen option id must reflect the intent, never invert it."""

    def test_approve_picks_allow_once(self):
        assert select_option_id(LIVE_OPTIONS, True) == "allow_once"

    def test_refuse_picks_reject_once(self):
        assert select_option_id(LIVE_OPTIONS, False) == "reject_once"

    def test_refuse_never_falls_back_to_an_allow_option(self):
        # Only allow options offered: refusing must not silently approve.
        options = [{"optionId": "allow_once", "kind": "allow_once"}]
        assert select_option_id(options, False) == "reject_once"

    def test_empty_options_still_answers(self):
        assert select_option_id([], True) == "allow_once"
        assert select_option_id([], False) == "reject_once"

    def test_unconventional_option_ids_matched_by_verb(self):
        options = [{"optionId": "allow-this-once", "kind": "custom_allow"}]
        assert select_option_id(options, True) == "allow-this-once"


class TestV3PermissionOptionShape:
    """The v3 engine offers different optionIds than v1/v2 — match on `kind`.

    Captured verbatim from a live kiro-cli 2.19.x v3 ``session/request_permission``
    (title "printf <marker>"). The ids are ``accept``/``reject`` rather than
    ``allow_once``/``reject_once``, so any id-based matching would silently invert
    the decision. Answering the ``reject`` id was confirmed to block execution.
    """

    V3_OPTIONS = [
        {"optionId": "accept", "kind": "allow_once", "name": "Accept"},
        {"optionId": "always-accept", "kind": "allow_always", "name": "Always accept"},
        {"optionId": "reject", "kind": "reject_once", "name": "Reject"},
        {"optionId": "always-reject", "kind": "reject_always", "name": "Always reject"},
    ]

    def test_refuse_picks_the_v3_reject_id(self):
        assert select_option_id(self.V3_OPTIONS, False) == "reject"

    def test_approve_picks_the_v3_accept_id(self):
        assert select_option_id(self.V3_OPTIONS, True) == "accept"

    def test_refuse_never_selects_an_accept_id(self):
        """Guards the fail-safe: refusing must never resolve to an allow option."""
        assert select_option_id(self.V3_OPTIONS, False) not in {"accept", "always-accept"}


# ---------------------------------------------------------------------------
# Integration with ACPClient
# ---------------------------------------------------------------------------

class TestAcpClientIntegration:
    """The client consults the policy when answering permission requests."""

    def test_default_client_allows_every_tool(self):
        from kiro.acp_client import ACPClient
        client = ACPClient(command="kiro-cli")
        assert client._permission_policy.has_rules is False
        for title in ("Running: rm -rf /", "Reading /etc/shadow",
                      "Editing app.py", "Running: @srv/tool"):
            chosen = client._select_permission_option(LIVE_OPTIONS,
                                                     _request(title))
            assert chosen == "allow_once", title

    def test_policy_denies_matching_call(self):
        from kiro.acp_client import ACPClient
        policy = ToolPermissionPolicy.from_config("", "Bash(rm -rf *)")
        client = ACPClient(command="kiro-cli", permission_policy=policy)
        assert client._select_permission_option(
            LIVE_OPTIONS, _request("Running: rm -rf /data")) == "reject_once"
        assert client._select_permission_option(
            LIVE_OPTIONS, _request("Running: ls")) == "allow_once"

    def test_policy_allows_despite_trust_tools_false(self):
        """An allow rule can permit a call in an otherwise answer-only gateway."""
        from kiro.acp_client import ACPClient
        policy = ToolPermissionPolicy.from_config("Bash(git status*)", "",
                                                  default_allow=False)
        client = ACPClient(command="kiro-cli", trust_tools=False,
                           permission_policy=policy)
        assert client._select_permission_option(
            LIVE_OPTIONS, _request("Running: git status")) == "allow_once"
        assert client._select_permission_option(
            LIVE_OPTIONS, _request("Running: curl evil.example")) == "reject_once"

    def test_trust_tools_false_without_rules_still_rejects(self):
        from kiro.acp_client import ACPClient
        client = ACPClient(command="kiro-cli", trust_tools=False)
        assert client._select_permission_option(
            LIVE_OPTIONS, _request("Running: echo hi")) == "reject_once"

    def test_params_omitted_preserves_boolean_behaviour(self):
        from kiro.acp_client import ACPClient
        client = ACPClient(command="kiro-cli")
        assert client._select_permission_option(LIVE_OPTIONS) == "allow_once"
