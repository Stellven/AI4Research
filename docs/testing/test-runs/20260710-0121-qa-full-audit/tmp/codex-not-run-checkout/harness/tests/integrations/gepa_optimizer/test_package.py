"""Package-level smoke tests: import safety and lazy resolution.

``test_import_has_no_side_effects`` checks that the *first* time the
package is loaded none of the heavy submodules are pulled in. Because
pytest collects multiple test files in one process, earlier tests may
have already imported those submodules — so we check the recorded
``__getattr__`` behaviour instead.
"""

from __future__ import annotations

import importlib
import sys


def test_package_loads_clean_and_exposes_version_and_all():
    import integrations.gepa_optimizer as g
    assert g.__version__
    assert isinstance(g.__all__, list) and g.__all__


def test_lazy_resolution_does_not_load_submodule_until_accessed():
    """Force a fresh load and check the __getattr__ contract."""
    # Strip any cached module entries so we exercise the cold path.
    for name in list(sys.modules):
        if name == "integrations.gepa_optimizer" or name.startswith(
            "integrations.gepa_optimizer."
        ):
            sys.modules.pop(name)

    g = importlib.import_module("integrations.gepa_optimizer")
    # Right after import, no submodule should be loaded yet.
    assert "integrations.gepa_optimizer.evaluator" not in sys.modules
    assert "integrations.gepa_optimizer.promote" not in sys.modules

    # First attribute access materialises the submodule.
    _ = g.SubprocessEvaluator
    assert "integrations.gepa_optimizer.evaluator" in sys.modules


def test_all_public_symbols_resolve():
    import integrations.gepa_optimizer as g
    for name in g.__all__:
        if name == "__version__":
            continue
        assert getattr(g, name) is not None, f"public symbol {name} did not resolve"


def test_attribute_error_on_unknown_name():
    import integrations.gepa_optimizer as g
    try:
        _ = g.NotARealSymbol
    except AttributeError:
        return
    raise AssertionError("expected AttributeError for unknown symbol")
