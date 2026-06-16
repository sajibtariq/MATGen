# SPDX-License-Identifier: GPL-3.0-or-later
# MATGen - Mobile Application Traffic Generator
# Copyright (C) 2022  RomARS (Mattia Quadrini) — original FWTG framework
# Copyright (C) 2026  Md Tariqul Islam
# See LICENSE for full terms
"""
im_params.py
Simple classes that hold the parameters for one Interaction Mode (IM).

These replace the ~100-variable dictionary returned by the original obtain_params().
"""


class DirectionParams:
    """Parameters for one traffic direction (GET or POST) within an IM."""

    def __init__(
        self,
        total_requests,
        burst_probability,
        burst_frequency,
        burst_duration,
        burst_interval,
        burst_req_min,
        burst_req_max,
        burst_size,
        burst_size_max,
        non_burst_per_second_limit,
        max_size_each_second,
        max_size_each_second_non_burst,
        session_data_cap,
        phase_data_caps,
        non_burst_req_min,
        non_burst_req_max,
    ):
        self.total_requests              = total_requests
        self.burst_probability           = burst_probability           # dict {beginning, middle, end}
        self.burst_frequency             = burst_frequency             # dict {beginning, middle, end}
        self.burst_duration              = burst_duration              # dict of lists per phase
        self.burst_interval              = burst_interval              # dict of lists per phase
        self.burst_req_min               = burst_req_min               # dict per phase
        self.burst_req_max               = burst_req_max               # dict per phase
        self.burst_size                  = burst_size                  # dict of lists per phase
        self.burst_size_max              = burst_size_max              # dict per phase
        self.non_burst_per_second_limit  = non_burst_per_second_limit  # float, sampled once per IM
        self.max_size_each_second        = max_size_each_second        # float
        self.max_size_each_second_non_burst = max_size_each_second_non_burst
        self.session_data_cap            = session_data_cap            # float
        self.phase_data_caps             = phase_data_caps             # list [beginning, middle, end]
        self.non_burst_req_min           = non_burst_req_min
        self.non_burst_req_max           = non_burst_req_max


class IMParams:
    """All parameters for one Interaction Mode."""

    def __init__(self, im_name, im_obj, get, post, max_requests_per_second, max_time):
        self.im_name                 = im_name    # 'non_interactive' | 'interactive' | 'full_interactive'
        self.im_obj                  = im_obj     # total objects (get + post)
        self.get                     = get        # DirectionParams
        self.post                    = post       # DirectionParams
        self.max_requests_per_second = max_requests_per_second
        self.max_time                = max_time
