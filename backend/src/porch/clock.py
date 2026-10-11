"""The real wall clock; tests and adapters inject fakes instead."""

import time

from porch.ports import Clock


class SystemClock(Clock):
    def now_ms(self) -> int:
        return int(time.time() * 1000)
