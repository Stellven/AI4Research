BASELINE_UNSUPPORTED = [5, 4, 5, 6]
INTERVENTION_UNSUPPORTED = [2, 1, 2, 1]


def mean(values):
    return sum(values) / len(values)


def unsupported_claim_reduction_percent():
    baseline = mean(BASELINE_UNSUPPORTED)
    intervention = mean(INTERVENTION_UNSUPPORTED)
    return ((baseline - intervention) / baseline) * 100.0
