"""Declarative permission gating for kiro-cli's built-in tool runs.

Why this exists
---------------
kiro-cli runs its **own** tools (shell, file read/edit, search, fetch, MCP) and
asks the gateway for approval first via ``session/request_permission``. Until
now the gateway answered with a single global boolean (``ACP_TRUST_TOOLS``):
approve everything, or refuse everything. Harnesses that implement their own
permission gating could not express anything in between through the gateway
(`issue #31 <https://github.com/ankitcharolia/kiro-gateway/issues/31>`_ comment).

That was a gateway limitation, **not** an ACP one. Verified against a live
kiro-cli 2.17.0 probe:

* the request carries enough to decide on —
  ``{"toolCall": {"toolCallId": …, "title": "Running: echo PERMPROBE_OK"},
  "options": [allow_once, allow_always, reject_once],
  "_meta": {"trustOptions": [{"setting_key": "allowedCommands",
  "patterns": ["echo( .*)?"], "display": "echo *"}]}}``;
* answering ``reject_once`` **genuinely blocks execution** — a denied
  ``touch`` never created its file, and the agent reported the denial and
  carried on; and
* decisions are **per call**: in one session a probe allowed one command and
  denied the next, and exactly the allowed one took effect.

So this module turns that into a policy: deny rules, allow rules, and a
fallback to ``ACP_TRUST_TOOLS`` when nothing matches.

Rule syntax
-----------
Rules are matched against the tool call kiro-cli describes:

===============================  ==============================================
Rule                             Matches
===============================  ==============================================
``Bash(git status*)``            an ``execute`` call whose command glob-matches
``Bash``                         every ``execute`` call
``Read(/etc/*)``                 a ``read`` call whose target glob-matches
``Edit`` / ``Write``             every file-modifying call
``mcp__github__create_issue``    that MCP tool (Claude Code spelling)
``@github/create_issue``         the same MCP tool (kiro-cli spelling)
``rm -rf *``                     a bare glob, matched against command *or* title
===============================  ==============================================

Tool names are case-insensitive and aliased, so ``Bash``, ``bash``, ``shell``,
``execute`` and ``run`` all mean the same thing. This is deliberately the
Claude Code ``permissions`` spelling so a harness's existing rules can be reused
verbatim.

Precedence is **deny → allow → default**, which is the conventional and safe
ordering: an explicit deny can never be overridden by a broad allow.
"""

from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from loguru import logger

# Decisions the policy can reach.
DECISION_ALLOW = "allow"
DECISION_DENY = "deny"
DECISION_DEFAULT = "default"

# Canonical tool categories, with the spellings harnesses and kiro-cli use.
_TOOL_ALIASES = {
    "execute": "execute",
    "bash": "execute",
    "shell": "execute",
    "run": "execute",
    "command": "execute",
    "executebash": "execute",
    "read": "read",
    "readfile": "read",
    "cat": "read",
    "edit": "edit",
    "write": "edit",
    "create": "edit",
    "writefile": "edit",
    "editfile": "edit",
    "multiedit": "edit",
    "search": "search",
    "grep": "search",
    "glob": "search",
    "find": "search",
    "fetch": "fetch",
    "webfetch": "fetch",
    "web": "fetch",
    "websearch": "fetch",
    "mcp": "mcp",
}

# ``Tool(pattern)`` rule form.
_RULE_RE = re.compile(r"^\s*(?P<tool>[A-Za-z_][A-Za-z0-9_]*)\s*\((?P<pattern>.*)\)\s*$",
                      re.DOTALL)

# Claude Code's MCP rule spelling: ``mcp__<server>__<tool>``.
_MCP_RULE_RE = re.compile(r"^mcp__(?P<server>[^_]+(?:_[^_]+)*?)__(?P<tool>.+)$")

# Titles kiro-cli puts on a tool call (verified live): "Running: echo hi",
# "Reading README.md:1-5", "Running: @server/tool".
_TITLE_PATTERNS = (
    ("mcp", re.compile(r"^\s*(?:running|calling)\s*:\s*@(?P<target>\S+)", re.IGNORECASE)),
    ("execute", re.compile(r"^\s*(?:running|executing)\s*:\s*(?P<target>.+)$",
                           re.IGNORECASE | re.DOTALL)),
    ("read", re.compile(r"^\s*(?:reading|read)\s+(?P<target>.+)$", re.IGNORECASE)),
    ("edit", re.compile(r"^\s*(?:editing|writing|creating|updating|applying)\s+(?P<target>.+)$",
                        re.IGNORECASE)),
    ("search", re.compile(r"^\s*(?:searching|grepping|finding)\s+(?P<target>.+)$",
                          re.IGNORECASE)),
    ("fetch", re.compile(r"^\s*(?:fetching|downloading)\s+(?P<target>.+)$",
                         re.IGNORECASE)),
)


