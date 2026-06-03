# This file has been removed.
# Direct HTTP calls to Kiro's private API are not permitted.
# All completions route through kiro-cli via ACP (Agent Client Protocol).
# See kiro/acp_client.py for the compliant integration path.
raise ImportError(
    "kiro.http_client has been removed. Direct Kiro API access is not "
    "compliant. Use kiro/acp_client.py instead."
)
