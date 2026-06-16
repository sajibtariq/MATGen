# SPDX-License-Identifier: GPL-3.0-or-later
# MATGen - Mobile Application Traffic Generator
# Copyright (C) 2022  RomARS (Mattia Quadrini) — original FWTG framework
# Copyright (C) 2026  Md Tariqul Islam
# See LICENSE for full terms
"""
interaction_params.py
Returns an IMParams dataclass for the current interaction mode.

Replaces the original obtain_params() which unpacked ~100 variables into a flat dict.
"""

import random

from .config import load_app_json, SERVICE_CATEGORIES, INTERACTION_MODES
from .im_params import DirectionParams, IMParams

# Map the internal IM string to the JSON key
_IM_TO_KEY = {
    INTERACTION_MODES[0]: "non_interactive",
    INTERACTION_MODES[1]: "interactive",
    INTERACTION_MODES[2]: "full_interactive",
}


def _binarise(prob: float) -> float:
    """Treat any non-zero probability as 1 (original code behaviour)."""
    return 1.0 if prob != 0 else 0.0


def _load_direction(raw: dict, average_key: str) -> DirectionParams:
    """
    Build a DirectionParams from one direction block in the app JSON.
    average_key is 'max_size_each_second_non_burst' (same in both GET and POST).
    """
    avg_size = raw["max_size_each_second_non_burst"]
    # Sample the non-burst per-second limit once per IM (original behaviour)
    non_burst_limit = random.uniform(avg_size / 2, avg_size)

    return DirectionParams(
        total_requests=raw["total_requests"],

        burst_probability={
            ph: _binarise(raw["burst_probability"][ph])
            for ph in ["beginning", "middle", "end"]
        },
        burst_frequency=raw["burst_frequency"],
        burst_duration=raw["burst_duration"],
        burst_interval=raw["burst_interval"],
        burst_req_min=raw["burst_req_min"],
        burst_req_max=raw["burst_req_max"],
        burst_size=raw["burst_size"],
        burst_size_max=raw["burst_size_max"],

        non_burst_per_second_limit=non_burst_limit,
        max_size_each_second=raw["max_size_each_second"],
        max_size_each_second_non_burst=avg_size,

        session_data_cap=raw["session_data_cap"],
        phase_data_caps=raw["phase_data_caps"],

        non_burst_req_min=raw["non_burst_req_min"],
        non_burst_req_max=raw["non_burst_req_max"],
    )


def obtain_params(session, im_string: str) -> IMParams:
    """
    Load and return all parameters for the given session + interaction mode.

    session  – a Session object with .category
    im_string – one of INTERACTION_MODES ('non-interactive', 'interactive', 'full-interactive')
    """
    im_key = _IM_TO_KEY[im_string]
    app_data = load_app_json(session.category)
    im_block = app_data[im_key]

    get_dir  = _load_direction(im_block["get"],  "max_size_each_second_non_burst")
    post_dir = _load_direction(im_block["post"], "max_size_each_second_non_burst")

    return IMParams(
        im_name=im_key,
        im_obj=get_dir.total_requests + post_dir.total_requests,
        get=get_dir,
        post=post_dir,
        max_requests_per_second=im_block["max_requests_per_second"],
        max_time=im_block["max_time"],
    )
