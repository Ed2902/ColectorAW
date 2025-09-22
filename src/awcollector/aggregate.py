# C:\Users\gcave\Desktop\ColectorAW\src\awcollector\aggregate.py
from __future__ import annotations
import os
import json
import socket
import getpass
from datetime import datetime, time
from typing import Dict, Any, List, Tuple, DefaultDict
from collections import defaultdict, Counter
from pathlib import Path

import httpx
import tldextract
from tzlocal import get_localzone

from .config import load_settings, PENDING_DIR, LOGS_DIR
from .aw_api import list_buckets, get_events


def _today_range_local() -> Tuple[datetime, datetime]:
    tz = get_localzone()
    now = datetime.now(tz)
    start = datetime.combine(now.date(), time(0, 0, 0)).astimezone(tz)
    end = now  # hasta “ahora”
    return start, end


def _duration(ev: Dict[str, Any]) -> float:
    # ActivityWatch suele incluir "duration" en segundos
    d = ev.get("duration")
    if isinstance(d, (int, float)):
        return float(d)
    # fallback seguro
    return 0.0


def _domain(url: str) -> str:
    try:
        ext = tldextract.extract(url)
        # incluir subdominio si existe (mail.google.com)
        parts = [p for p in [ext.subdomain, ext.domain, ext.suffix] if p]
        return ".".join(parts)
    except Exception:
        return "unknown"


def _pick_app(data: Dict[str, Any]) -> str:
    exe = (data.get("executable") or data.get("app") or "unknown").lower()
    return exe


