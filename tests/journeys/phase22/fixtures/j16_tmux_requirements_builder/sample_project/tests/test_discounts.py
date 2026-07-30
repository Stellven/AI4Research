from __future__ import annotations

from discounts import eligible_discount


def test_trial_accounts_never_receive_paid_tier_discount() -> None:
    assert eligible_discount({"tier": "pro", "is_trial": True}) == 0
    assert eligible_discount({"tier": "enterprise", "is_trial": True}) == 0


def test_paid_tier_discounts_for_non_trial_accounts() -> None:
    assert eligible_discount({"tier": "pro", "is_trial": False}) == 20
    assert eligible_discount({"tier": "enterprise", "is_trial": False}) == 30


def test_default_discount_for_non_trial_standard_account() -> None:
    assert eligible_discount({"tier": "standard", "is_trial": False}) == 5
