# C:\Users\gcave\Desktop\ColectorAW\src\awcollector\ui_tk.py
from __future__ import annotations
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import os, sys, uuid, tempfile, json
from pathlib import Path
from typing import Optional
from datetime import datetime

import cv2  # OpenCV para cámara
from PIL import Image, ImageTk  # mostrar frames en Tk

from .config import load_settings
from .aggregate import build_daily_payload, send_payload
from .photo_api import send_photo

# ---------- Paleta Genika ----------
COLOR_BG      = "#FFFFFF"   # Blanco
COLOR_TEXT    = "#0B3D6E"   # Azul profundo
COLOR_ACCENT  = "#2CB6C0"   # Turquesa
COLOR_ORANGE  = "#FF7A00"   # Naranja (Salida)
COLOR_GREEN   = "#2BB673"   # Verde (Entrada)
COLOR_MUTED   = "#6B7280"   # Gris texto
COLOR_DIVIDER = "#E5E7EB"   # Divisor

# Ruta segura a assets (funciona en .py y en .exe)
def _resource_path(rel: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))  # repo root en dev
    return base / rel


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Genika Control")

        # === Icono de la ventana (usa assets/Genika.ico) ===
        icon_path = _resource_path(r"assets/Genika.ico")
        if icon_path.exists():
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass
        # ===================================================

        self.geometry("680x520")
        self.resizable(False, False)
        self.configure(bg=COLOR_BG)

        # Fuente global
        try:
            self.option_add("*Font", ("Segoe UI", 10))
        except Exception:
            pass

        # Estilos ttk
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Genika.TFrame", background=COLOR_BG)
        style.configure("Genika.Title.TLabel", background=COLOR_BG, foreground=COLOR_TEXT, font=("Segoe UI", 12, "bold"))
        style.configure("Genika.SubLabel.TLabel", background=COLOR_BG, foreground=COLOR_MUTED, font=("Segoe UI", 9))
        style.configure("Genika.TSeparator", background=COLOR_DIVIDER)
        style.configure("Genika.TButton", font=("Segoe UI", 10), padding=6)

        # Contenedor
        frm = ttk.Frame(self, padding=16, style="Genika.TFrame")
        frm.pack(fill="both", expand=True)

        # ---- Logo ----
        self._logo_img = None
        logo_path = _resource_path(r"assets/Genika.webp")
        if logo_path.exists():
            try:
                img = Image.open(logo_path).convert("RGBA")
                base_h = 48
                w, h = img.size
                img = img.resize((int(w * (base_h / h)), base_h), Image.LANCZOS)
                self._logo_img = ImageTk.PhotoImage(img)
                tk.Label(frm, image=self._logo_img, bg=COLOR_BG).pack(anchor="w", pady=(0,6))
            except Exception:
                pass

        # Título y divisor
        ttk.Label(frm, text="Genika Control", style="Genika.Title.TLabel").pack(anchor="w")
        ttk.Separator(frm, style="Genika.TSeparator").pack(fill="x", pady=8)

        # Subtítulo
        ttk.Label(
            frm,
            text="Cámara activa. Usa ENTRADA o SALIDA para capturar y enviar. "
                 "En SALIDA también se envía el reporte de ActivityWatch.",
            style="Genika.SubLabel.TLabel"
        ).pack(anchor="w", pady=(0,6))

        # ---- Área de cámara + controles ----
        top = ttk.Frame(frm, style="Genika.TFrame")
        top.pack(fill="x")

        # Vista de cámara (izquierda)
        left = ttk.Frame(top, style="Genika.TFrame")
        left.pack(side="left", padx=(0, 12))

        self.preview_w = 480
        self.preview_h = 360
        self.video_label = tk.Label(left, width=self.preview_w, height=self.preview_h, bg="#000000")
        self.video_label.pack()

        ttk.Label(left, text="Vista previa (cámara permanece abierta)", style="Genika.SubLabel.TLabel").pack(anchor="w", pady=(8,0))

        # Controles (derecha)
        right = ttk.Frame(top, style="Genika.TFrame")
        right.pack(side="left", fill="y")

        self.btn_entrada = ttk.Button(right, text="ENTRADA", style="Genika.TButton",
                                      command=lambda: self.on_click_tipo("entrada"))
        self.btn_entrada.pack(fill="x", pady=(0,8))
        self.btn_entrada.configure(cursor="hand2")

        self.btn_salida = ttk.Button(right, text="SALIDA", style="Genika.TButton",
                                     command=lambda: self.on_click_tipo("salida"))
        self.btn_salida.pack(fill="x")
        self.btn_salida.configure(cursor="hand2")

        # Estado
        self.status = tk.StringVar(value="Inicializando cámara…")
        ttk.Label(frm, textvariable=self.status, style="Genika.SubLabel.TLabel", wraplength=640).pack(anchor="w", pady=12)

        # Pie de ayuda
        ttk.Label(frm, text="Asegúrate que ActivityWatch esté corriendo (http://localhost:5600) para el reporte de SALIDA.", style="Genika.SubLabel.TLabel").pack(anchor="w")

        # Config y cámara
        self.settings = load_settings()

        # Atributos de cámara
        self._cap: Optional[cv2.VideoCapture] = None
        self._current_frame_bgr = None
        self._running = False

        # Arrancar cámara y loop de preview
        self._start_camera()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ======================= Cámara =======================

    def _try_open_camera(self) -> Optional[cv2.VideoCapture]:
        """
        Intenta abrir la cámara probando varios backends/índices para mejorar compatibilidad.
        """
        candidates = [
            (0, cv2.CAP_DSHOW),  # Windows preferido
            (0, 0),              # backend por defecto
            (1, cv2.CAP_DSHOW),  # segundo dispositivo
            (1, 0),
            (2, cv2.CAP_DSHOW),
            (2, 0),
        ]
        for idx, backend in candidates:
            try:
                cap = cv2.VideoCapture(idx, backend) if backend else cv2.VideoCapture(idx)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                if cap.isOpened():
                    # probar un frame para validar
                    ok, _ = cap.read()
                    if ok:
                        return cap
                    cap.release()
            except Exception:
                try:
                    cap.release()
                except Exception:
                    pass
        return None

    def _start_camera(self):
        self._cap = self._try_open_camera()
        if not self._cap:
            self.status.set("No se pudo abrir la cámara (prueba otra app o revisa permisos de Windows).")
            messagebox.showerror(
                "Genika Control",
                "No se pudo abrir la cámara.\nCierra otras apps (Teams/Zoom), "
                "revisa permisos en Configuración > Privacidad > Cámara, "
                "o conecta otra cámara."
            )
            return

        self._running = True
        self.status.set("Cámara lista. Elige ENTRADA o SALIDA para capturar y enviar.")
        self._update_preview()

    def _update_preview(self):
        if not self._running or not self._cap:
            return

        ret, frame = self._cap.read()
        if ret:
            self._current_frame_bgr = frame  # último frame para capturar
            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(rgb).resize((self.preview_w, self.preview_h), Image.LANCZOS)
                imgtk = ImageTk.PhotoImage(image=img)
                self.video_label.imgtk = imgtk  # evitar GC
                self.video_label.configure(image=imgtk)
            except Exception:
                pass
        # ~30 fps
        self.after(33, self._update_preview)

    def _capture_to_tempfile(self) -> Optional[Path]:
        """
        Captura el frame actual y lo guarda como JPG en una carpeta temporal.
        Devuelve la ruta del archivo o None si falla.
        """
        if self._current_frame_bgr is None:
            return None
        try:
            base_tmp = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "ColectorAW" / "tmp"
            base_tmp.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            out_path = base_tmp / f"captura_{ts}.jpg"
            ok, buf = cv2.imencode(".jpg", self._current_frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
            if not ok:
                return None
            out_path.write_bytes(buf.tobytes())
            return out_path
        except Exception:
            return None

    # ======================= Acciones =======================

    def on_click_tipo(self, tipo: str):
        # Confirmación previa
        txt = "¿Deseas enviar ENTRADA con la captura actual?" if tipo == "entrada" else \
              "¿Deseas enviar SALIDA con la captura actual (también enviará el reporte AW)?"
        if not messagebox.askyesno("Confirmar", txt):
            return

        photo_path = self._capture_to_tempfile()
        if not photo_path or not photo_path.exists():
            messagebox.showwarning("Genika Control", "No se pudo capturar la imagen de la cámara.")
            return

        # Ejecutar en hilo para no bloquear la UI
        self._set_busy(True, "Enviando foto…")
        threading.Thread(target=self._do_send_tipo, args=(tipo, photo_path), daemon=True).start()

    def _format_photo_api_response(self, data: Optional[dict]) -> str:
        """
        Convierte el JSON del API de foto a un texto amigable si vienen campos típicos.
        """
        if not isinstance(data, dict):
            return ""
        parts = []
        # Campos comunes según tu front
        if "match" in data:
            parts.append(f"match: {data.get('match')}")
        if "registrado" in data:
            parts.append(f"registrado: {data.get('registrado')}")
        if isinstance(data.get("score"), (int, float)):
            parts.append(f"score: {float(data['score']):.2f}")
        if isinstance(data.get("umbral"), (int, float)):
            parts.append(f"umbral: {float(data['umbral']):.2f}")
        if data.get("documento"):
            parts.append(f"documento: {data['documento']}")
        if data.get("nombres") or data.get("apellidos"):
            nombre = f"{data.get('nombres','')} {data.get('apellidos','')}".strip()
            if nombre:
                parts.append(f"nombre: {nombre}")
        if data.get("fecha_hora"):
            parts.append(f"fecha_hora: {data['fecha_hora']}")
        # Fallback si no hay campos conocidos
        if not parts:
            try:
                return "\nRespuesta: " + json.dumps(data, ensure_ascii=False)
            except Exception:
                return ""
        return "\n" + " · ".join(parts)

    def _do_send_tipo(self, tipo: str, photo_path: Path):
        try:
            cid = str(uuid.uuid4())  # correlation_id para enlazar foto y reporte

            # 1) Enviar foto SIEMPRE
            ok_foto, msg_foto, data_foto = send_photo(
                settings=self.settings,
                photo_path=photo_path,
                tipo=tipo,               # 'entrada' | 'salida'
                correlation_id=cid,
                umbral=None,            # usa default de settings (0.55)
                extra_fields=None
            )

            if ok_foto:
                detalle = self._format_photo_api_response(data_foto)
                self.status.set(f"Foto: OK. {msg_foto}")
                messagebox.showinfo("Genika Control", f"✅ Foto enviada con éxito.{detalle}")
            else:
                self.status.set(f"Foto: ERROR. {msg_foto}")
                messagebox.showwarning("Genika Control", f"❕ {msg_foto}")
                return  # No seguimos con AW si falló la foto

            # 2) Si es SALIDA, enviar también el reporte AW
            if tipo == "salida":
                self.status.set("Foto: OK. Preparando reporte AW…")
                payload = build_daily_payload(self.settings, meta_extra={
                    "correlation_id": cid,
                    "marcacion_tipo": "salida",
                })
                self.status.set("Enviando reporte AW…")
                ok_aw, msg_aw = send_payload(self.settings, payload)
                if ok_aw:
                    self.status.set("Foto: OK. Reporte AW: OK.")
                    messagebox.showinfo("Genika Control", "✅ Salida enviada con éxito (foto + reporte).")
                else:
                    self.status.set(f"Foto: OK. Reporte AW: ERROR. {msg_aw}")
                    messagebox.showwarning("Genika Control", f"❕ Reporte AW con error.\n{msg_aw}")
            else:
                # ENTRADA: solo foto (ya mostramos el detalle)
                pass

        except Exception as e:
            self.status.set(f"Error inesperado: {e}")
            messagebox.showerror("Genika Control", f"❌ Error inesperado:\n{e}")
        finally:
            # Limpieza del archivo temporal
            try:
                photo_path.unlink(missing_ok=True)
            except Exception:
                pass
            self._set_busy(False)

    # --- util ---
    def _set_busy(self, busy: bool, msg: str | None = None):
        state = "disabled" if busy else "normal"
        self.btn_entrada.config(state=state)
        self.btn_salida.config(state=state)
        if msg:
            self.status.set(msg)

    def _on_close(self):
        # Liberar cámara
        try:
            self._running = False
            if self._cap is not None:
                self._cap.release()
        except Exception:
            pass
        self.destroy()


def run():
    app = App()
    app.mainloop()
