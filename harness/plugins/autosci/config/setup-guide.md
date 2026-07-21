# Solar AutoSci Setup Guide

This setup route is intentionally non-mutating.  It documents environment
variables that may enable provider-backed AutoSci evidence paths; it does not
write secrets or credentials.

## Optional Provider Variables

- `OPENAI_API_KEY`: enables OpenAI-compatible Review LLM calls when explicitly configured.
- `AUTOSCI_REVIEW_LLM_PROVIDER`: set to `openai-compatible` to use the provider path.
- `AUTOSCI_REVIEW_LLM_MODEL`: defaults to `gpt-5.5` for Review LLM provider evidence.
- `AUTOSCI_REVIEW_LLM_ENDPOINT`: optional OpenAI-compatible endpoint override.
- `SEMANTIC_SCHOLAR_API_KEY`: optional Semantic Scholar API key for higher-rate S2 fetches.
- `DEEPXIV_API_URL`: optional DeepXiv-compatible search endpoint.
- `AUTOSCI_DISABLE_NETWORK_FETCH`: set to `1` to force source fetch helpers to emit inconclusive offline evidence.

## Safety Policy

Remote execution, SMTP delivery, destructive reset, browser rendering, and
long-running experiment launch require explicit approval and runtime evidence.
Setup must never write secrets automatically.
