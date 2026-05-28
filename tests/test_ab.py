from __future__ import annotations

from salesflow.eval.ab import default_price_variants, run_ab


def test_ab_is_deterministic_given_seed() -> None:
    variants = default_price_variants()
    a = run_ab(variants, n_per_variant=120, seed=11)
    b = run_ab(variants, n_per_variant=120, seed=11)
    assert [r.rate for r in a.results] == [r.rate for r in b.results]


def test_ab_recovers_best_variant_with_significance() -> None:
    report = run_ab(default_price_variants(), n_per_variant=300, seed=7)
    # The world's most persuasive rebuttal (smaller_entry, p=0.50) should win.
    assert report.best().name == "smaller_entry"
    by_name = {r.name: r for r in report.results}
    # Baseline is its own reference: zero lift, not flagged significant.
    assert by_name["baseline"].lift_vs_baseline == 0.0
    assert by_name["baseline"].significant is False
    # A clearly better variant beats baseline with statistical significance.
    assert by_name["smaller_entry"].lift_vs_baseline > 0
    assert by_name["smaller_entry"].significant is True


def test_ab_does_not_falsely_promote_a_marginal_variant() -> None:
    # social_proof is only marginally better than baseline; at this n it must
    # NOT clear the significance bar (guards against over-promotion).
    report = run_ab(default_price_variants(), n_per_variant=300, seed=7)
    by_name = {r.name: r for r in report.results}
    assert by_name["social_proof"].significant is False
