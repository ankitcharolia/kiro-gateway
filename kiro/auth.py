# This file has been removed.
# Authentication is handled exclusively by the official kiro CLI.
# The gateway never touches Kiro credentials or internal APIs directly.
# See kiro/acp_client.py for the compliant integration path.
raise ImportError(
    "kiro.auth has been removed. All authentication is delegated to the "
    "kiro CLI subprocess. See kiro/acp_client.py."
)
