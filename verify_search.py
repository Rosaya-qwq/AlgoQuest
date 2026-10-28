"""Run the real search and image download path without sending QQ messages."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

import httpx
import nonebot


async def verify(query: str, repeat: int) -> bool:
    from bot.plugins.web_search import _download_image
    from bot.services.web_search import SEARCH_PIPELINE_VERSION, search_web

    print(f"Source: {Path(__file__).resolve().parent}; pipeline: {SEARCH_PIPELINE_VERSION}")
    success = True
    for attempt in range(1, repeat + 1):
        print(f"Verification {attempt}/{repeat}", flush=True)
        try:
            reply = await search_web(query)
            print(reply.text, flush=True)
            downloaded = 0
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
                for index, url in enumerate(reply.image_urls, start=1):
                    data, suffix = await _download_image(client, url)
                    downloaded += 1
                    print(f"Image {index}: {len(data)} bytes, {suffix}", flush=True)
            if not downloaded:
                success = False
            print(f"Verified downloads: {downloaded}", flush=True)
        except Exception as exc:
            # Do not print exception URLs, headers, API keys, or model reasoning.
            print(f"Verification failed: {type(exc).__name__}", flush=True)
            success = False
    return success


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", default="帮我找一张海泽莉塔的图片")
    parser.add_argument("--repeat", type=int, choices=range(1, 6), default=1)
    args = parser.parse_args()
    os.chdir(Path(__file__).resolve().parent)
    nonebot.init()
    raise SystemExit(0 if asyncio.run(verify(args.query, args.repeat)) else 1)
