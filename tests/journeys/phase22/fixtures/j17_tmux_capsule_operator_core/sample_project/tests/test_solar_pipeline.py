from solar_pipeline import MaterialCandidate, rank_candidates


def test_candidates_are_ranked_by_priority_score() -> None:
    ranked = rank_candidates(
        [
            MaterialCandidate("baseline", 1.1, 0.60, 0.2),
            MaterialCandidate("perovskite-a", 1.6, 0.82, 0.4),
            MaterialCandidate("oxide-b", 1.3, 0.91, 0.3),
        ]
    )

    assert [row["sample_id"] for row in ranked] == ["perovskite-a", "oxide-b", "baseline"]
    assert ranked[0]["priority_score"] == 1.312
