# SPDX-License-Identifier: AGPL-3.0-or-later
# MATGen - Mobile Application Traffic Generator
# Copyright (C) 2022  RomARS (Mattia Quadrini) — original FWTG framework
# Copyright (C) 2026  Md Tariqul Islam
# See LICENSE for full terms
"""
http_request.py
Async HTTP GET and POST helpers plus a concurrent batch dispatcher.

"""

import asyncio
import datetime
import logging
import random
import string


async def make_get(client, url: str, obj_size: int) -> tuple:
    """
    Send a GET request and return timing/size metrics.

    Returns:
        (status_code, elapsed_s, content_bytes, throughput_mbps,
         http_version, method, response_received_time)
    """
    params = {"size": obj_size}
    try:
        start = asyncio.get_event_loop().time()

        response = await client.get(url, params=params)

        end = asyncio.get_event_loop().time()
        response_received_time = datetime.datetime.now()

        elapsed_s = end - start
        content_bytes = len(response.content) if response.content else 0
        throughput_mbps = (content_bytes * 8 / 1_000_000) / elapsed_s

        return (
            response.status_code,
            elapsed_s,
            content_bytes,
            throughput_mbps,
            response.http_version,
            "GET",
            response_received_time,
        )
    except Exception as e:
        logging.error("Error in make_get: %s", e)
        return None


async def make_post(client, url: str, obj_size: int) -> tuple:
    """
    Send a POST request with a random-string body of `obj_size × 1000` chars.

    Returns the same 8-tuple as make_get.
    """
    # Build payload: 1 000-char random string repeated obj_size times
    chunk = "".join(
        random.choice(string.ascii_lowercase + string.punctuation + string.digits)
        for _ in range(1000)
    )
    body = chunk * int(obj_size)

    try:
        start = asyncio.get_event_loop().time()

        response = await client.post(url, data=body)

        end = asyncio.get_event_loop().time()
        response_received_time = datetime.datetime.now()

        elapsed_s = end - start
        content_bytes = len(response.content) if response.content else 0
        throughput_mbps = (content_bytes * 8 / 1_000_000) / elapsed_s

        return (
            response.status_code,
            elapsed_s,
            content_bytes,
            throughput_mbps,
            response.http_version,
            "POST",
            response_received_time,
        )
    except Exception as e:
        logging.error("Error in make_post: %s", e)
        return None


async def fetch_urls_concurrently(client, url_info: list) -> list:
    """
    Fire all requests in url_info concurrently using asyncio.gather().

    url_info = [url_list, size_list, method_list]

    Requests are staggered slightly to avoid all hitting the server at once.
    Returns a list of result tuples (same order as input).
    """
    urls, sizes, methods = url_info
    tasks = []

    for url, size, method in zip(urls, sizes, methods):
        # stagger: spread requests evenly across ~1 second
        stagger = (1 / len(urls)) - 0.03 if len(urls) > 0 else 0
        await asyncio.sleep(max(stagger, 0))

        if method == "GET":
            tasks.append(make_get(client, url, size))
        else:
            tasks.append(make_post(client, url, size))

    return await asyncio.gather(*tasks)
