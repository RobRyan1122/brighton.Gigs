"""Year inference for venue listings that omit a year."""
from datetime import date


def resolve_month_day(month, day, reference_date, end_date=None, year=None):
    if year is not None:
        return date(year, month, day)
    # Prefer an actual occurrence in the requested interval, including leap days.
    for candidate_year in range(reference_date.year, (end_date or reference_date).year + 1):
        try:
            candidate = date(candidate_year, month, day)
        except ValueError:
            continue
        if reference_date <= candidate <= (end_date or reference_date):
            return candidate
    # Without an explicit range match, choose the nearest year to the reference.
    # This avoids turning last month's stale listings into next year's gigs.
    candidates = []
    for candidate_year in range(reference_date.year - 1, reference_date.year + 2):
        try:
            candidates.append(date(candidate_year, month, day))
        except ValueError:
            pass
    if not candidates:
        raise ValueError("Invalid month/day")
    return min(candidates, key=lambda value: (abs((value-reference_date).days), value < reference_date))
