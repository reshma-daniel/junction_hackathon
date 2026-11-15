"""A per-run RSSI reference, not a distance or direction measurement."""
import math
import time


class RssiPosition:
    def __init__(self, close_dbm=-80.0, power_drop=0.20, stale_s=3.0, clock=time.monotonic):
        if not 0 < power_drop < 1 or stale_s <= 0:
            raise ValueError("power_drop must be between 0 and 1 and stale_s positive")
        self.close_dbm = float(close_dbm)
        self.drop_db = -10 * math.log10(1 - power_drop)
        self.stale_s, self.clock = stale_s, clock
        self.initial = None
        self.current = None
        self.received_at = None

    def update(self, value) -> bool:
        if not isinstance(value, dict):
            return False
        if value.get("detected") is not True:
            self.current = self.received_at = None
            return False
        rssi, age = value.get("rssi_smoothed_dbm"), value.get("age_ms")
        if (isinstance(rssi, bool) or not isinstance(rssi, (int, float))
                or not math.isfinite(rssi) or not -127 <= rssi <= 20
                or isinstance(age, bool) or not isinstance(age, (int, float))
                or not math.isfinite(age) or not 0 <= age < self.stale_s * 1000):
            return False
        self.current = float(rssi)
        self.received_at = self.clock() - age / 1000
        if self.initial is None:
            self.initial = self.current
        return True

    @property
    def fresh(self):
        return self.current is not None and self.received_at is not None and self.clock() - self.received_at < self.stale_s

    @property
    def too_far(self):
        return (self.fresh and self.initial is not None and self.current < self.close_dbm
                and self.current <= self.initial - self.drop_db)

    @property
    def close(self):
        return self.fresh and self.current >= self.close_dbm

    def snapshot(self):
        return {"initial_rssi_dbm": self.initial, "rssi_dbm": self.current, "fresh": self.fresh,
                "return_below_dbm": None if self.initial is None else self.initial - self.drop_db}
