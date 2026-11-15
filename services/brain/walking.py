"""Story-owned walking: no serial I/O and no autonomous start outside a walk episode."""
import time

from services.position.rssi import RssiPosition


class RssiWalk:
    def __init__(self, position: RssiPosition, pwm=255, motion_stale_s=3.0,
                 reversal_s=0.2, clock=time.monotonic):
        if not 0 <= pwm <= 255 or motion_stale_s <= 0 or reversal_s < 0:
            raise ValueError("invalid walking configuration")
        self.position, self.pwm, self.clock = position, int(pwm), clock
        self.motion_stale_s, self.reversal_s = motion_stale_s, reversal_s
        self.enabled = False
        self.phase = "idle"
        self.moving = None
        self.motion_at = None
        self.output = 0
        self._sign = 0
        self._resume_at = 0.0

    def on_motion(self, sample):
        changed = sample.moving is not None and sample.moving != self.moving
        self.motion_at = self.clock()
        if sample.moving is not None:
            self.moving = sample.moving
        if self.enabled and self.phase == "approach" and changed and self.moving:
            self.phase = "lead"
        # Still reports never trigger return. IMU cannot interrupt an RSSI return.

    def start(self):
        if not self.enabled:
            self.enabled = True
            self.phase = "lead" if self.moving is True else "approach"

    def stop(self):
        self.enabled = False
        self.phase = "idle"
        self.output = self._sign = 0
        self._resume_at = 0.0

    def tick(self):
        now = self.clock()
        healthy = (self.position.fresh and self.motion_at is not None
                   and now - self.motion_at < self.motion_stale_s and self.moving is not None)
        if not self.enabled or not healthy:
            self.output = 0
            return self.output
        if self.phase == "lead" and self.position.too_far:
            self.phase = "return"
        elif self.phase == "return" and self.position.close:
            self.phase = "lead"
        wanted = self.pwm if self.phase in ("approach", "return") else -self.pwm
        sign = 1 if wanted > 0 else -1 if wanted < 0 else 0
        if sign != self._sign:
            if self._sign:
                self._resume_at = now + self.reversal_s
            self._sign = sign
        self.output = 0 if now < self._resume_at else wanted
        return self.output

    def snapshot(self):
        return {"phase": self.phase, "speed": self.output, "enabled": self.enabled,
                "moving": self.moving, **self.position.snapshot()}
