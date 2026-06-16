# SPDX-License-Identifier: GPL-3.0-or-later
# MATGen - Mobile Application Traffic Generator
# Copyright (C) 2022  RomARS (Mattia Quadrini) — original FWTG framework
# Copyright (C) 2026  Md Tariqul Islam
# See LICENSE for full terms
"""
stats.py
EmulationStats replaces the ~30 global counters scattered across tcp_client.py.

Usage:
    stats = EmulationStats()
    stats.record_get(obj_size, elapsed_time)
    ...
    stats.export(output_path, client_id)
"""

import csv
import math
import time


class IMRecord:
    """Stats for one completed Interaction Mode within a session."""

    def __init__(self, session_number, app_category, im_name):
        self.session_number = session_number
        self.app_category   = app_category
        self.im_name        = im_name
        self.total_objects  = 0
        self.n_get          = 0
        self.n_post         = 0
        self.data_get_kb    = 0.0
        self.data_post_kb   = 0.0
        self.duration_s     = 0.0

    def avg_rate_get(self):
        return self.data_get_kb / self.duration_s if self.duration_s > 0 else 0.0

    def avg_rate_post(self):
        return self.data_post_kb / self.duration_s if self.duration_s > 0 else 0.0


class EmulationStats:
    """Collects and exports all emulation-wide statistics."""

    def __init__(self):
        # session / IM counts
        self.n_sessions: int = 0
        self.n_ims: int = 0
        self.n_total_objects: int = 0
        self.n_get: int = 0
        self.n_post: int = 0

        # per-second rate logs
        self.req_rate_get: list = []
        self.req_rate_post: list = []

        # per-object size logs
        self.obj_size_get: list = []
        self.obj_size_post: list = []

        # session and IM duration logs
        self.session_times: list = []
        self.im_times: list = []

        # completed IM records (for CSV export)
        self.im_records: list = []   # list[IMRecord]

        # response flow (for response_flow.csv)
        self._resp_timestamps: list = []
        self._resp_methods: list = []
        self._resp_ims: list = []
        self._resp_sizes: list = []


    # ── per-request recording ─────────────────────────────────────────────────

    def record_get(self, obj_size_kb: float, resp_time, im_name: str):
        self.n_get += 1
        self.n_total_objects += 1
        self.obj_size_get.append(obj_size_kb)
        self._resp_timestamps.append(resp_time)
        self._resp_methods.append("GET")
        self._resp_ims.append(im_name)
        self._resp_sizes.append(obj_size_kb)

    def record_post(self, obj_size_kb: float, resp_time, im_name: str):
        self.n_post += 1
        self.n_total_objects += 1
        self.obj_size_post.append(obj_size_kb)
        self._resp_timestamps.append(resp_time)
        self._resp_methods.append("POST")
        self._resp_ims.append(im_name)
        self._resp_sizes.append(obj_size_kb)

    def record_idle_second(self):
        """Called when req_rate == 0 (1-second wait)."""
        self.obj_size_get.append(0)
        self.obj_size_post.append(0)

    def record_rates(self, get_rate: int, post_rate: int):
        self.req_rate_get.append(get_rate)
        self.req_rate_post.append(post_rate)

    def add_im_record(self, record: IMRecord):
        self.n_ims += 1
        self.im_times.append(record.duration_s)
        self.im_records.append(record)

    # ── summary printing ──────────────────────────────────────────────────────

    def print_summary(self, start_time: float, output_path: str = None):
        import numpy as np
        duration = round(time.time() - start_time, 3)
        total_objs = self.n_total_objects or 1  # avoid div-by-zero

        lines = []
        lines.append(f"\n- Emulation terminated: {duration}s\n")
        lines.append("-" * 49)
        lines.append("STATISTICS FOR ENTIRE SESSION:\n")
        lines.append(f"Number of Sessions:          {self.n_sessions}")
        lines.append(f"Number of IMs:               {self.n_ims}")
        lines.append(f"Total Objects:               {self.n_total_objects}")
        lines.append(f"GET (%):                     {math.floor(self.n_get / total_objs * 100)}%")
        lines.append(f"POST (%):                    {math.floor(self.n_post / total_objs * 100)}%")
        if self.session_times:
            lines.append(f"Total Session Time:          {round(np.sum(self.session_times), 3)}s")
            lines.append(f"Average Session Time:        {round(np.mean(self.session_times), 3)}s")
        if self.im_times:
            lines.append(f"Total IM Duration:           {round(np.sum(self.im_times), 3)}s")
            lines.append(f"Average IM Duration:         {round(np.mean(self.im_times), 3)}s")
        lines.append(f"Total GET Requests:          {round(np.sum(self.req_rate_get), 3)}")
        lines.append(f"Total POST Requests:         {round(np.sum(self.req_rate_post), 3)}")
        total_size_get  = round(np.sum(self.obj_size_get), 3)
        total_size_post = round(np.sum(self.obj_size_post), 3)
        total_time      = round(np.sum(self.session_times), 3) if self.session_times else 1
        lines.append(f"Total Size GET:              {total_size_get} kB")
        lines.append(f"Total Size POST:             {total_size_post} kB")
        lines.append(f"Overall GET Data Rate:       {round(total_size_get / total_time, 3)} kB/s")
        lines.append(f"Overall POST Data Rate:      {round(total_size_post / total_time, 3)} kB/s")
        lines.append("-" * 49)
        lines.append("\nINTERACTION MODE DETAILS:\n")
        session_seen = set()
        for rec in self.im_records:
            if rec.session_number not in session_seen:
                lines.append(f"Session {rec.session_number} — category: {rec.app_category}")
                session_seen.add(rec.session_number)
            lines.append(f"  IM: {rec.im_name}")
            lines.append(f"    Objects: {rec.total_objects}  GET: {rec.n_get}  POST: {rec.n_post}")
            lines.append(f"    Data GET: {rec.data_get_kb:.2f} kB  POST: {rec.data_post_kb:.2f} kB")
            lines.append(f"    Time: {rec.duration_s:.3f}s  "
                         f"Rate GET: {rec.avg_rate_get():.2f} kB/s  POST: {rec.avg_rate_post():.2f} kB/s")
        lines.append("-" * 49)

        text = "\n".join(lines)
        print(text)

        if output_path:
            with open(f"{output_path}/session_summary.log", "w") as f:
                f.write(text + "\n")

    # ── CSV export ────────────────────────────────────────────────────────────

    def export(self, output_path: str, client_id: int):
        """Write per-session IM CSV files and response_flow.csv."""
        # group IM records by session
        sessions = {}
        for rec in self.im_records:
            sessions.setdefault(rec.session_number, []).append(rec)

        for session_num, records in sessions.items():
            filename = (
                f"{output_path}/client_id_{client_id}"
                f"_interaction_mode_info_session_{session_num}_info.csv"
            )
            with open(filename, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Interaction Mode Name",
                    "Total Number of Objects",
                    "Number of GET Requests",
                    "Number of POST Requests",
                    "Total Data Size (GET)",
                    "Total Data Size (POST)",
                    "Total Time",
                    "Average Data Rate (GET)",
                    "Average Data Rate (POST)",
                ])
                for rec in records:
                    writer.writerow([
                        rec.im_name,
                        rec.total_objects,
                        rec.n_get,
                        rec.n_post,
                        rec.data_get_kb,
                        rec.data_post_kb,
                        rec.duration_s,
                        rec.avg_rate_get(),
                        rec.avg_rate_post(),
                    ])

        # response_flow.csv
        with open(f"{output_path}/response_flow.csv", "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "method", "im", "size"])
            writer.writerows(zip(
                self._resp_timestamps,
                self._resp_methods,
                self._resp_ims,
                self._resp_sizes,
            ))
