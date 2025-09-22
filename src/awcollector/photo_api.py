# C:\Users\gcave\Desktop\ColectorAW\src\awcollector\photo_api.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, Optional, Tuple, List
import json
import shutil
import mimetypes
from datetime import datetime

import httpx

from .config import (
    load_settings,
    PENDING_PHOTOS_DIR,
    PENDING_PHOTOS_FILES_DIR,
)


# ========== helpers internos ==========

def _now_ts() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _mime_for(path: Path) -> str:
    mt, _ = mimetypes.guess_type(str(path))
    return mt or "application/octet-stream"


def _endpoint_url(settings: Dict) -> str:
    base = str(settings.get("photo_api_url", "")).rstrip("/")
    path = "/" + str(settings.get("photo_ingest_path", "")).lstrip("/")
    return f"{base}{path}"


def _copy_into_pending_files(src: Path) -> Optional[Path]:
    """
    Copia el archivo original dentro de pending/photos/files/ para garantizar reintentos,
    incluso si el usuario mueve o borra el archivo original. Devuelve la ruta de la copia.
    """
    try:
        PENDING_PHOTOS_FILES_DIR.mkdir(parents=True, exist_ok=True)
        dst = PENDING_PHOTOS_FILES_DIR / f"{_now_ts()}_{src.name}"
        shutil.copy2(src, dst)
        return dst
    except Exception:
        return None


def _save_photo_pending(meta: Dict) -> Path:
    """
    Guarda un JSON de pendiente en pending/photos/, con metadatos suficientes para reintento.
    Espera que meta incluya:
    - endpoint (str)
    - headers (dict)
    - fields (dict)
    - file_path (str)  -> ruta original
    - file_copy (str|None) -> copia en pending/photos/files/ si existe
    - info opcional (status_code, error, etc.)
    """
    jname = f"photo-{_now_ts()}.json"
    jpath = PENDING_PHOTOS_DIR / jname
    jpath.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return jpath


def _validate_photo(settings: Dict, photo_path: Path) -> Optional[str]:
    """
    Devuelve un string con mensaje de error si hay problema; si todo OK, devuelve None.
    """
    if not photo_path:
        return "No se especificó un archivo de foto."
    if not photo_path.exists():
        return f"El archivo no existe: {photo_path}"

    # extensión
    allowed = set([e.lower() for e in settings.get("photo_allowed_ext", [])])
    ext = photo_path.suffix.lower().lstrip(".")
    if allowed and ext not in allowed:
        return f"Extensión no permitida .{ext}. Permitidas: {', '.join(sorted(allowed))}"

    # tamaño
    try:
        size_mb = photo_path.stat().st_size / (1024 * 1024)
    except Exception:
        size_mb = 0
    max_mb = float(settings.get("photo_max_mb", 8))
    if size_mb > max_mb:
        return f"Archivo demasiado grande: {size_mb:.1f} MB (máximo {max_mb:.1f} MB)."

    return None


# ========== API pública ==========

