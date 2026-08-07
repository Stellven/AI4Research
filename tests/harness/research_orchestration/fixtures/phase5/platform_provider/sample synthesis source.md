# Phase 5 Platform Provider Resilience Fixture

## Abstract
This small source verifies that the production Solar research path can process a
local Markdown input when artifact roots, source paths, and repository paths
contain spaces.

## Method
The fixture describes a deterministic resilience check. The platform command
must preserve the input path, copy the source into the run artifact root, and
emit hash-checked artifacts through the normal Solar research runtime state.

## Results
The expected synthesis is a local, non-provider research lifecycle run with
traceable artifacts, a final runtime status, and no credential material in the
captured evidence.

## Limitations
This fixture is intentionally small. It proves path handling and orchestration
contract behavior, not live provider quality.
