"""Acceptance tests. They fail until DEMO-41 and DEMO-42 are done."""

import math

import pytest

from stats import mean, median, stdev


def test_mean():
    assert mean([1, 2, 3, 4]) == 2.5


def test_mean_empty_raises():
    with pytest.raises(ValueError):
        mean([])


def test_median_odd():
    assert median([5, 1, 3]) == 3


def test_median_even():
    assert median([1, 2, 3, 4]) == 2.5


def test_median_empty_raises():
    with pytest.raises(ValueError):
        median([])


def test_stdev_is_sample_stdev():
    assert math.isclose(stdev([2, 4, 4, 4, 5, 5, 7, 9]), 2.138, rel_tol=1e-3)


def test_stdev_needs_two_values():
    with pytest.raises(ValueError):
        stdev([3])
