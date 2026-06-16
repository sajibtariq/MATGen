# SPDX-License-Identifier: GPL-3.0-or-later
# MATGen - Mobile Application Traffic Generator
# Copyright (C) 2022  RomARS (Mattia Quadrini) — original FWTG framework
# Copyright (C) 2026  Md Tariqul Islam
# See LICENSE for full terms
"""
tcp_client.py
Single-session HTTP traffic generator for MATGEN.

Usage:
    python tcp_client.py <profile> <duration_s> <server_ip> <server_port> \
                            <HTTP|HTTPS> <output_dir> [verbose] [client_id]

    profile    : social_engager | news_follower | content_consumer | shopper
    duration_s : emulation duration in seconds (default 300)
    verbose    : literal string "verbose" to enable per-request logging
    client_id  : integer identifier for this client (default 0)

app_numbers is always 1 (single session).
"""

import asyncio
import logging
import math
import os
import random
import sys
import threading
import time

import httpx
import numpy as np

from module.http_request import fetch_urls_concurrently
from module.utils.config import (
    User, Session,
    divide_time, random_category,
    SERVICE_CATEGORIES, INTERACTION_MODES,
)
from module.utils.rate_size_selection import (
    user_probabilities, user_activity,
    select_req_rate, select_size,
)
from module.utils.interaction_params import obtain_params
from module.utils.burst import BurstController
from module.utils.stats import EmulationStats, IMRecord

# ── constants ─────────────────────────────────────────────────────────────────
IM_NI = INTERACTION_MODES[0]   # 'non-interactive'
IM_I  = INTERACTION_MODES[1]   # 'interactive'
IM_FI = INTERACTION_MODES[2]   # 'full-interactive'

# ── globals ───────────────────────────────────────────────────────────────────
stats     = EmulationStats()   # EmulationStats is imported from module/utils/stats.py
terminate = threading.Event()


# ── helpers ───────────────────────────────────────────────────────────────────

# Called from run_emulation() — converts the CLI profile name into a User object
# with activity weights and service probabilities loaded from user_profiles.json.
def _build_user(profile: str) -> User:
    idx = {
        "social_engager": 0, "news_follower": 1,
        "content_consumer": 2, "shopper": 3,
    }[profile]
    u = User(profile)  # User is imported from module/utils/config.py
    u.add_activity(user_activity[idx])       # user_activity is imported from module/utils/rate_size_selection.py
    u.add_service(user_probabilities[idx])   # user_probabilities is imported from module/utils/rate_size_selection.py
    return u


# Called from run_emulation() — builds the base URL (http or https) used for every request.
def _base_url(conn_type: str, ip: str, port: int) -> str:
    scheme = "http" if conn_type == "HTTP" else "https"
    return f"{scheme}://{ip}:{port}/"


# Called from run_session() — advances the Markov chain to pick the next interaction mode.
def _next_im(current: str) -> str:
    """Deterministic Markov chain: NI → I → FI → (break)."""
    if current == "":
        return IM_NI
    if current == IM_NI:
        return str(random.choices([IM_NI, IM_I, IM_FI], weights=[0, 100, 0], k=1)[0])
    if current == IM_I:
        return str(random.choices([IM_NI, IM_I, IM_FI], weights=[0, 0, 100], k=1)[0])
    return None   # FI → session ends


# Called from run_interaction_mode() — returns the object-count thresholds that
# separate beginning / middle / end phases for one traffic direction.
def _phase_boundaries(total_requests: float) -> tuple:
    """Return (b1, b2) where b1=1/3 and b2=2/3 of total_requests."""
    return total_requests / 3, (total_requests / 3) * 2


# Called from run_interaction_mode() for every non-burst object — enforces the
# three data-cap layers: per-second, phase, and session.
def _cap_size(obj_size: float, current_sec: float, per_sec_limit: float,
              total_sent: float, session_cap: float,
              phase_sent: float, phase_cap: float) -> float:
    """
    Apply the three data-cap layers (per-second non-burst, session, phase).
    Returns the (possibly reduced) obj_size, minimum 1.
    """
    # per-second non-burst cap
    if current_sec <= per_sec_limit:
        if current_sec + obj_size > per_sec_limit:
            obj_size = per_sec_limit - current_sec
    else:
        obj_size = 1.0

    # phase cap
    if phase_sent <= phase_cap:
        if phase_sent + obj_size > phase_cap:
            obj_size = phase_cap - phase_sent
    else:
        obj_size = 1.0

    # session cap
    if total_sent <= session_cap:
        if total_sent + obj_size > session_cap:
            obj_size = session_cap - total_sent
    else:
        obj_size = 1.0

    return max(1.0, obj_size)


