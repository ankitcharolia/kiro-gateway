"""Inject MCP (Model Context Protocol) server tool definitions into ACP requests."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .acp_models import ACPRequest, ACPTool

logger = logging.getLogger(__name__)


def _load_tools_from_file(path: Path) -> List[ACPTool]:
    """Load tool definitions from a JSON file."""
    try:
        data = json.loads(path.read_text())
        tools: List[ACPTool] = []
        entries = data if isinstance(data, list) else data.get("tools", [])
        for entry in entries:
            tools.append(
                ACPTool(
                    name=entry["name"],
                    description=entry.get("description"),
                    input_schema=entry.get("input_schema") or entry.get("parameters") or {},
                )
            )
        return tools
    except Exception as exc:
        logger.warning("Failed to load MCP tools from %s: %s", path, exc)
        return []


def load_mcp_tools(tools_path: Optional[str] = None) -> List[ACPTool]:
    """
    Load MCP tool definitions.

    Looks for tools in (in order):
      1. *tools_path* if explicitly provided
      2. ``~/.kiro/mcp_tools.json``
      3. ``./mcp_tools.json`` in the CWD
    """
    candidates: List[Path] = []
    if tools_path:
        candidates.append(Path(tools_path).expanduser())
    candidates.append(Path.home() / ".kiro" / "mcp_tools.json")
    candidates.append(Path("mcp_tools.json"))

    for path in candidates:
        if path.exists():
            tools = _load_tools_from_file(path)
            if tools:
                logger.info("Loaded %d MCP tools from %s", len(tools), path)
                return tools
    return []


def inject_mcp_tools(
    acp_request: ACPRequest,
    mcp_tools: List[ACPTool],
    deduplicate: bool = True,
) -> ACPRequest:
    """
    Merge *mcp_tools* into *acp_request.tools*, avoiding duplicates by name.

    The request's existing tools take precedence — MCP tools are appended
    so that explicitly user-supplied tools always appear first.
    """
    if not mcp_tools:
        return acp_request

    existing = list(acp_request.tools or [])
    if deduplicate:
        existing_names = {t.name for t in existing}
        new_tools = [t for t in mcp_tools if t.name not in existing_names]
    else:
        new_tools = list(mcp_tools)

    if not new_tools:
        return acp_request

    acp_request.tools = existing + new_tools
    logger.debug("Injected %d MCP tools into request (total: %d)", len(new_tools), len(acp_request.tools))
    return acp_request
