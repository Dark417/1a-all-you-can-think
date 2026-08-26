"""Tiny numeric core for the demo project.

Known issues (see the ticket tracker):
  DEMO-41  stdev() is missing
  DEMO-42  median() crashes on empty input
"""


def mean(values):
    return sum(values) / len(values)


def median(values):
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2
