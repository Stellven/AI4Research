# /daily-arxiv setup Management Boundary

## Proposed Changes

- Resolve or create config/daily-arxiv.yml from config/daily-arxiv.yml.example.
- Verify .github/workflows/daily-arxiv.yml env exposures for S2 and DeepXiv secrets.
- Report missing required secrets without reading secret values.

## Execution Boundary

- No protected config, workflow, secret, scheduler, SMTP, or wiki mutation was applied.
- Apply changes only through a separately approved execution path.
