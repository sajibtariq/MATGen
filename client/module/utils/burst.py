# SPDX-License-Identifier: GPL-3.0-or-later
# MATGen - Mobile Application Traffic Generator
# Copyright (C) 2022  RomARS (Mattia Quadrini) — original FWTG framework
# Copyright (C) 2026  Md Tariqul Islam
# See LICENSE for full terms
"""
burst.py
BurstController encapsulates all burst state for one traffic direction (GET or POST).

One instance is created per direction per IM.  Each second the caller must:
  1. call update_state()   – may enter or exit a burst
  2. call tick()           – decrement countdown, update budget
  3. use .active, .burst_req_rate, .intensity for rate/size decisions
  4. call apply_burst_cap() for each object while .active
"""

import random
import time

from .im_params import DirectionParams


PHASES = ["beginning", "middle", "end"]


def _phase_index(total_num: float, b1: float, b2: float) -> int:
    """Return 0 (beginning), 1 (middle), or 2 (end)."""
    if total_num <= b1:
        return 0
    elif total_num <= b2:
        return 1
    return 2


def _per_second_budget(total_size: float, burst_time: int) -> list:
    """Distribute total_size evenly across burst_time seconds (piecewise linear)."""
    if burst_time == 1:
        return [total_size]
    points = [i * (total_size / burst_time) for i in range(1, burst_time)]
    return (
        [points[0]]
        + [points[i] - points[i - 1] for i in range(1, len(points))]
        + [total_size - points[-1]]
    )


class BurstController:
    """Manages all burst state for one traffic direction within an IM."""

    def __init__(self, params: DirectionParams):
        self._p = params

        # per-phase counters
        self._periods_used = [0, 0, 0]       # bursts fired per phase
        self._first_triggered = [False, False, False]  # first-burst flag per phase

        # burst activation state
        self.active = False
        self._timing_set = False             # burst duration/budget initialized
        self._end_elapsed = 0.0             # emulation elapsed seconds when burst ends
        self._last_end_wall = 0.0           # wall-clock time when last burst ended

        # per-second budget (set when burst starts, indexed by countdown)
        self._per_second_limit = []
        self._countdown = 0                 # seconds remaining in current burst

        # running totals for the current burst
        self._size_in_burst = 0.0           # total data sent this burst

        # per-second caps and intensity (updated each second)
        self.per_second_limit_value = 0.0   # budget for this second: _per_second_limit[_countdown]
        self.total_budget = 0.0             # max_burst_size_2
        self.burst_req_rate = 0             # request rate for this second in burst
        self.intensity = 0                  # size multiplier = burst_size_max / burst_req_max

    # ── public API ────────────────────────────────────────────────────────────

    def update_state(
        self,
        total_num: float,
        boundaries: tuple,
        emulation_elapsed: float,
    ):
        """
        Called once per second. Decides whether to enter or stay in a burst,
        and checks whether an active burst has expired.

        boundaries = (b1, b2) where b1 = im_duration/3 and b2 = 2*im_duration/3.
        """
        b1, b2 = boundaries
        phase_idx = _phase_index(total_num, b1, b2)
        phase = PHASES[phase_idx]
        p = self._p

        prob = p.burst_probability[phase]
        max_periods = p.burst_frequency[phase]
        req_max = p.burst_req_max[phase]
        req_min = p.burst_req_min[phase]

        # update intensity for this phase
        if req_max > 0:
            self.intensity = round(p.burst_size_max[phase] / req_max)

        if not self.active:
            self._try_enter(phase_idx, phase, prob, max_periods, req_min, req_max)
        else:
            self._check_exit(emulation_elapsed)

        if self.active:
            self.burst_req_rate = random.randint(int(req_min), int(req_max)) if req_max > 0 else 0

    def init_timing(self, total_num: float, boundaries: tuple, emulation_elapsed: float):
        """
        Called the first second of a new burst to set duration, budget, and
        per-second limit list.  Must be called after update_state() sets active=True.
        """
        if self._timing_set:
            return

        b1, b2 = boundaries
        phase_idx = _phase_index(total_num, b1, b2)
        phase = PHASES[phase_idx]
        p = self._p
        period_i = self._periods_used[phase_idx] - 1  # 0-based index

        burst_time = p.burst_duration[phase][period_i]
        burst_size = p.burst_size[phase][period_i]

        self._countdown = burst_time
        self._end_elapsed = emulation_elapsed + burst_time
        self.total_budget = burst_size
        self._per_second_limit = _per_second_budget(burst_size, burst_time)
        self._size_in_burst = 0.0
        self._timing_set = True

    def tick(self):
        """
        Called once per second while active, after init_timing().
        Decrements countdown and updates remaining budget for this second.
        """
        if not self.active or not self._timing_set:
            return
        remaining_budget = self.total_budget - self._size_in_burst
        self._countdown -= 1
        # per_second_limit_value is for the CURRENT second (indexed by countdown after decrement)
        if 0 <= self._countdown < len(self._per_second_limit):
            self.per_second_limit_value = self._per_second_limit[self._countdown]
        else:
            self.per_second_limit_value = remaining_budget

    def apply_burst_cap(
        self,
        obj_size: float,
        current_sec_size: float,
    ) -> float:
        """
        Cap obj_size so it does not exceed:
          1. per-second burst budget
          2. max_size_each_second from params
          3. remaining total burst budget

        Returns the (possibly reduced) obj_size.
        """
        # cap 1 – per-second burst budget
        if current_sec_size <= self.per_second_limit_value:
            if current_sec_size + obj_size > self.per_second_limit_value:
                obj_size = self.per_second_limit_value - current_sec_size
        else:
            return 1.0

        # cap 2 – max_size_each_second
        if current_sec_size <= self._p.max_size_each_second:
            if current_sec_size + obj_size > self._p.max_size_each_second:
                obj_size = self._p.max_size_each_second - current_sec_size
        else:
            return 1.0

        # cap 3 – total burst budget
        remaining = self.total_budget - self._size_in_burst
        if remaining <= 0:
            return 1.0
        if obj_size > remaining:
            obj_size = remaining

        return obj_size

    def record_sent(self, obj_size: float):
        """Must be called for each object sent during a burst."""
        self._size_in_burst += obj_size

    # ── private helpers ───────────────────────────────────────────────────────

    def _try_enter(self, phase_idx, phase, prob, max_periods, req_min, req_max):
        if not self._first_triggered[phase_idx]:
            # first attempt in this phase
            if self._periods_used[phase_idx] < max_periods:
                if random.random() < prob:
                    self._activate(phase_idx)
            else:
                self.active = False
        else:
            # subsequent attempts: respect interval
            if self._periods_used[phase_idx] < max_periods:
                intervals = self._p.burst_interval[phase]
                idx = self._periods_used[phase_idx]
                if isinstance(intervals, list) and idx < len(intervals) and intervals[idx] > 0:
                    wait = random.randint(1, int(intervals[idx]))
                else:
                    wait = 0
                if time.time() - self._last_end_wall >= wait:
                    if random.random() < prob:
                        self._activate(phase_idx)
            else:
                self.active = False

    def _activate(self, phase_idx):
        self.active = True
        self._size_in_burst = 0.0
        self._timing_set = False
        self._periods_used[phase_idx] += 1
        self._first_triggered[phase_idx] = True

    def _check_exit(self, emulation_elapsed: float):
        if emulation_elapsed > self._end_elapsed:
            self.active = False
            self._timing_set = False
            self._size_in_burst = 0.0
            self._last_end_wall = time.time()