def prepare_photo_fields(
    settings: Dict,
    tipo: str,
    correlation_id: Optional[str] = None,
    umbral: Optional[float] = None,
    extra: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    Arma el diccionario de campos de formulario para la API de marcación.
    - tipo: 'entrada' | 'salida' (minúsculas)
    - umbral: si no se pasa, toma settings["photo_default_umbral"]
    - correlation_id: opcional, para enlazar con el reporte
    - extra: campos adicionales opcionales
    """
    t = (tipo or "").strip().lower()
    if t not in ("entrada", "salida"):
        # No interrumpimos aquí; dejamos que el flujo superior decida, pero normalizamos
        t = "entrada"

    if umbral is None:
        try:
            umbral = float(settings.get("photo_default_umbral", 0.55))
        except Exception:
            umbral = 0.55

    fields: Dict[str, str] = {
        "tipo": t,
        "umbral": str(umbral),
    }
    if correlation_id:
        fields["correlation_id"] = str(correlation_id)

    if extra:
        # Solo admitimos str en multipart de 'data'
        for k, v in extra.items():
            if v is None:
                continue
            fields[str(k)] = str(v)

    return fields


def send_photo(
    settings: Dict,
    photo_path: Path,
    tipo: str,
    correlation_id: Optional[str] = None,
    umbral: Optional[float] = None,
    extra_fields: Optional[Dict[str, str]] = None,
) -> Tuple[bool, str, Optional[Dict]]:
    """
    Sube la foto a la API de marcación como multipart/form-data.
    Retorna: (ok: bool, mensaje: str, respuesta_json: dict|None)

    Campos enviados:
    - 'tipo' ('entrada'|'salida', minúsculas)
    - 'file' (archivo)
    - 'umbral' (string, p.ej. '0.55')
    - 'correlation_id' (opcional)
    - + extra_fields (opcional)
    """
    # Validaciones de archivo
    err = _validate_photo(settings, photo_path)
    if err:
        return False, err, None

    url = _endpoint_url(settings)
    timeout = settings.get("request_timeout_sec", 20)
    field_name = settings.get("photo_field_file", "file")

    headers: Dict[str, str] = {}
    token = (settings.get("photo_auth_token") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # Campos del formulario
    fields = prepare_photo_fields(
        settings=settings,
        tipo=tipo,
        correlation_id=correlation_id,
        umbral=umbral,
        extra=extra_fields,
    )

    # POST multipart
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            with open(photo_path, "rb") as fh:
                files = {field_name: (photo_path.name, fh, _mime_for(photo_path))}
                resp = client.post(url, data=fields, files=files)

        if 200 <= resp.status_code < 300:
            try:
                data = resp.json()
            except Exception:
                data = None
            return True, "Foto enviada con éxito.", data

        # No-2xx → guardamos pendiente (JSON + copia del archivo)
        copy_path = _copy_into_pending_files(photo_path)
        pending_meta = {
            "endpoint": url,
            "headers": headers,
            "fields": fields,
            "file_path": str(photo_path),
            "file_copy": str(copy_path) if copy_path else None,
            "status_code": resp.status_code,
            "response_text": resp.text[:1000],  # acortar por si es muy largo
            "saved_at": _now_ts(),
        }
        _save_photo_pending(pending_meta)
        return False, f"Error {resp.status_code} al enviar la foto. Guardada en pendientes.", None

    except Exception as e:
        # Error de red → también guardamos pendiente
        copy_path = _copy_into_pending_files(photo_path)
        pending_meta = {
            "endpoint": url,
            "headers": headers,
            "fields": fields,
            "file_path": str(photo_path),
            "file_copy": str(copy_path) if copy_path else None,
            "error": str(e),
            "saved_at": _now_ts(),
        }
        _save_photo_pending(pending_meta)
        return False, f"Error de red al enviar la foto: {e}. Guardada en pendientes.", None


def resend_pending_photos(settings: Dict) -> List[Tuple[Path, bool, str]]:
    """
    Reintenta todos los pendientes en pending/photos/.
    Devuelve una lista de tuplas: (ruta_json_pendiente, ok, mensaje)
    """
    results: List[Tuple[Path, bool, str]] = []
    url_default = _endpoint_url(settings)
    timeout = settings.get("request_timeout_sec", 20)
    field_name = settings.get("photo_field_file", "file")

    for jpath in sorted(PENDING_PHOTOS_DIR.glob("photo-*.json")):
        try:
            meta = json.loads(jpath.read_text(encoding="utf-8"))

            url = str(meta.get("endpoint") or url_default)
            headers = dict(meta.get("headers") or {})
            fields = dict(meta.get("fields") or {})

            # usar copia si existe, si no el original
            fcopy = meta.get("file_copy")
            fpath = Path(fcopy) if fcopy else Path(meta.get("file_path", ""))

            if not fpath.exists():
                results.append((jpath, False, "Archivo de foto no encontrado para reintento."))
                continue

            with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
                with open(fpath, "rb") as fh:
                    files = {field_name: (fpath.name, fh, _mime_for(fpath))}
                    resp = client.post(url, data=fields, files=files)

            if 200 <= resp.status_code < 300:
                # éxito → borrar pendiente y (si es copia) el archivo
                try:
                    if fcopy and Path(fcopy).exists():
                        Path(fcopy).unlink(missing_ok=True)
                finally:
                    jpath.unlink(missing_ok=True)

                try:
                    data = resp.json()
                except Exception:
                    data = None
                msg_ok = "Foto reenviada con éxito."
                if data:
                    msg_ok += " (Respuesta recibida)"
                results.append((jpath, True, msg_ok))
            else:
                results.append((jpath, False, f"Error {resp.status_code} al reenviar la foto."))

        except Exception as e:
            results.append((jpath, False, f"Error procesando pendiente: {e}"))

    return results
