# C:\Users\gcave\Desktop\ColectorAW\src\awcollector\ui_tk.py
from __future__ import annotations
import threading
import os, sys, uuid, tempfile, json
from pathlib import Path
from typing import Optional
from datetime import datetime

import cv2
from PIL import Image, ImageTk, ImageDraw

import customtkinter as ctk  # <<< UI moderna

from .config import load_settings
from .aggregate import build_daily_payload, build_yesterday_payload, send_payload
from .photo_api import send_photo

# ====== Paleta (marca) ======
COLOR_GREEN    = "#2BB673"   # éxito
COLOR_ORANGE   = "#FF7A00"   # acento (botón SALIDA)
COLOR_MUTED    = "#6B7280"   # texto sutil
COLOR_RED      = "#DC2626"   # fracaso

# ====== Util assets ======
def _resource_path(rel: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / rel


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        # Apariencia & tema
        ctk.set_appearance_mode("system")   # "light" | "dark" | "system"
        ctk.set_default_color_theme("green")
        self.title("Genika Control")
        self.geometry("860x620")
        self.resizable(False, False)

        # Icono
        icon_path = _resource_path(r"assets/Genika.ico")
        if icon_path.exists():
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        # Estado/animación
        self._busy = False
        self._progress_win: Optional[ctk.CTkToplevel] = None
        self._progress_bar: Optional[ctk.CTkProgressBar] = None
        self._dots_job = None

        # Config & cámara
        self.settings = load_settings()
        self._cap: Optional[cv2.VideoCapture] = None
        self._current_frame_bgr = None
        self._running = False

        # ====== LAYOUT ======
        header = ctk.CTkFrame(self, corner_radius=18, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 8))
        ctk.CTkLabel(header, text="Genika Control", font=("Segoe UI", 20, "bold"),
                     text_color="white").pack(pady=12)

        overlay = ctk.CTkFrame(self, fg_color="transparent")
        overlay.place(x=28, y=18)

        self._logo_img = None
        logo_path = _resource_path(r"assets/Genika.webp")
        if logo_path.exists():
            try:
                img = Image.open(logo_path).convert("RGBA")
                base_h = 40
                w, h = img.size
                img = img.resize((int(w * (base_h / h)), base_h), Image.LANCZOS)
                self._logo_img = ImageTk.PhotoImage(img)
            except Exception:
                pass

        row = ctk.CTkFrame(overlay, fg_color="transparent")
        row.pack()
        ctk.CTkLabel(row, text="", image=self._logo_img).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(row, text="Genika Control", font=("Segoe UI", 18, "bold")).pack(side="left")

        theme_row = ctk.CTkFrame(self, fg_color="transparent")
        theme_row.place(x=860-220, y=18)
        ctk.CTkLabel(theme_row, text="Tema", text_color=COLOR_MUTED).pack(side="left", padx=(0, 8))
        self._theme_var = ctk.StringVar(value="System")
        theme = ctk.CTkOptionMenu(theme_row, values=["System","Light","Dark"],
                                  command=self._on_theme_change, width=110)
        theme.pack(side="left")

        subtitle = ctk.CTkLabel(self,
                                text="Cámara activa. Usa ENTRADA o SALIDA para capturar y enviar.\n"
                                     "En SALIDA también se envía el reporte de ActivityWatch.",
                                justify="left", text_color=COLOR_MUTED)
        subtitle.pack(anchor="w", padx=22, pady=(2, 10))

        card = ctk.CTkFrame(self, corner_radius=16)
        card.pack(fill="both", expand=False, padx=16, pady=(0, 14))

        left = ctk.CTkFrame(card, fg_color="transparent")
        left.pack(side="left", padx=(16, 12), pady=16)

        right = ctk.CTkFrame(card, fg_color="transparent")
        right.pack(side="left", padx=16, pady=16, fill="y")

        self.preview_w = 560
        self.preview_h = 400
        self.video_label = ctk.CTkLabel(left, width=self.preview_w, height=self.preview_h, text="")
        self.video_label.pack()
        ctk.CTkLabel(left, text="Vista previa (la cámara permanece abierta)",
                     text_color=COLOR_MUTED).pack(anchor="w", pady=(10,0))

        self.btn_entrada = ctk.CTkButton(
            right, text="ENTRADA", width=220, height=46,
            corner_radius=14, fg_color=COLOR_GREEN, hover_color="#25A166",
            command=lambda: self.on_click_tipo("entrada"))
        self.btn_entrada.pack(fill="x", pady=(0, 10))

        self.btn_salida = ctk.CTkButton(
            right, text="SALIDA", width=220, height=46,
            corner_radius=14, fg_color=COLOR_ORANGE, hover_color="#E06B00",
            command=lambda: self.on_click_tipo("salida"))
        self.btn_salida.pack(fill="x")

        self.btn_ayer = ctk.CTkButton(
            right, text="enviar informe de AYER",
            width=10, height=30, corner_radius=8,
            fg_color="transparent", hover=False,
            text_color=COLOR_MUTED,
            command=self.on_click_ayer)
        self.btn_ayer.pack(anchor="e", pady=(12, 0))

        self.status = ctk.StringVar(value="Inicializando cámara…")
        ctk.CTkLabel(self, textvariable=self.status, text_color=COLOR_MUTED).pack(anchor="w", padx=22, pady=10)

        ctk.CTkLabel(self,
                     text="Asegúrate que ActivityWatch esté corriendo (http://localhost:5600) para el reporte de SALIDA.",
                     text_color=COLOR_MUTED).pack(anchor="w", padx=22)

        self._start_camera()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind_all("<Control-d>", lambda e: self._toggle_theme())

    # ====== Tema ======
    def _on_theme_change(self, value: str):
        v = value.lower()
        if v == "light":
            ctk.set_appearance_mode("light")
        elif v == "dark":
            ctk.set_appearance_mode("dark")
        else:
            ctk.set_appearance_mode("system")

    def _toggle_theme(self):
        cur = ctk.get_appearance_mode().lower()
        ctk.set_appearance_mode("dark" if cur == "light" else "light")

    # ====== Cámara ======
    def _try_open_camera(self) -> Optional[cv2.VideoCapture]:
        candidates = [
            (0, cv2.CAP_DSHOW),
            (0, 0),
            (1, cv2.CAP_DSHOW),
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
            self.status.set("No se pudo abrir la cámara (cierra otras apps o revisa permisos).")
            if hasattr(ctk, "CTkMessagebox"):
                ctk.CTkMessagebox(
                    title="Genika Control",
                    message="No se pudo abrir la cámara.\nCierra Teams/Zoom, revisa permisos de Windows,\n"
                            "o conecta otra cámara.",
                    icon="warning"
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
            self._current_frame_bgr = frame
            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(rgb).resize((self.preview_w, self.preview_h), Image.LANCZOS)
                imgtk = ImageTk.PhotoImage(image=img)
                self.video_label.configure(image=imgtk)
                self.video_label.image = imgtk
            except Exception:
                pass
        self.after(33, self._update_preview)  # ~30 fps

    def _capture_to_tempfile(self) -> Optional[Path]:
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

    # ====== Helpers ======
    def _truthy(self, val) -> bool:
        if isinstance(val, bool):
            return val
        if isinstance(val, (int, float)):
            return val != 0
        if isinstance(val, str):
            v = val.strip().lower()
            return v in {"ok", "true", "1", "yes", "si", "sí", "success", "éxito", "exito", "enviado", "enviados"}
        return False

    def _compute_photo_success(self, raw: dict) -> bool:
        match = self._truthy(raw.get("match"))
        registrado = self._truthy(raw.get("registrado"))
        mensaje = str(raw.get("mensaje", "")).strip().lower()
        return bool(match or registrado or mensaje in {"ok", "success", "éxito", "exito"})

    def _compute_aw_success(self, aw_resp):
        # aw_resp puede ser str o dict; sin forzar estructura
        if isinstance(aw_resp, dict):
            for k in ("ok", "success", "estado", "status", "mensaje", "message", "enviado"):
                if k in aw_resp:
                    return self._truthy(aw_resp.get(k))
            return any(s in json.dumps(aw_resp, ensure_ascii=False).lower()
                       for s in ("ok", "success", "éxito", "exito", "enviado"))
        if isinstance(aw_resp, (bytes, bytearray)):
            try:
                aw_resp = aw_resp.decode("utf-8", errors="replace")
            except Exception:
                aw_resp = str(aw_resp)
        text = str(aw_resp or "").lower()
        return any(s in text for s in ("ok", "success", "éxito", "exito", "enviado"))

    # ====== Modal simple (compacto) ======
    def _show_compact_modal(self, photo_raw, aw_raw=None):
        """
        Modal compacto que une ambas respuestas:
        - Control de acceso: OK / rechazado
        - Datos de tu equipo: ENVIADOS / NO ENVIADOS
        - Solo: Nombre, Documento, match, registrado
        """
        nombre = "—"
        documento = "—"
        match = False
        registrado = False
        acceso_ok = False
        equipo_ok = None

        if isinstance(photo_raw, dict):
            nombre_ = str(photo_raw.get("nombres", "")).strip()
            apellidos_ = str(photo_raw.get("apellidos", "")).strip()
            nombre = (nombre_ + (" " + apellidos_ if apellidos_ else "")).strip() or "—"
            documento = str(photo_raw.get("documento", "—"))
            match = bool(photo_raw.get("match")) if isinstance(photo_raw.get("match"), bool) else self._truthy(photo_raw.get("match"))
            registrado = bool(photo_raw.get("registrado")) if isinstance(photo_raw.get("registrado"), bool) else self._truthy(photo_raw.get("registrado"))
            acceso_ok = self._compute_photo_success(photo_raw)
        else:
            # si no es dict, igual mostramos literal nombre/documento no disponibles
            acceso_ok = self._truthy(photo_raw)

        if aw_raw is not None:
            equipo_ok = self._compute_aw_success(aw_raw)

        def _open():
            win = ctk.CTkToplevel(self)
            win.title("Resultado")
            win.geometry("560x320")
            win.resizable(False, False)
            win.grab_set()
            win.transient(self)

            outer = ctk.CTkFrame(win, corner_radius=14)
            outer.pack(fill="both", expand=True, padx=10, pady=10)

            # --- Control de acceso
            color1 = COLOR_GREEN if acceso_ok else COLOR_RED
            banner1 = ctk.CTkFrame(outer, corner_radius=10, fg_color=color1)
            banner1.pack(fill="x", padx=6, pady=(4, 8))
            ctk.CTkLabel(banner1,
                         text="Control de acceso: OK" if acceso_ok else "Control de acceso: rechazado",
                         font=("Segoe UI", 18, "bold"),
                         text_color="white").pack(padx=12, pady=8)

            info = ctk.CTkFrame(outer, corner_radius=10)
            info.pack(fill="x", padx=6, pady=(0, 10))

            def row(lbl, val, bold=False):
                fr = ctk.CTkFrame(info, fg_color="transparent")
                fr.pack(fill="x", padx=10, pady=4)
                ctk.CTkLabel(fr, text=lbl, width=120, anchor="w", text_color=COLOR_MUTED).pack(side="left")
                font = ("Segoe UI", 14, "bold") if bold else ("Segoe UI", 14)
                ctk.CTkLabel(fr, text=val, anchor="w", font=font).pack(side="left", padx=(6,0))

            row("Nombre:", nombre, bold=True)
            row("Documento:", documento)
            row("match:", "True" if match else "False")
            row("registrado:", "True" if registrado else "False")

            # --- Datos de tu equipo
            if equipo_ok is not None:
                color2 = COLOR_GREEN if equipo_ok else COLOR_RED
                banner2 = ctk.CTkFrame(outer, corner_radius=10, fg_color=color2)
                banner2.pack(fill="x", padx=6, pady=(6, 10))
                ctk.CTkLabel(banner2,
                             text="Datos de tu equipo: ENVIADOS" if equipo_ok else "Datos de tu equipo: NO ENVIADOS",
                             font=("Segoe UI", 18, "bold"),
                             text_color="white").pack(padx=12, pady=8)

            # --- Botonera
            btn = ctk.CTkButton(outer, text="Cerrar", width=120, command=win.destroy)
            btn.pack(pady=(6, 2))

            # centrar
            self.update_idletasks()
            x = self.winfo_rootx() + (self.winfo_width() // 2) - 280
            y = self.winfo_rooty() + (self.winfo_height() // 2) - 160
            win.geometry(f"+{x}+{y}")

        self.after(0, _open)

    # ====== Modal / bloqueo ======
    def _open_progress(self, message: str = "Procesando…"):
        if self._progress_win is not None:
            return
        self._busy = True

        win = ctk.CTkToplevel(self)
        win.title("Enviando…")
        win.geometry("360x140")
        win.resizable(False, False)
        win.grab_set()
        win.transient(self)
        win.protocol("WM_DELETE_WINDOW", lambda: None)  # impedir cierre
        self._disable_close(True)

        frm = ctk.CTkFrame(win, corner_radius=16)
        frm.pack(fill="both", expand=True, padx=12, pady=12)

        self._dots_lbl = ctk.CTkLabel(frm, text=message, anchor="center")
        self._dots_lbl.pack(pady=(8, 6))

        bar = ctk.CTkProgressBar(frm, indeterminate_speed=1.2)
        bar.pack(fill="x", padx=12, pady=(0, 10))
        bar.configure(mode="indeterminate")
        bar.start()

        ctk.CTkLabel(frm, text="Por favor espera…", text_color=COLOR_MUTED).pack()

        self.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() // 2) - 180
        y = self.winfo_rooty() + (self.winfo_height() // 2) - 70
        win.geometry(f"+{x}+{y}")

        self._progress_win = win
        self._progress_bar = bar
        self._set_busy(True)
        self._animate_dots("")

    def _animate_dots(self, dots: str):
        if self._progress_win is None:
            return
        next_dots = "." * ((len(dots) + 1) % 4)
        try:
            self._dots_lbl.configure(text=self._dots_lbl.cget("text").split(".")[0] + next_dots)
        except Exception:
            pass
        self._dots_job = self.after(350, lambda: self._animate_dots(next_dots))

    def _close_progress(self):
        if self._dots_job:
            self.after_cancel(self._dots_job)
            self._dots_job = None
        if self._progress_bar:
            try:
                self._progress_bar.stop()
            except Exception:
                pass
        if self._progress_win:
            try:
                self._progress_win.grab_release()
                self._progress_win.destroy()
            except Exception:
                pass
        self._progress_win = None
        self._progress_bar = None
        self._set_busy(False)
        self._disable_close(False)
        self._busy = False

    def _disable_close(self, disabled: bool):
        if disabled:
            self.protocol("WM_DELETE_WINDOW", lambda: None)
        else:
            self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ====== Acciones ======
    def on_click_tipo(self, tipo: str):
        txt = "¿Deseas enviar ENTRADA con la captura actual?" if tipo == "entrada" else \
              "¿Deseas enviar SALIDA con la captura actual (también enviará el reporte AW)?"
        if hasattr(ctk, "CTkMessagebox"):
            if ctk.CTkMessagebox(title="Confirmar", message=txt, icon="question",
                                 option_1="Cancelar", option_2="Aceptar").get() != "Aceptar":
                return
        else:
            if not self._legacy_confirm(txt):
                return

        photo_path = self._capture_to_tempfile()
        if not photo_path or not photo_path.exists():
            if hasattr(ctk, "CTkMessagebox"):
                ctk.CTkMessagebox(title="Genika Control",
                                  message="No se pudo capturar la imagen de la cámara.",
                                  icon="warning")
            return

        self._open_progress("Enviando foto y reporte")
        threading.Thread(target=self._do_send_tipo, args=(tipo, photo_path), daemon=True).start()

    def on_click_ayer(self):
        txt = "¿Enviar informe de ActivityWatch de AYER? (sin foto)"
        if hasattr(ctk, "CTkMessagebox"):
            if ctk.CTkMessagebox(title="Confirmar", message=txt, icon="question",
                                 option_1="Cancelar", option_2="Enviar").get() != "Enviar":
                return
        else:
            if not self._legacy_confirm(txt):
                return
        self._open_progress("Enviando informe de AYER")
        threading.Thread(target=self._do_send_ayer, daemon=True).start()

    def _legacy_confirm(self, txt: str) -> bool:
        import tkinter.messagebox as mb
        return mb.askyesno("Confirmar", txt)

    # ====== LÓGICA ======
    def _do_send_tipo(self, tipo: str, photo_path: Path):
        try:
            cid = str(uuid.uuid4())

            # 1) Control de acceso (Foto)
            ok_foto, msg_foto, data_foto = send_photo(
                settings=self.settings,
                photo_path=photo_path,
                tipo=tipo,
                correlation_id=cid,
                umbral=None,
                extra_fields=None
            )

            # 2) Datos de tu equipo (Productividad) si es salida
            aw_raw = None
            if tipo == "salida":
                self.after(0, lambda: self.status.set("Preparando reporte de productividad…"))
                payload = build_daily_payload(self.settings, meta_extra={
                    "correlation_id": cid,
                    "marcacion_tipo": "salida",
                })
                self.after(0, lambda: self.status.set("Enviando reporte de productividad…"))
                ok_aw, msg_aw = send_payload(self.settings, payload)
                aw_raw = msg_aw  # literal / lo que devuelva

            # 3) Un único modal compacto
            self.after(0, lambda: self.status.set("Respuesta(s) recibida(s)."))
            self._show_compact_modal(
                photo_raw=(data_foto if data_foto is not None else msg_foto),
                aw_raw=aw_raw if tipo == "salida" else None
            )

        except Exception as e:
            self.after(0, lambda: self.status.set("Ocurrió un error inesperado."))
            if hasattr(ctk, "CTkMessagebox"):
                ctk.CTkMessagebox(title="Error", message=str(e))
        finally:
            try:
                photo_path.unlink(missing_ok=True)
            except Exception:
                pass
            self.after(0, self._close_progress)

    def _do_send_ayer(self):
        try:
            cid = str(uuid.uuid4())
            self.after(0, lambda: self.status.set("Preparando reporte de AYER…"))
            payload = build_yesterday_payload(self.settings, meta_extra={
                "correlation_id": cid,
                "marcacion_tipo": "salida_ayer",
            })
            self.after(0, lambda: self.status.set("Enviando reporte de AYER…"))
            ok_aw, msg_aw = send_payload(self.settings, payload)

            # Modal compacto solo con "Datos de tu equipo"
            equipo_ok = self._compute_aw_success(msg_aw)

            def _open():
                win = ctk.CTkToplevel(self)
                win.title("Resultado AYER")
                win.geometry("520x200")
                win.resizable(False, False)
                win.grab_set()
                win.transient(self)

                outer = ctk.CTkFrame(win, corner_radius=14)
                outer.pack(fill="both", expand=True, padx=10, pady=10)

                color = COLOR_GREEN if equipo_ok else COLOR_RED
                banner = ctk.CTkFrame(outer, corner_radius=10, fg_color=color)
                banner.pack(fill="x", padx=6, pady=(6, 12))
                ctk.CTkLabel(banner,
                             text="Datos de tu equipo: ENVIADOS" if equipo_ok else "Datos de tu equipo: NO ENVIADOS",
                             font=("Segoe UI", 18, "bold"),
                             text_color="white").pack(padx=12, pady=10)

                ctk.CTkButton(outer, text="Cerrar", width=120, command=win.destroy).pack(pady=(4, 2))

                self.update_idletasks()
                x = self.winfo_rootx() + (self.winfo_width() // 2) - 260
                y = self.winfo_rooty() + (self.winfo_height() // 2) - 100
                win.geometry(f"+{x}+{y}")
            self.after(0, _open)

            self.after(0, lambda: self.status.set("Respuesta recibida (AYER)."))
        except Exception as e:
            self.after(0, lambda: self.status.set("Ocurrió un error inesperado."))
            if hasattr(ctk, "CTkMessagebox"):
                ctk.CTkMessagebox(title="Error", message=str(e))
        finally:
            self.after(0, self._close_progress)

    # ====== util ======
    def _set_busy(self, busy: bool, msg: str | None = None):
        state = "disabled" if busy else "normal"
        for btn in (getattr(self, "btn_entrada", None),
                    getattr(self, "btn_salida", None),
                    getattr(self, "btn_ayer", None)):
            if btn is not None:
                btn.configure(state=state)
        if msg:
            self.status.set(msg)

    def _on_close(self):
        if self._busy or self._progress_win is not None:
            return
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