# Called from run_interaction_mode() each second — picks the active phase data cap
# based on how many objects have been sent so far vs the phase boundaries.
def _current_phase_cap(phase_caps: list, total_num: float, b1: float, b2: float) -> float:
    """Return the data cap for the current phase."""
    if total_num <= b1:
        return phase_caps[0]
    elif total_num <= b2:
        return phase_caps[1]
    return phase_caps[2]


# Called from run_interaction_mode() each second — splits the sampled total req_rate
# into a GET count and a POST count, giving priority to any active burst.
def _calculate_req_rates(
    total_rate: int,
    params,
    total_get: float, total_post: float,
    bc_get: BurstController, bc_post: BurstController,
) -> tuple:
    """
    Split total_rate into (get_req_rate, post_req_rate).
    Burst has priority; completion logic redirects all requests to the
    unfinished direction.
    """
    im_obj      = params.im_obj
    get_target  = params.get.total_requests
    post_target = params.post.total_requests
    max_total   = params.max_requests_per_second
    max_get_nb  = params.get.non_burst_req_max
    min_get_nb  = params.get.non_burst_req_min
    max_post_nb = params.post.non_burst_req_max
    min_post_nb = params.post.non_burst_req_min

    get_rate  = round(total_rate * (get_target / im_obj))
    post_rate = total_rate - get_rate

    get_rate  = min(get_rate,  max_get_nb,  max_total - post_rate)
    post_rate = min(post_rate, max_post_nb, max_total - get_rate)

    # burst priority overrides normal rate
    if bc_get.active and not bc_post.active:
        get_rate  = bc_get.burst_req_rate
        post_rate = min(max_total - get_rate,
                        random.randint(int(min_post_nb), int(max_post_nb)),
                        post_rate)

    elif bc_post.active and not bc_get.active:
        post_rate = bc_post.burst_req_rate
        get_rate  = min(max_total - post_rate,
                        random.randint(int(min_get_nb), int(max_get_nb)),
                        get_rate)

    elif bc_get.active and bc_post.active:
        if bc_get.burst_req_rate >= bc_post.burst_req_rate:
            get_rate  = bc_get.burst_req_rate
            post_rate = min(bc_post.burst_req_rate, max_total - get_rate)
        else:
            post_rate = bc_post.burst_req_rate
            get_rate  = min(bc_get.burst_req_rate,  max_total - post_rate)

    # completion: redirect to whichever direction still needs objects
    if total_get >= get_target and total_post < post_target:
        get_rate  = 0
        post_rate = total_rate
        if bc_post.active:
            post_rate = bc_post.burst_req_rate
        if total_post + post_rate > post_target:
            post_rate = post_target - total_post
            get_rate  = 0

    elif total_post >= post_target and total_get < get_target:
        get_rate  = total_rate
        post_rate = 0
        if bc_get.active:
            get_rate = bc_get.burst_req_rate
        if total_get + get_rate > get_target:
            get_rate  = get_target - total_get
            post_rate = 0

    elif total_get >= get_target and total_post >= post_target:
        get_rate = post_rate = 0

    return round(get_rate), round(post_rate)


# ── stop thread ───────────────────────────────────────────────────────────────

# Called from run_emulation() — launched in a daemon thread at startup.
# Blocks until terminate.set() is called, then prints stats and writes output CSVs.
def _stop_emulation(start_time: float, output_path: str, client_id: int):
    """Runs in a background thread; waits for terminate, then prints/exports stats."""
    terminate.wait()
    stats.print_summary(start_time, output_path)
    try:
        stats.export(output_path, client_id)
    except Exception as e:
        logging.error("Error exporting stats: %s", e)


# ── interaction mode ──────────────────────────────────────────────────────────

