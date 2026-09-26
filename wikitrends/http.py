"""Thin urllib wrapper: mandatory User-Agent, retries, readable errors."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from . import USER_AGENT


class ApiError(Exception):
    """API call error with a hint on what to do next."""

    def __init__(self, message: str, hint: str = "", status: int | None = None):
        super().__init__(message)
        self.hint = hint
        self.status = status


def get_json(
    url: str,
    params: dict | None = None,
    *,
    retries: int = 3,
    timeout: int = 30,
) -> dict:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})

    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # A Pageviews 404 means "no data", not a failure, so raise right away.
            if exc.code == 404:
                raise ApiError(
                    f"404: no data ({url})",
                    hint="Check the article title and period: per-article data starts on 2015-07-01.",
                    status=404,
                ) from exc
            if exc.code == 429 or exc.code >= 500:
                last_error = exc
                time.sleep(2**attempt)
                continue
            raise ApiError(
                f"HTTP {exc.code} for {url}",
                hint="Check the request parameters.",
                status=exc.code,
            ) from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(2**attempt)

    raise ApiError(
        f"Failed to fetch {url}: {last_error}",
        hint="Looks like a network problem. Retry later.",
    )


def encode_title(title: str) -> str:
    """Article title for the REST endpoint: spaces → _, slashes escaped."""
    return urllib.parse.quote(title.replace(" ", "_"), safe="")
