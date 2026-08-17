# How CI judges a pull request

## The problem this replaces

The repository holds 885 test files. Continuous integration ran seven of them.

That is not a small gap, and it is invisible from the outside: a workflow that
runs seven files and goes green looks exactly like a workflow that runs
everything and goes green. The remaining files were neither passing nor failing.
Nobody knew which, because nothing ran them.

Running them all was not simply a matter of pointing CI at `tests/`. The suite
is not green, and it will not be green soon: it came from a fork that was
developed on without cleanup, so it contains tests that are stale, tests that
assert a contract the product deliberately changed, and tests that need
something a public runner cannot supply. A gate that demanded zero failures
would have to be switched off on day one, which puts the repository back where
it started.

## The rule

**A pull request is judged on what it changed, not on an absolute pass rate.**

Every test file runs. `tests/ci_baseline.json` records which tests were already
red. The gate compares the two, and every way of making a failure disappear
without fixing it is blocking:

| verdict | what it means |
| --- | --- |
| `NEW_FAILURE` | red now, not in the baseline |
| `BASELINE_ADDITION` | an entry this branch added to the baseline, compared against the same file on the base commit |
| `STALE_BASELINE` | a baseline entry with no matching test in the run, which is what deleting or renaming a failing test looks like |
| `UNRECORDED_FIX` | a baseline test that now passes; left recorded as red it is a hole it can regress into |
| `MISSING_SHARD` | a shard `tests/ci_lanes.json` declares produced no results |
| `UNEXPECTED_SHARD` | a shard reported that the manifest does not declare |
| `DUPLICATE_IDENTITY` | one test reported by two shards, so the shards are not a partition |
| `UNREADABLE_JUNIT` | a shard's XML did not parse |

The baseline may only shrink. It is a ratchet, and the ratchet is enforced
rather than requested: the gate reads `tests/ci_baseline.json` as of the base
commit and blocks any entry the branch added. Without that comparison, breaking
a test and adding it to the baseline in the same commit passes, and reads like
an ordinary baseline update in review.

Tests are compared by identity (`classname::name`), never by count. Two runs can
report the same number of failures and be failing entirely different tests; a
count-based comparison calls that "no change".

Shard identity comes from the `testsuite name` inside each JUnit document, not
from the file name, so a lost or renamed artifact cannot pass itself off as a
shard that ran. An aggregate case-count floor was tried first and is not enough:
losing a small shard leaves the total well inside any sane margin.

`tests/repository/governance/test_ci_gate.py` holds one adversarial test per row
of that table. Each was written after demonstrating the bypass against the real
script, and each is confirmed to fail through its own assertion when the
corresponding check is deleted.

## The lanes

`tests/ci_lanes.json` says which runner owns each file.

| lane | what it is |
| --- | --- |
| `pytest` | the default; anything pytest collects needs no entry |
| `script` | a `test_*.py` that is a program with `main()` and no test functions, so pytest collects nothing from it |
| `shell` | a bash test |
| `excluded` | not run in public CI, with the reason written down |

`scripts/check-test-census.py` fails if any test file falls outside all four.
That is what stops the gap from reopening: a new test file either runs, or
somebody wrote down why it cannot.

An `excluded` entry must say what the test needs that a public runner cannot
give: network access, an installed runtime under `~/.solar`, a terminal
multiplexer, a model provider, or a non-Linux host. "It fails" is not a reason
to exclude a test; that is what the baseline is for.

## Running it

```bash
# one shard, as CI runs it
python scripts/run-test-shard.py --lane pytest --shard 0 --of 6 --junit junit/pytest-0.xml

# the whole pytest lane in one process
python scripts/run-test-shard.py --lane pytest --shard 0 --of 1 --junit junit/all.xml

# the two gates
python scripts/check-test-census.py
python scripts/check-test-baseline.py junit/*.xml
```

## After you fix a test

```bash
python scripts/check-test-baseline.py junit/*.xml --update
```

Commit the result in the same pull request as the fix. The diff shows exactly
which test identities left the baseline, which is the evidence that the fix did
what it claimed.

Running `--update` to silence a test your change broke does not work: the gate
compares the baseline against the base commit and blocks added entries. The diff
shows it too, but the diff is not what stops it.

## Sharding

Shards are dealt round-robin over the sorted file list, so a given file lands in
the same shard on every run. This matters: if shard 3 held a different set of
files on two runs, comparing those runs would be meaningless.

`fail-fast` is off. A shard that is cancelled writes no JUnit, and a run missing
a shard's JUnit is indistinguishable from a run where that shard had nothing to
report. The expected shards are named in `tests/ci_lanes.json` under `shards`,
which the workflow matrix and the gate both read, so changing one without the
other fails instead of silently changing what CI covers.

## Dependencies

`requirements/ci.txt` pins exact versions rather than floors. A dependency that
resolves differently than it did when the baseline was recorded would move
tests, and a moved test is indistinguishable from a regression. Bump it
deliberately, in its own pull request, and regenerate the baseline there if the
bump moves anything.