# Called from run_session() — drives the per-second request loop for one full IM
# (non-interactive, interactive, or full-interactive) and returns its IMRecord.
async def run_interaction_mode(
    client,
    session: Session,
    im_string: str,
    emulation_start: float,
    session_end: float,
    profile: str,
    base_url: str,
    verbose: bool,
    session_number: int,
) -> IMRecord:
    """Run one complete interaction mode and return its IMRecord."""


    #load  
    params = obtain_params(session, im_string)  # obtain_params is imported from module/utils/interaction_params.py

    get_boundaries  = _phase_boundaries(params.get.total_requests) 
    post_boundaries = _phase_boundaries(params.post.total_requests)

    bc_get  = BurstController(params.get)   # BurstController is imported from module/utils/burst.py
    bc_post = BurstController(params.post)

    total_get_num   = 0.0
    total_post_num  = 0.0
    n_obj           = 0

    total_data_get  = 0.0   # kB sent/received GET
    total_data_post = 0.0   # kB sent/received POST
    phase_data_get  = 0.0   # kB sent in current GET phase (resets on phase transition)
    phase_data_post = 0.0   # kB sent in current POST phase (resets on phase transition)
    current_phase_get  = 0  # 0=beginning 1=middle 2=end
    current_phase_post = 0

    im_record = IMRecord(           # IMRecord is imported from module/utils/stats.py
        session_number=session_number,
        app_category=session.category,
        im_name=params.im_name,
    )
    im_start = time.time()

    while n_obj < params.im_obj:
        if time.time() > session_end:
            break

        elapsed = time.time() - emulation_start
        req_rate = select_req_rate(session, im_string)  # select_req_rate is imported from module/utils/rate_size_selection.py

        # ── burst state ───────────────────────────────────────────────────────
        bc_get.update_state(total_get_num,  get_boundaries,  elapsed)
        bc_post.update_state(total_post_num, post_boundaries, elapsed)

        if bc_get.active:
            bc_get.init_timing(total_get_num, get_boundaries, elapsed)
            bc_get.tick()

        if bc_post.active:
            bc_post.init_timing(total_post_num, post_boundaries, elapsed)
            bc_post.tick()

        # ── idle second ───────────────────────────────────────────────────────
        if req_rate == 0:
            stats.record_idle_second()
            if verbose:
                print(f"| {elapsed:.3f} {profile} req_rate=0 — sleeping 1s")
            time.sleep(1)
            continue

        stats.record_rates(*_calculate_req_rates(
            req_rate, params, total_get_num, total_post_num, bc_get, bc_post
        ))
        get_rate, post_rate = _calculate_req_rates(
            req_rate, params, total_get_num, total_post_num, bc_get, bc_post
        )

        if verbose:
            print(
                f"| {elapsed:.3f} {profile} rate={req_rate} "
                f"(GET={get_rate} POST={post_rate}) "
                f"cat={session.category} IM={im_string} "
                f"obj={n_obj}/{int(params.im_obj)}"
            )

        # ── build request list ────────────────────────────────────────────────
        urls, sizes, methods = [], [], []
        sec_size_post = 0.0
        sec_size_get  = 0.0

        # phase caps — reset per-phase counter on phase transition (matches original)
        b1g, b2g = get_boundaries
        new_phase_get = 0 if total_get_num <= b1g else (1 if total_get_num <= b2g else 2)
        if new_phase_get != current_phase_get:
            phase_data_get = 0.0
            current_phase_get = new_phase_get

        b1p, b2p = post_boundaries
        new_phase_post = 0 if total_post_num <= b1p else (1 if total_post_num <= b2p else 2)
        if new_phase_post != current_phase_post:
            phase_data_post = 0.0
            current_phase_post = new_phase_post

        phase_cap_get  = _current_phase_cap(
            params.get.phase_data_caps, total_get_num, *get_boundaries)
        phase_cap_post = _current_phase_cap(
            params.post.phase_data_caps, total_post_num, *post_boundaries)

        # ── POST objects ──────────────────────────────────────────────────────
        n_post_this_sec = min(post_rate, int(params.post.total_requests - total_post_num))
        for _ in range(n_post_this_sec):
            if n_obj >= params.im_obj:
                break

            obj_size = float(select_size(session, im_string, "POST", "non_burst"))  # select_size is imported from module/utils/rate_size_selection.py

            if bc_post.active:
                obj_size *= bc_post.intensity
                obj_size  = bc_post.apply_burst_cap(obj_size, sec_size_post)
                bc_post.record_sent(obj_size)
            else:
                obj_size = _cap_size(
                    obj_size, sec_size_post,
                    params.post.non_burst_per_second_limit,
                    total_data_post, params.post.session_data_cap,
                    phase_data_post, phase_cap_post,
                )

            # enforce phase and session caps even in burst
            if phase_data_post + obj_size > phase_cap_post:
                obj_size = max(1.0, phase_cap_post - phase_data_post)
            if total_data_post + obj_size > params.post.session_data_cap:
                obj_size = max(1.0, params.post.session_data_cap - total_data_post)

            obj_size = max(1, round(obj_size))
            sec_size_post   += obj_size
            total_data_post += obj_size
            phase_data_post += obj_size
            total_post_num  += 1
            n_obj           += 1

            urls.append(base_url)
            sizes.append(obj_size)
            methods.append("POST")

        sec_size_post = 0.0   # reset per-second counter before GET loop

        # ── GET objects ───────────────────────────────────────────────────────
        n_get_this_sec = min(get_rate, int(params.get.total_requests - total_get_num))
        for _ in range(n_get_this_sec):
            if n_obj >= params.im_obj:
                break

            obj_size = float(select_size(session, im_string, "GET", "non_burst"))   # select_size is imported from module/utils/rate_size_selection.py

            if bc_get.active:
                obj_size *= bc_get.intensity
                obj_size  = bc_get.apply_burst_cap(obj_size, sec_size_get)
                bc_get.record_sent(obj_size)
            else:
                obj_size = _cap_size(
                    obj_size, sec_size_get,
                    params.get.non_burst_per_second_limit,
                    total_data_get, params.get.session_data_cap,
                    phase_data_get, phase_cap_get,
                )

            # enforce phase and session caps even in burst
            if phase_data_get + obj_size > phase_cap_get:
                obj_size = max(1.0, phase_cap_get - phase_data_get)
            if total_data_get + obj_size > params.get.session_data_cap:
                obj_size = max(1.0, params.get.session_data_cap - total_data_get)

            obj_size = max(1, round(obj_size))
            sec_size_get   += obj_size
            total_data_get += obj_size
            phase_data_get += obj_size
            total_get_num  += 1
            n_obj          += 1

            urls.append(base_url)
            sizes.append(obj_size)
            methods.append("GET")

        # ── fire all requests ─────────────────────────────────────────────────
        if not urls:
            time.sleep(1)
            continue

        tick_start = time.time()
        results = await fetch_urls_concurrently(client, [urls, sizes, methods])  # fetch_urls_concurrently is imported from module/http_request.py

        for result in results:
            if result is None:
                continue
            (status, elapsed_s, content_bytes,
             throughput, http_version,
             method, resp_time) = result

            content_kb = content_bytes / 1000
            if method == "GET":
                stats.record_get(content_kb, resp_time, params.im_name)
                im_record.n_get += 1
                im_record.data_get_kb += content_kb
            else:
                stats.record_post(content_kb, resp_time, params.im_name)
                im_record.n_post += 1
                im_record.data_post_kb += content_kb

            if verbose:
                print(
                    f"| {elapsed:.3f} {profile} {method} "
                    f"status={status} size={content_bytes}B "
                    f"elapsed={elapsed_s:.3f}s throughput={throughput:.3f}Mbps "
                    f"http={http_version}"
                )

        # sleep for the remainder of this 1-second window
        remaining = 1.0 - (time.time() - tick_start)
        if remaining > 0:
            await asyncio.sleep(remaining)

    im_record.total_objects = im_record.n_get + im_record.n_post
    im_record.duration_s    = time.time() - im_start
    return im_record


