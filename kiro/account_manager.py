# This file has been removed.
# Multi-account pooling and credential management are not permitted.
# kiro-gateway operates with a single kiro CLI session (single account).
# See kiro/compliance.py for the single-account enforcement.
raise ImportError(
    "kiro.account_manager has been removed. Multi-account pooling is not "
    "compliant with Kiro ToS. Use a single authenticated kiro CLI session."
)
