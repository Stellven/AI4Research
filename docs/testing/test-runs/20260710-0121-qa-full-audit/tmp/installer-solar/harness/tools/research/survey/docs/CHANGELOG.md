# Survey Gates Changelog

## S01 Requirements

- Captured source quality as more than URL count.
- Required authority distribution and anti-stuffing checks.
- Required argument density across five reasoning dimensions.
- Required controversy and negative evidence handling.
- Required multi-direction exploration with elimination reasons.

## S02 Architecture

- Defined package-first gate registry boundaries.
- Defined dataclass contracts for source quality and argument density.
- Defined contradiction matrix and claim-evidence link contracts.
- Defined exploration run and elimination record contracts.
- Defined gate report aggregation and partial verdict behavior.

## S03 Core Runtime

- Added append-only survey schema dataclasses.
- Added package-local gate registry.
- Added source quality distribution gate.
- Added argument density gate.
- Added controversy matrix gate.
- Added deterministic exploration package.
- Added gate report aggregator and runner hook.

## S04 Orchestration UI

- Added source quality CLI formatter.
- Added argument density CLI formatter.
- Added contradiction matrix CLI formatter.
- Added exploration CLI formatter.
- Added gate report CLI formatter.
- Added view registry for pluggable surfaces.
- Added epic status and dispatch hint modules.

## S05 Verification Release

- Added deterministic smoke fixture artifacts.
- Added negative control tests.
- Added activation proof artifacts.
- Added package documentation.
- Added release handoff requirements.
- Kept production rollout and live LLM verification deferred.