# ── session ───────────────────────────────────────────────────────────────────

# Called from run_emulation() — opens the HTTP client and steps through
# NI → I → FI for one app-category session.
async def run_session(
    user: User,
    session: Session,
    emulation_start: float,
    session_number: int,
    profile: str,
    base_url: str,
    conn_type: str,
    verbose: bool,
    single_cycle: bool = False,
):
    """Run one full app session (NI → I → FI)."""
    session_end = time.time() + session.duration
    im_string   = ""
    bool_http2  = conn_type != "HTTP"

    ssl_verify = False  # self-signed cert — skip verification to support any server IP
    async with httpx.AsyncClient(http2=bool_http2, verify=ssl_verify) as client:
        while time.time() < session_end:
            im_string = _next_im(im_string)
            if im_string is None:
                if single_cycle or time.time() >= session_end:
                    time.sleep(5)   # 5s idle at end of cycle
                    break
                im_string = IM_I  # replay FI: _next_im("I") → FI
                continue

            if verbose:
                elapsed = time.time() - emulation_start
                print(f"| {elapsed:.3f} {profile} — IM: {im_string}")

            record = await run_interaction_mode(
                client, session, im_string,
                emulation_start, session_end,
                profile, base_url, verbose, session_number,
            )
            stats.add_im_record(record)
            stats.im_times.append(record.duration_s)

            if time.time() > session_end:
                break


