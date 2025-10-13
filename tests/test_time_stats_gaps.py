from deskcoach.utils.time_stats import accumulate_sit_stand_seconds


def test_long_gap_between_samples_is_capped_default():
    # Two samples 1 hour apart; default max_gap_sec=900 should cap attribution to 900s from first sample
    t0 = 1_700_000_000
    measurements = [
        (t0, 700),           # seated (below threshold)
        (t0 + 3600, 700),    # still seated
    ]
    seated, standing = accumulate_sit_stand_seconds(
        measurements=measurements,
        lock_intervals=[],
        stand_threshold_mm=900,
        end_ts=t0 + 3600,
    )
    assert seated == 900
    assert standing == 0


def test_tail_gap_is_capped_default():
    # Single sample with tail to end_ts; tail should be capped to 900 seconds
    t0 = 1_700_000_000
    measurements = [(t0, 1000)]  # standing (above threshold)
    seated, standing = accumulate_sit_stand_seconds(
        measurements=measurements,
        lock_intervals=[],
        stand_threshold_mm=900,
        end_ts=t0 + 7200,
    )
    assert seated == 0
    assert standing == 900


def test_lock_intervals_applied_within_capped_window():
    # Tail capped to 900s with a 300s lock interval inside; net attribution should be 600s standing
    t0 = 1_700_000_000
    measurements = [(t0, 1200)]  # standing
    locks = [(t0 + 300, t0 + 600)]  # 300 seconds locked inside the first 900s
    seated, standing = accumulate_sit_stand_seconds(
        measurements=measurements,
        lock_intervals=locks,
        stand_threshold_mm=900,
        end_ts=t0 + 5000,
    )
    assert seated == 0
    assert standing == 900 - 300

