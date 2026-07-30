from __future__ import annotations


def eligible_discount(user: dict[str, object]) -> int:
    """Return the checkout discount percentage for one user."""
    tier = str(user.get("tier", "")).lower()
    if tier == "enterprise":
        return 30
    if tier == "pro":
        return 20
    if user.get("is_trial"):
        return 0
    return 5
