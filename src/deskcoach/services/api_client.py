"""HTTP client utilities for fetching desk height.

Expose a simple function get_height_mm(base_url) that returns the current
height in millimeters, fetching JSON like {"table_height": 79} (cm).
Includes a small retry loop and warning logs on failures.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

log = logging.getLogger(__name__)


def get_height_mm(base_url: str, *, timeout: float = 5.0, retries: int = 2) -> int:
    """Fetch current desk height in millimeters.

    Parameters
    ----------
    base_url: str
        Base URL of the API, e.g. http://host:port
    timeout: float
        Request timeout in seconds.
    retries: int
        Number of quick retries after the first attempt (total attempts = 1 + retries).

    Returns
    -------
    int
        Height in millimeters.

    Raises
    ------
    RuntimeError if all attempts fail or the response is invalid.
    """
    url = base_url.rstrip("/") + "/"
    last_err: Exception | None = None

    for attempt in range(1 + retries):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(url)
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()  # type: ignore[assignment]
                # Expected key "table_height" expressed in centimeters
                if "table_height" not in data:
                    raise KeyError("Missing 'table_height' in response JSON")
                cm = float(data["table_height"])  # may be int or float
                mm = int(round(cm * 10))  # convert centimeters to millimeters
                return mm
        except Exception as e:  # broad to log and retry
            last_err = e
            if attempt < retries:
                log.warning("API call failed (attempt %s/%s): %s", attempt + 1, 1 + retries, e)
                time.sleep(0.5)
            else:
                break

    assert last_err is not None
    log.warning("API call failed after %s attempts: %s", 1 + retries, last_err)
    raise RuntimeError(f"Failed to fetch height from {url}: {last_err}")
