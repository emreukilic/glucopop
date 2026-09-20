"""What the alert engine must never get wrong.

`classify` decides whether a number is an emergency, and until now nothing tested it. Every case
below failed before 0.2.1 — two of them in the direction that matters most, where something
dangerous was quietly downgraded to something calm.
"""

from __future__ import annotations

import time

import pytest

from glucopop.config import DEFAULTS
from glucopop.alerts import AlertEngine
from glucopop.sources.base import Reading


def engine(**over):
    cfg = dict(DEFAULTS)
    cfg.update(over)
    return AlertEngine(cfg)


def reading(mgdl: float, age_min: float = 1.0) -> Reading:
    return Reading(mgdl=mgdl, timestamp=time.time() - age_min * 60)


def test_a_value_it_cannot_compare_is_never_called_normal():
    # every comparison against NaN is false, so this used to fall through to "ok" — drawn as if
    # the reading were in range, with no alert of any kind
    assert engine().classify(reading(float("nan"))) != "ok"


@pytest.mark.parametrize("mgdl,state", [
    (54, "urgent_low"), (55, "low"), (56, "low"),
    (89, "low"), (90, "ok"), (91, "ok"),
    (179, "ok"), (180, "ok"), (181, "high"),
])
def test_the_thresholds_one_value_either_side(mgdl, state):
    assert engine().classify(reading(mgdl)) == state


def test_an_urgent_low_stays_urgent_after_it_goes_stale():
    """A feed a few minutes behind is ordinary; being hypo unannounced because of it is not."""
    e = engine()
    assert e.classify(reading(38, age_min=16)) == "urgent_low"
    assert e.classify(reading(38, age_min=29)) == "urgent_low"


def test_but_not_forever_past_twice_the_threshold_the_sensor_is_the_story():
    assert engine().classify(reading(38, age_min=31)) == "stale"


def test_an_ordinary_low_still_yields_to_staleness():
    e = engine()
    assert e.classify(reading(85, age_min=14)) == "low"
    assert e.classify(reading(85, age_min=16)) == "stale"


def test_the_staleness_boundary_itself():
    e = engine()
    assert e.classify(reading(120, age_min=14)) == "ok"
    assert e.classify(reading(120, age_min=16)) == "stale"


def test_an_urgent_low_repeats_on_the_fast_schedule():
    """The downgrade cost this too: stale repeats at ten minutes, urgent low at five."""
    e = engine(repeat_minutes=15)
    assert e.should_notify("urgent_low") is True      # first one always fires
    assert e.should_notify("urgent_low") is False     # and not again immediately
    e._last_notify = time.time() - 6 * 60
    assert e.should_notify("urgent_low") is True      # but after five minutes, yes
