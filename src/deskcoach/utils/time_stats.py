from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

# Types
# Measurement rows are pairs (timestamp_sec, height_mm)
Measurement = Tuple[int, int]
# Lock intervals are half-open ranges [start_ts, end_ts)
LockInterval = Tuple[int, int]


def _overlap_len(a0: int, a1: int, b0: int, b1: int) -> int:
    """Return the length of overlap between [a0, a1) and [b0, b1)."""
    return max(0, min(a1, b1) - max(a0, b0))


def _subtract_locked(seg_start: int, seg_end: int, lock_intervals: Sequence[LockInterval]) -> int:
    """Given a segment [seg_start, seg_end), subtract any locked sub-intervals and
    return the effective unlocked length. Assumes lock_intervals are within the
    same broader window and can be unordered.
    """
    length = max(0, seg_end - seg_start)
    if length == 0 or not lock_intervals:
        return length
    cut = 0
    for l0, l1 in lock_intervals:
        cut += _overlap_len(seg_start, seg_end, l0, l1)
        if cut >= length:
            return 0
    return max(0, length - cut)


def accumulate_sit_stand_seconds(
    measurements: Sequence[Measurement],
    lock_intervals: Sequence[LockInterval],
    stand_threshold_mm: int,
    end_ts: int,
) -> Tuple[int, int]:
    """Accumulate seated and standing seconds for the provided measurements until end_ts.

    Attribution rules:
    - Each interval between consecutive samples is attributed to the state of the earlier sample.
    - The trailing interval from the last sample to end_ts is attributed to the last sample's state.
    - Any time overlapped by lock_intervals is excluded.

    Parameters
    ----------
    measurements: a sequence of (ts, height_mm), sorted ascending by ts. Duplicates and non-monotonic
                  sequences are tolerated (non-increasing steps are skipped).
    lock_intervals: list of [start, end) timestamps during which time should be excluded.
    stand_threshold_mm: height in mm at/above which a sample is considered standing.
    end_ts: inclusive window end boundary (tail interval ends at this timestamp).

    Returns
    -------
    (seated_seconds, standing_seconds)
    """
    if end_ts <= 0 or not measurements:
        return 0, 0

    seated = 0
    standing = 0
    thr = int(stand_threshold_mm)

    # Attribute consecutive sample intervals
    for i in range(len(measurements) - 1):
        t0, h0 = measurements[i]
        t1, _ = measurements[i + 1]
        if t1 <= t0:
            continue
        effective = _subtract_locked(t0, t1, lock_intervals)
        if effective <= 0:
            continue
        if h0 >= thr:
            standing += effective
        else:
            seated += effective

    # Tail from last sample to end_ts
    last_ts, last_h = measurements[-1]
    if end_ts > last_ts:
        effective = _subtract_locked(last_ts, end_ts, lock_intervals)
        if effective > 0:
            if last_h >= thr:
                standing += effective
            else:
                seated += effective

    return seated, standing
