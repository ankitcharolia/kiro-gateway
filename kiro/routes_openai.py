# This file has been removed.
# The old OpenAI route handler called Kiro's private API directly.
# Use kiro/routes_openai_shim.py instead — it routes through ACP/kiro-cli.
raise ImportError(
    "kiro.routes_openai has been removed. Use kiro.routes_openai_shim, "
    "which routes all completions through kiro-cli via ACP."
)