def canonical_tool(name: object) -> Optional[str]:
    """Map a tool name or ACP ``kind`` to its canonical category.

    Args:
        name: A tool name (``"Bash"``), an ACP ``kind`` (``"execute"``), or
            ``None``.

    Returns:
        The canonical category (``"execute"``, ``"read"``, ``"edit"``,
        ``"search"``, ``"fetch"``, ``"mcp"``), or ``None`` when unrecognised.
    """
    if not name:
        return None
    key = re.sub(r"[^a-z0-9]", "", str(name).lower())
    return _TOOL_ALIASES.get(key)


@dataclass(frozen=True)
class PermissionRule:
    """One parsed allow/deny rule.

    Attributes:
        tool: Canonical tool category the rule is scoped to, or ``None`` to
            match any tool.
        pattern: A glob matched against the call's target/command (and its
            title), or ``None`` to match every call of ``tool``.
        source: Where the rule came from, for logging.
    """

    tool: Optional[str]
    pattern: Optional[str]
    source: str = "config"

    def matches(self, tool: Optional[str], target: str, title: str,
                extra: Sequence[str] = ()) -> bool:
        """Report whether this rule matches a described tool call.

        Args:
            tool: The call's canonical tool category, or ``None`` if unknown.
            target: The command or path the call acts on.
            title: kiro-cli's human-readable title for the call.
            extra: Additional candidate strings to match (e.g. kiro-cli's own
                ``_meta.trustOptions`` displays).

        Returns:
            ``True`` when the rule applies to this call.
        """
        if self.tool is not None:
            # A tool-scoped rule needs the categories to agree. An unknown
            # category never satisfies a scoped rule (fail closed for allows,
            # and simply doesn't widen denies).
            if tool != self.tool:
                return False
        if self.pattern is None:
            return True
        candidates = [c for c in (target, title, *extra) if c]
        pattern = self.pattern
        for candidate in candidates:
            if fnmatch.fnmatch(candidate, pattern):
                return True
            # A trailing-wildcard rule should also match the bare prefix, so
            # ``Bash(git status*)`` matches exactly ``git status``.
            if pattern.endswith("*") and candidate == pattern[:-1].rstrip():
                return True
        return False


def parse_rule(raw: object, source: str = "config") -> Optional[PermissionRule]:
    """Parse one rule string into a :class:`PermissionRule`.

    Args:
        raw: The rule text (``"Bash(git *)"``, ``"Read"``, ``"rm -rf *"``,
            ``"mcp__srv__tool"``, ``"@srv/tool"``).
        source: Where the rule came from, for logging.

    Returns:
        The parsed rule, or ``None`` when ``raw`` is empty/not a string.
    """
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None

    mcp = _MCP_RULE_RE.match(text)
    if mcp:
        return PermissionRule(
            tool="mcp",
            pattern=f"{mcp.group('server')}/{mcp.group('tool')}",
            source=source,
        )

    if text.startswith("@"):
        return PermissionRule(tool="mcp", pattern=text[1:], source=source)

    match = _RULE_RE.match(text)
    if match:
        tool = canonical_tool(match.group("tool"))
        pattern = match.group("pattern").strip()
        if tool is None:
            # Unknown tool name -> treat the whole thing as a bare glob so the
            # rule still does something predictable rather than being dropped.
            return PermissionRule(tool=None, pattern=text, source=source)
        return PermissionRule(tool=tool, pattern=pattern or None, source=source)

    tool_only = canonical_tool(text)
    if tool_only is not None and " " not in text:
        return PermissionRule(tool=tool_only, pattern=None, source=source)

    return PermissionRule(tool=None, pattern=text, source=source)


def parse_rules(value: object, source: str = "config") -> List[PermissionRule]:
    """Parse a rule list from JSON, a comma/newline-separated string, or a list.

    Args:
        value: ``'["Bash(git *)"]'``, ``"Bash(git *), Read"``, or a real list.
        source: Where the rules came from, for logging.

    Returns:
        The parsed rules, skipping anything unusable.
    """
    items: List[object] = []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                decoded = json.loads(text)
                items = decoded if isinstance(decoded, list) else [decoded]
            except ValueError:
                logger.warning("Tool permission rules are not valid JSON; "
                               "falling back to comma-separated parsing")
                items = _split_plain(text)
        else:
            items = _split_plain(text)
    elif isinstance(value, (list, tuple)):
        items = list(value)
    elif value is None:
        return []
    else:
        items = [value]

    rules = [parse_rule(item, source) for item in items]
    return [r for r in rules if r is not None]


def _split_plain(text: str) -> List[object]:
    """Split a plain rule string on newlines and commas outside parentheses.

    A rule's pattern can legitimately contain a comma, so splitting only happens
    at depth zero.

    Args:
        text: The raw string.

    Returns:
        The individual rule strings.
    """
    parts: List[object] = []
    buf: List[str] = []
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if char in ",\n" and depth == 0:
            if "".join(buf).strip():
                parts.append("".join(buf).strip())
            buf = []
            continue
        buf.append(char)
    if "".join(buf).strip():
        parts.append("".join(buf).strip())
    return parts


