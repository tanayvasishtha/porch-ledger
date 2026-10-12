from porch.evals.stitching import NOISE_LEVELS, run


def test_clean_days_are_scored_perfectly() -> None:
    result = run(days=3, scenarios_per_day=24, noise=NOISE_LEVELS["clean"], seed=7)
    assert result["accuracy"] == 1.0


def test_same_seed_gives_same_result() -> None:
    first = run(days=2, scenarios_per_day=12, noise=NOISE_LEVELS["harsh"], seed=11)
    second = run(days=2, scenarios_per_day=12, noise=NOISE_LEVELS["harsh"], seed=11)
    assert first == second