# ── emulation entry point ─────────────────────────────────────────────────────

# Called from main() via asyncio.run() — top-level async entry point.
# Builds the user, picks the session category, starts the stop thread, then calls run_session().
async def run_emulation(
    profile: str,
    emulation_time: int,
    server_ip: str,
    server_port: int,
    conn_type: str,
    output_path: str,
    verbose: bool,
    client_id: int,
    single_cycle: bool = False,
):
    emulation_start = time.time()
    base_url = _base_url(conn_type, server_ip, server_port)

    logging.info(f"Emulation started — profile={profile} duration={emulation_time}s")
    print(f"Emulation started — profile={profile} duration={emulation_time}s url={base_url}")

    user = _build_user(profile)

    # Single session: app_numbers = 1
    session_times = divide_time(emulation_time, 1)  # divide_time is imported from module/utils/config.py
    stats.n_sessions = 1
    stats.session_times = session_times

    th = threading.Thread(
        target=_stop_emulation,
        args=(emulation_start, output_path, client_id),
        daemon=True,
    )
    th.start()

    s_category = random_category(user, SERVICE_CATEGORIES)  # random_category is imported from module/utils/config.py
    session = Session(s_category, session_times[0])          # Session is imported from module/utils/config.py

    print(f"Session category: {s_category}  duration: {session_times[0]}s")
    print(f"User service weights: {user.service}")
    print("-" * 49)

    try:
        await run_session(
            user, session, emulation_start,
            session_number=1,
            profile=profile,
            base_url=base_url,
            conn_type=conn_type,
            verbose=verbose,
            single_cycle=single_cycle,
        )
    except Exception as e:
        logging.error("Error in run_session: %s", e)
        print(f"Error in run_session: {e}")

    terminate.set()
    th.join()


# ── CLI ───────────────────────────────────────────────────────────────────────

# Entry point — called by `if __name__ == "__main__"`.
# Parses CLI args and calls asyncio.run(run_emulation(...)).
def main():
    try:
        if len(sys.argv) > 1:
            profile     = sys.argv[1].lower()
            duration    = int(sys.argv[2])
            server_ip   = sys.argv[3]
            server_port = int(sys.argv[4])
            conn_type   = sys.argv[5]
            output_path = sys.argv[6]
            verbose      = len(sys.argv) > 7 and sys.argv[7] == "verbose"
            client_id    = int(sys.argv[8]) if len(sys.argv) > 8 else 0
            single_cycle = "single_cycle" in sys.argv
        else:
            # defaults for quick testing
            # NOTE: always use the local IP address of the server machine here
            profile      = "social_engager"
            duration     = 300
            server_ip    = "127.0.0.1"  # local IP address
            server_port  = 8443         # use 8443 for HTTPS without root permission
            conn_type    = "HTTPS"
            output_path  = "."
            verbose      = False
            client_id    = 0
            single_cycle = False
    except (IndexError, ValueError) as e:
        print(f"Argument error: {e}")
        print(__doc__)
        sys.exit(1)

    # Create a dedicated output subfolder: <output_dir>/client_<id>_<timestamp>/
    timestamp   = time.strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(output_path, f"client_{client_id}_{timestamp}")
    os.makedirs(output_path, exist_ok=True)

    logging.basicConfig(
        filename=os.path.join(output_path, "client.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    print("Emulation parameters:")
    print(f"  profile     : {profile}")
    print(f"  duration    : {duration}s")
    print(f"  server      : {conn_type} {server_ip}:{server_port}")
    print(f"  output      : {output_path}")
    print(f"  verbose      : {verbose}")
    print(f"  client_id    : {client_id}")
    print(f"  single_cycle : {single_cycle}")

    try:
        asyncio.run(run_emulation(
            profile, duration, server_ip, server_port,
            conn_type, output_path, verbose, client_id, single_cycle,
        ))
    except KeyboardInterrupt:
        logging.info("Emulation stopped by user.")
        terminate.set()


if __name__ == "__main__":
    main()
