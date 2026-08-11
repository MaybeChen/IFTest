from browser_ai_test.metrics.statistics import calculate_statistics, percentile


def test_percentiles_linear_interpolation():
    values = [1, 2, 3, 4, 5]
    assert percentile(values, 50) == 3
    assert percentile(values, 90) == 4.6
    assert percentile(values, 95) == 4.8
    assert percentile(values, 99) == 4.96


def test_empty_percentile():
    assert percentile([], 50) is None


def test_empty_statistics():
    stats = calculate_statistics([])
    assert stats["total"] == 0
    assert stats["ttft_avg"] is None
    assert stats["stream_p99"] is None
