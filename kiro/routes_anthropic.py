# This file has been removed.
# The old Anthropic route handler called Kiro's private API directly.
# Use kiro/routes_anthropic_shim.py instead — it routes through ACP/kiro-cli.
raise ImportError(
    "kiro.routes_anthropic has been removed. Use kiro.routes_anthropic_shim, "
    "which routes all completions through kiro-cli via ACP."
)
