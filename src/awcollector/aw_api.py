# C:\Users\gcave\Desktop\ColectorAW\src\awcollector\aw_api.py
from __future__ import annotations
import httpx
from typing import List, Dict, Any
from datetime import datetime

def _iso(dt: datetime) -> str:
    return dt.isoformat()

def _join(*parts: str) -> str:
    # Une pedazos de URL asegurando slashes correctos
    left = parts[0].rstrip("/")
    rest = [p.strip("/") for p in parts[1:]]
    return left + "/" + "/".join(rest) + ("/" if parts[-1].endswith("/") else "")

def list_buckets(client: httpx.Client, aw_base_url: str) -> List[Dict[str, Any]]:
    # NOTA: el endpoint correcto lleva slash final
    url = _join(aw_base_url, "buckets/")  # -> .../api/0/buckets/
    r = client.get(url)
    r.raise_for_status()
    return r.json()

def get_events(
    client: httpx.Client,
    aw_base_url: str,
    bucket_id: str,
    start: datetime,
    end: datetime,
    limit: int = 200000
) -> List[Dict[str, Any]]:
    url = _join(aw_base_url, f"buckets/{bucket_id}/events")
    params = {"start": _iso(start), "end": _iso(end), "limit": str(limit)}
    r = client.get(url, params=params)
    r.raise_for_status()
    return r.json()
