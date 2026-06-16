# SPDX-License-Identifier: GPL-3.0-or-later
# MATGen - Mobile Application Traffic Generator
# Copyright (C) 2022  RomARS (Mattia Quadrini) — original FWTG framework
# Copyright (C) 2026  Md Tariqul Islam
# See LICENSE for full terms
"""
rate_size_selection.py
select_req_rate() and select_size() using a lookup table instead of 24+ if/elif branches.

Replaces rate_size_selection_2.py.
All CSV distributions are loaded once at import time.
"""

import logging
import random
import sys
import time

from .config import (
    SERVICE_CATEGORIES,
    INTERACTION_MODES,
    load_user_profiles,
    load_app_distributions,
    load_app_json,
    _CATEGORY_TO_APP,
)

# ── Load user profiles at import ──────────────────────────────────────────────
_user_service_weights, _user_activity_values = load_user_profiles()

user_probabilities = _user_service_weights   # index 0-3 matching profile order
user_activity      = _user_activity_values


# ── Load all CSV distributions at import ──────────────────────────────────────
# _DIST[category][im_name] = {'request_rate': (vals, probs), 'get_size': ..., 'post_size': ...}
_DIST = {}
for _cat in SERVICE_CATEGORIES:
    try:
        _DIST[_cat] = load_app_distributions(_cat)
    except SystemExit:
        raise

# ── IM name mapping: internal string → JSON key ───────────────────────────────
_IM_KEY = {
    INTERACTION_MODES[0]: "non_interactive",
    INTERACTION_MODES[1]: "interactive",
    INTERACTION_MODES[2]: "full_interactive",
}


def app_session(session) -> dict:
    """Load the full app JSON for the given session's category."""
    from .config import load_app_json
    return load_app_json(session.category)


def select_req_rate(session, im_string: str) -> int:
    """Sample a total request rate (GET + POST combined) for this second."""
    try:
        im_key = _IM_KEY[im_string]
        vals, probs = _DIST[session.category][im_key]["request_rate"]
        rate = int(random.choices(vals, weights=probs, k=1)[0])
        print(f"ReqRate: {rate}")
        return rate
    except Exception as e:
        logging.error(f"Error in select_req_rate: {e}")
        sys.exit()


def select_size(session, im_string: str, method: str, burst_type: str) -> int:
    """
    Sample an object size from the non-burst distribution.
    method     – 'GET' or 'POST'
    burst_type – always 'non_burst' (burst sizes are handled via scaling in the caller)
    """
    try:
        im_key = _IM_KEY[im_string]
        dist_key = "get_size" if method == "GET" else "post_size"
        vals, probs = _DIST[session.category][im_key][dist_key]
        return int(random.choices(vals, weights=probs, k=1)[0])
    except Exception as e:
        logging.error(f"Error in select_size: {e}")
        sys.exit()