def build_daily_payload(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Consulta AW y devuelve el payload de resumen diario."""
    aw_base = settings["aw_base_url"]
    timeout = settings["request_timeout_sec"]
    top_titles_n = int(settings["top_titles_limit"])
    top_urls_n = int(settings["top_urls_limit"])

    start, end = _today_range_local()

    active_sec = 0.0
    afk_sec = 0.0

    app_totals: DefaultDict[str, float] = defaultdict(float)
    app_titles: DefaultDict[str, Counter] = defaultdict(Counter)

    domain_totals: DefaultDict[str, float] = defaultdict(float)
    domain_urls: DefaultDict[str, Counter] = defaultdict(Counter)

    keys_count = 0.0
    mouse_dist = 0.0

    # Cliente HTTP
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        # listar buckets
        buckets = list_buckets(client, aw_base)

        # identificar buckets relevantes
        bucket_ids = [b["id"] if isinstance(b, dict) else b for b in buckets]  # tolerante
        afk_buckets = [b for b in bucket_ids if "aw-watcher-afk" in b]
        window_buckets = [b for b in bucket_ids if "aw-watcher-window" in b]
        web_buckets = [b for b in bucket_ids if "aw-watcher-web" in b]
        input_buckets = [b for b in bucket_ids if "aw-watcher-input" in b]

        # AFK: activo vs inactivo
        for bid in afk_buckets:
            events = get_events(client, aw_base, bid, start, end)
            for ev in events:
                dur = _duration(ev)
                status = (ev.get("data") or {}).get("status", "").lower()
                if status == "not-afk":
                    active_sec += dur
                else:
                    afk_sec += dur

        # WINDOW: apps + títulos
        for bid in window_buckets:
            events = get_events(client, aw_base, bid, start, end)
            for ev in events:
                dur = _duration(ev)
                data = ev.get("data") or {}
                app = _pick_app(data)
                title = (data.get("title") or "").strip() or "(sin título)"
                app_totals[app] += dur
                if title:
                    app_titles[app][title] += dur

        # WEB: dominios + urls
        for bid in web_buckets:
            events = get_events(client, aw_base, bid, start, end)
            for ev in events:
                dur = _duration(ev)
                data = ev.get("data") or {}
                url = (data.get("url") or "").strip()
                if not url:
                    continue
                dom = _domain(url)
                domain_totals[dom] += dur
                domain_urls[dom][url] += dur

        # INPUT: teclas y distancia mouse (si el watcher lo provee)
        for bid in input_buckets:
            events = get_events(client, aw_base, bid, start, end)
            for ev in events:
                data = ev.get("data") or {}
                # distintos watchers pueden usar nombres distintos; soportamos varios
                for key_name in ("keys", "keycount", "keypresses", "keystrokes"):
                    if isinstance(data.get(key_name), (int, float)):
                        keys_count += float(data[key_name])
                        break
                for mouse_name in ("mouse_distance", "mouse", "mouse_move_distance"):
                    if isinstance(data.get(mouse_name), (int, float)):
                        mouse_dist += float(data[mouse_name])
                        break

    # top N títulos por app y top N urls por dominio
    apps_list = []
    for app, total in sorted(app_totals.items(), key=lambda x: x[1], reverse=True):
        top_titles = [t for t, _ in app_titles[app].most_common(top_titles_n)]
        apps_list.append({"app": app, "total_sec": round(total, 2), "top_titles": top_titles})

    web_list = []
    for dom, total in sorted(domain_totals.items(), key=lambda x: x[1], reverse=True):
        top_urls = [u for u, _ in domain_urls[dom].most_common(top_urls_n)]
        web_list.append({"domain": dom, "total_sec": round(total, 2), "top_urls": top_urls})

    payload = {
        "date": datetime.now().date().isoformat(),
        "hostname": socket.gethostname(),
        "user": getpass.getuser(),
        "totals": {
            "active_sec": round(active_sec, 2),
            "afk_sec": round(afk_sec, 2),
            "keys": round(keys_count, 2),
            "mouse_dist": round(mouse_dist, 2),
        },
    # NOTE: puedes añadir más campos si quieres
        "apps": apps_list,
        "web": web_list,
        "meta": {
            "version": "v1",
            "source": "activitywatch",
            "generated_at": datetime.now().isoformat(),
        },
    }
    return payload


# ==== helpers de guardado ====

def _save_pending(payload: Dict[str, Any]) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    fname = f"payload-{payload.get('date','unknown')}-{ts}.json"
    path = PENDING_DIR / fname
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _desktop_dir() -> Path:
    # Funciona en Windows en español o inglés: %USERPROFILE%\Desktop
    return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"


def _save_to_desktop(payload: Dict[str, Any]) -> Path:
    fecha = payload.get("date") or "hoy"
    fname = f"reporte-{fecha}.json"
    path = _desktop_dir() / fname
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ==== envío al servidor ====

def send_payload(settings: Dict[str, Any], payload: Dict[str, Any]) -> Tuple[bool, str]:
    """POST al servidor.
    - 2xx: OK
    - 404 o cualquier otro fallo/exception: guardar en pending/ y también en Escritorio
    """
    url = settings["server_url"] + settings["ingest_path"]
    timeout = settings["request_timeout_sec"]
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            r = client.post(url, json=payload)
            if 200 <= r.status_code < 300:
                return True, "Enviado con éxito"
            # Cualquier no-2xx: guardar en pending y Escritorio
            _save_pending(payload)
            desk_path = _save_to_desktop(payload)
            return False, f"Error {r.status_code}. Copias en 'pending/' y Escritorio: {desk_path}"
    except Exception as e:
        # Error de red (ej. WinError 10061): también guardamos en ambos
        _save_pending(payload)
        desk_path = _save_to_desktop(payload)
        return False, f"Error de red: {e}. Copias en 'pending/' y Escritorio: {desk_path}"


# ==== reintento de pendientes ====

def resend_pending(settings: Dict[str, Any]) -> List[Tuple[Path, bool, str]]:
    """Intenta reenviar los archivos en pending/. Devuelve lista de (path, éxito, mensaje)."""
    results: List[Tuple[Path, bool, str]] = []
    files = sorted(PENDING_DIR.glob("payload-*.json"))
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            success, msg = send_payload(settings, data)
            if success:
                path.unlink()  # borrar si se envió con éxito
            results.append((path, success, msg))
        except Exception as e:
            results.append((path, False, f"Error leyendo o enviando: {e}"))
    return results
