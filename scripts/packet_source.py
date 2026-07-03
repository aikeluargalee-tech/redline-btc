"""Shared packet data fetcher — single source of truth for Redline BTC.

Reads from the Pipeline Dashboard V3 BTC Data Packet:
  https://aikeluargalee-tech.github.io/pipeline-dashboard-v3/packet/data.json

This aggregates 30+ pipeline JSON files + AMT feed into one JSON.
All Redline fetchers should use this as their primary data source.
"""

import json
import logging
import urllib.error
import urllib.request
from typing import Optional

PACKET_URL = (
    "https://aikeluargalee-tech.github.io/"
    "pipeline-dashboard-v3/packet/data.json"
)

logger = logging.getLogger(__name__)


def fetch_packet() -> Optional[dict]:
    """Fetch the BTC Data Packet JSON.

    Returns parsed dict or None on failure (with warning logged).
    """
    try:
        with urllib.request.urlopen(PACKET_URL, timeout=15) as r:
            data = json.loads(r.read())
        return data
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
        logger.warning("Packet fetch failed from %s: %s", PACKET_URL, e)
        return None