def describe_tool_call(params: dict) -> tuple:
    """Derive the tool category, target and title from a permission request.

    ``session/request_permission`` describes the call with a prose ``title``
    (verified live: ``"Running: echo PERMPROBE_OK"``, ``"Reading README.md:1-5"``,
    ``"Running: @server/tool"``) and sometimes a ``kind``. This recovers a
    structured view so rules can be matched.

    Args:
        params: The request's ``params`` object.

    Returns:
        A ``(tool, target, title, extra)`` tuple, where ``tool`` is the
        canonical category (or ``None``), ``target`` is the command/path,
        ``title`` is the raw title, and ``extra`` holds additional candidate
        strings taken from ``_meta.trustOptions``.
    """
    tool_call = params.get("toolCall")
    if not isinstance(tool_call, dict):
        tool_call = {}
    title = str(tool_call.get("title") or "")

    tool = canonical_tool(tool_call.get("kind"))
    target = ""
    for category, pattern in _TITLE_PATTERNS:
        match = pattern.match(title)
        if match:
            target = match.group("target").strip()
            if tool is None:
                tool = category
            break
    if not target:
        target = title

    # kiro-cli's own trust suggestions carry the command in a clean form
    # (``display: "echo *"``), which makes glob rules match more reliably.
    extra: List[str] = []
    meta = params.get("_meta")
    if isinstance(meta, dict):
        for option in meta.get("trustOptions") or []:
            if isinstance(option, dict):
                display = option.get("display")
                if isinstance(display, str) and display:
                    extra.append(display)
    return tool, target, title, extra


@dataclass
class ToolPermissionPolicy:
    """Allow/deny rules applied to every ``session/request_permission``.

    Attributes:
        allow: Rules that approve a matching call.
        deny: Rules that refuse a matching call. Checked first.
        default_allow: What to do when no rule matches — normally
            ``ACP_TRUST_TOOLS``.
    """

    allow: List[PermissionRule] = field(default_factory=list)
    deny: List[PermissionRule] = field(default_factory=list)
    default_allow: bool = True

    @property
    def has_rules(self) -> bool:
        """Report whether any rule is configured.

        Returns:
            ``True`` when at least one allow or deny rule exists.
        """
        return bool(self.allow or self.deny)

    @classmethod
    def from_config(cls, allow: object, deny: object,
                    default_allow: bool = True) -> "ToolPermissionPolicy":
        """Build a policy from raw configured values.

        Args:
            allow: Raw allow rules (JSON list, delimited string, or list).
            deny: Raw deny rules, same accepted forms.
            default_allow: Fallback when no rule matches.

        Returns:
            The constructed policy.
        """
        return cls(
            allow=parse_rules(allow, "ACP_TOOL_ALLOW"),
            deny=parse_rules(deny, "ACP_TOOL_DENY"),
            default_allow=default_allow,
        )

    def decide(self, params: dict) -> str:
        """Decide how to answer one permission request.

        Precedence is deny → allow → default, so an explicit deny is never
        overridden by a broader allow.

        Args:
            params: The ``session/request_permission`` ``params`` object.

        Returns:
            ``"deny"``, ``"allow"``, or ``"default"`` when no rule matched.
        """
        tool, target, title, extra = describe_tool_call(params)

        for rule in self.deny:
            if rule.matches(tool, target, title, extra):
                logger.info(
                    f"Tool permission DENIED by policy ({rule.source}: "
                    f"tool={rule.tool or '*'} pattern={rule.pattern!r}): {title!r}"
                )
                return DECISION_DENY

        for rule in self.allow:
            if rule.matches(tool, target, title, extra):
                logger.debug(
                    f"Tool permission allowed by policy ({rule.source}: "
                    f"tool={rule.tool or '*'} pattern={rule.pattern!r}): {title!r}"
                )
                return DECISION_ALLOW

        return DECISION_DEFAULT


def select_option_id(options: Sequence[dict], approve: bool) -> str:
    """Pick the option id matching the desired outcome.

    Args:
        options: The request's ``options`` array (each with ``optionId`` and
            ``kind``; kiro-cli offers ``allow_once``/``allow_always``/
            ``reject_once``).
        approve: ``True`` to approve this invocation, ``False`` to refuse it.

    Returns:
        The chosen ``optionId``. Falls back to the conventional id when the
        agent offers nothing usable, so a turn is never left unanswered.
    """
    wanted = (("allow_once", "allow_always", "allow") if approve
              else ("reject_once", "reject_always", "reject", "deny"))
    for kind in wanted:
        for opt in options or []:
            if opt.get("kind") == kind or opt.get("optionId") == kind:
                return opt.get("optionId", kind)

    verb = "allow" if approve else "reject"
    for opt in options or []:
        if verb in str(opt.get("kind", "")) or verb in str(opt.get("optionId", "")):
            return opt.get("optionId", verb)

    if options:
        # Never silently approve when the intent was to refuse: only fall back
        # to an arbitrary option when approving.
        if approve:
            return options[0].get("optionId", "allow_once")
        return "reject_once"
    return "allow_once" if approve else "reject_once"
