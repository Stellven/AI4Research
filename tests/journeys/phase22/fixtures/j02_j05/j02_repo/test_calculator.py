from calculator import run


def test_run_returns_sum():
    assert run(2, 3) == 5
    assert run(-1, 1) == 0
