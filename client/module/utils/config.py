# SPDX-License-Identifier: GPL-3.0-or-later
# MATGen - Mobile Application Traffic Generator
# Copyright (C) 2022  RomARS (Mattia Quadrini) — original FWTG framework
# Copyright (C) 2026  Md Tariqul Islam
# See LICENSE for full terms
"""
config.py
Paths, data-loading helpers, and simple model classes.

Paths, loaders, and model classes for the csv/ and json/ data layout.
"""

import csv
import json
import random
import sys
from pathlib import Path

# ── paths ─────────────────────────────────────────────────────────────────────
_BASE     = Path(__file__).parent.parent.parent        # matgenv1/client/
CSV_PATH  = _BASE.parent / "data" / "csv"             # matgenv1/data/csv/
JSON_PATH = _BASE.parent / "data" / "json"            # matgenv1/data/json/

# ── constants ─────────────────────────────────────────────────────────────────
SERVICE_CATEGORIES = ["news", "social_network", "entertainment", "e-commerce"]
INTERACTION_MODES  = ["non-interactive", "interactive", "full-interactive"]

# Mapping from service category to app folder name and JSON file
_CATEGORY_TO_APP = {
    "news":          "cnn",
    "social_network": "facebook",
    "entertainment": "tiktok",
    "e-commerce":    "amazon",
}

# ── model classes ─────────────────────────────────────────────────────────────

class User:
    def __init__(self, profile: str):
        self.profile = profile

    def add_activity(self, activity: int):
        self.activity = int(activity)

    def add_service(self, weights: list):
        self.service = weights


class Session:
    def __init__(self, category: str, duration: float):
        self.category = str(category)
        self.duration = float(duration)


# ── helpers ───────────────────────────────────────────────────────────────────

def divide_time(total_time: float, n_sessions: int) -> list:
    """Split total_time evenly into n_sessions durations."""
    return [total_time / n_sessions] * n_sessions


def random_category(user: User, categories: list) -> str:
    try:
        return str(random.choices(categories, weights=user.service, k=1)[0])
    except Exception as e:
        print("Error in random_category:", e)
        sys.exit()


def load_user_profiles() -> tuple:
    """
    Returns (service_weights, activity_values) for all four user profiles.
    service_weights[i] = [news%, social%, entertainment%, e-commerce%] for profile i.
    activity_values[i] = int frequency for profile i.
    Profile order: [social_engager, news_follower, content_consumer, shopper]
    """
    path = JSON_PATH / "user_profiles.json"
    try:
        data = json.loads(path.read_text())
        profiles = ["social_engager", "news_follower", "content_consumer", "shopper"]
        service_weights = [
            [data[p]["news"], data[p]["social_network"],
             data[p]["entertainment"], data[p]["e-commerce"]]
            for p in profiles
        ]
        activity_values = [int(data[p]["user_activity"]) for p in profiles]
        return service_weights, activity_values
    except FileNotFoundError:
        print(f"Error: user_profiles.json not found at {path}")
        sys.exit()


def load_app_json(category: str) -> dict:
    """Load the app JSON for the given service category."""
    app = _CATEGORY_TO_APP[category]
    path = JSON_PATH / f"{app}.json"
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        print(f"Error: {app}.json not found at {path}")
        sys.exit()


def load_csv_distribution(file_path) -> tuple:
    """
    Load a 2-column probability CSV.
    Returns (values, probabilities) as two lists of floats.
    """
    values, probs = [], []
    try:
        with open(file_path) as f:
            for row in csv.reader(f):
                values.append(float(row[0]))
                probs.append(float(row[1]))
        return values, probs
    except Exception as e:
        print(f"Error loading CSV {file_path}:", e)
        sys.exit()


def load_app_distributions(category: str) -> dict:
    """
    Load all six CSV distributions for one service category.
    Returns dict keyed by IM name × data type:
      {
        'non_interactive': {'request_rate': (vals, probs), 'get_size': ..., 'post_size': ...},
        'interactive':     {...},
        'full_interactive':{...},
      }
    """
    app = _CATEGORY_TO_APP[category]
    folder = CSV_PATH / app
    result = {}
    for im in ["non_interactive", "interactive", "full_interactive"]:
        result[im] = {
            "request_rate": load_csv_distribution(folder / f"request_rate_{im}.csv"),
            "get_size":     load_csv_distribution(folder / f"object_size_{im}_get.csv"),
            "post_size":    load_csv_distribution(folder / f"object_size_{im}_post.csv"),
        }
    return result
