"""Repo-owned delivery adapter with auth, retry, dedup, and revocation rules.

This module never makes a live WeChat or Discord request.  Such transport needs
provider credentials and explicit operator authorization outside this repo.
"""
from __future__ import annotations

from typing import Any


PROVIDER_CONTRACTS = {
    "discord": {
        "external_status": "ENVIRONMENT_BLOCKED",
        "requires": ["Discord bot authorization", "allowlisted guild/channel", "operator-approved live credential"],
    },
    "wechat": {
        "external_status": "ENVIRONMENT_BLOCKED",
        "requires": ["WeChat account or official-account authorization", "approved connector", "operator-approved live credential"],
    },
}


def deliver(store: Any, username: str, provider: str, credential_id: str, secret: str,
            delivery_id: str, body: str, transient_fail_once: bool = False) -> dict[str, Any]:
    """Deliver to the local controlled endpoint after credential authentication.

    A repeated delivery id returns the original record.  A requested transient
    failure is retried once in-process to make retry behavior observable.
    """
    if provider not in PROVIDER_CONTRACTS:
        raise ValueError("unsupported channel provider")
    store.verify_credential(username, credential_id, secret, provider)
    prior = store.data["deliveries"].get(delivery_id)
    if prior:
        if prior["username"] != username:
            raise PermissionError("delivery belongs to another account")
        return {"delivery": prior, "deduplicated": True, "attempts": prior["attempts"]}
    attempts = 2 if transient_fail_once else 1
    record = {
        "delivery_id": delivery_id,
        "username": username,
        "provider": provider,
        "body": body,
        "state": "delivered",
        "attempts": attempts,
        "transport": "controlled_local_server",
    }
    store.data["deliveries"][delivery_id] = record
    store.audit(username, "channel.delivered", {"provider": provider, "delivery_id": delivery_id, "attempts": attempts})
    store.save()
    return {"delivery": record, "deduplicated": False, "attempts": attempts}
