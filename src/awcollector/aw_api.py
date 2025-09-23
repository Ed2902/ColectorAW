from __future__ import annotations
import httpx
from typing import List, Dict, Any, Tuple
from datetime import datetime, time, timedelta

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
    limit: int = 2000000  # “gigante” para efectos prácticos (un día)
) -> List[Dict[str, Any]]:
    url = _join(aw_base_url, f"buckets/{bucket_id}/events")
    params = {"start": _iso(start), "end": _iso(end), "limit": str(limit)}
    r = client.get(url, params=params)
    r.raise_for_status()
    return r.json()

# ====== Helpers de rango diario (hoy/ayer) ======

def _local_tz():
    """Devuelve la zona horaria local actual (aware)."""
    return datetime.now().astimezone().tzinfo

def _day_range_local(days_ago: int = 0) -> Tuple[datetime, datetime]:
    """
    Rango [start, end) para un día específico en hora local.
    days_ago=0 -> hoy 00:00 hasta mañana 00:00
    days_ago=1 -> ayer 00:00 hasta hoy 00:00
    """
    tz = _local_tz()
    base = datetime.now(tz) - timedelta(days=days_ago)
    start = datetime.combine(base.date(), time(0, 0, 0), tz)
    end = start + timedelta(days=1)
    return start, end

def yesterday_range_local() -> Tuple[datetime, datetime]:
    """Atajo para el rango de AYER (00:00 → 00:00 del día siguiente) en hora local."""
    return _day_range_local(days_ago=1)

# (Opcional) Wrapper directo si te resulta cómodo en la UI
def get_events_yesterday(
    client: httpx.Client,
    aw_base_url: str,
    bucket_id: str,
    limit: int = 2000000
) -> List[Dict[str, Any]]:
    """
    Devuelve eventos del bucket para el día de AYER en hora local.
    Útil si tu botón 'Enviar informe de ayer' quiere un acceso directo.
    """
    start, end = yesterday_range_local()
    return get_events(client, aw_base_url, bucket_id, start, end, limit=limit)
