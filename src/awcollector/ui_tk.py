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
COLOR_GREEN   = "#2BB673"   # ENTRADA
COLOR_ORANGE  = "#FF7A00"   # SALIDA
COLOR_BLUE    = "#1E73B6"   # acento/links
COLOR_MUTED   = "#6B7280"   # texto sutil

# ====== Util assets ======
def _resource_path(rel: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / rel


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        # Apariencia & tema
        ctk.set_appearance_mode("system")   # "light" | "dark" | "system"
        ctk.set_default_color_theme("green")  # solo base; seteamos colores por botón
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
        # Header con degradado (tornasol)
        header = ctk.CTkFrame(self, corner_radius=18, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 8))

        ctk.CTkLabel(header, text="Genika Control", font=("Segoe UI", 20, "bold"),
                      text_color="white").pack(pady=12)

        # Logo + título arriba del gradiente para contraste
        overlay = ctk.CTkFrame(self, fg_color="transparent")
        overlay.place(x=28, y=18)  # ligero overlay encima del header

        # Logo
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

        # Tema (selector)
        theme_row = ctk.CTkFrame(self, fg_color="transparent")
        theme_row.place(x=860-220, y=18)
        ctk.CTkLabel(theme_row, text="Tema", text_color=COLOR_MUTED).pack(side="left", padx=(0, 8))
        self._theme_var = ctk.StringVar(value="System")
        theme = ctk.CTkOptionMenu(theme_row, values=["System","Light","Dark"],
                                  command=self._on_theme_change, width=110)
        theme.pack(side="left")

        # Subtítulo
        subtitle = ctk.CTkLabel(self,
                                text="Cámara activa. Usa ENTRADA o SALIDA para capturar y enviar.\n"
                                     "En SALIDA también se envía el reporte de ActivityWatch.",
                                justify="left", text_color=COLOR_MUTED)
        subtitle.pack(anchor="w", padx=22, pady=(2, 10))

        # Card principal
        card = ctk.CTkFrame(self, corner_radius=16)
        card.pack(fill="both", expand=False, padx=16, pady=(0, 14))

        # Layout card: izquierda preview, derecha botones
        left = ctk.CTkFrame(card, fg_color="transparent")
        left.pack(side="left", padx=(16, 12), pady=16)

        right = ctk.CTkFrame(card, fg_color="transparent")
        right.pack(side="left", padx=16, pady=16, fill="y")

        # Preview cámara
        self.preview_w = 560
        self.preview_h = 400
        self.video_label = ctk.CTkLabel(left, width=self.preview_w, height=self.preview_h, text="")
        self.video_label.pack()
        ctk.CTkLabel(left, text="Vista previa (la cámara permanece abierta)",
                     text_color=COLOR_MUTED).pack(anchor="w", pady=(10,0))

        # Botones de acción (distintos colores / posiciones)
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

        # Botón “ayer” estilo link
        self.btn_ayer = ctk.CTkButton(
            right, text="enviar informe de AYER",
            width=10, height=30, corner_radius=8,
            fg_color="transparent", hover=False,
            text_color=COLOR_MUTED,
            command=self.on_click_ayer)
        self.btn_ayer.pack(anchor="e", pady=(12, 0))

        # Estado
        self.status = ctk.StringVar(value="Inicializando cámara…")
        ctk.CTkLabel(self, textvariable=self.status, text_color=COLOR_MUTED).pack(anchor="w", padx=22, pady=10)

        # Footer
        ctk.CTkLabel(self,
                     text="Asegúrate que ActivityWatch esté corriendo (http://localhost:5600) para el reporte de SALIDA.",
                     text_color=COLOR_MUTED).pack(anchor="w", padx=22)

        # Cámara & ciclo
        self._start_camera()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Atajos
        self.bind_all("<Control-d>", lambda e: self._toggle_theme())

    # ====== Helpers visuales ======
    def _gradient_image(self, width: int, height: int, colors: list[str]) -> ImageTk.PhotoImage:
        """
        Genera un gradiente horizontal suave (tornasol) para header.
        """
        img = Image.new("RGB", (width, height), colors[0])
        draw = ImageDraw.Draw(img)

        # dividir el gradiente en tramos entre colores
        steps = width
        segs = len(colors) - 1
        for x in range(steps):
            # posición normalizada 0..1 y segmento
            t = x / max(steps - 1, 1)
            idx = min(int(t * segs), segs - 1)
            local_t = (t - idx / segs) * segs
            c1 = tuple(int(colors[idx].lstrip("#")[i:i+2], 16) for i in (0,2,4))
            c2 = tuple(int(colors[idx+1].lstrip("#")[i:i+2], 16) for i in (0,2,4))
            r = int(c1[0] + (c2[0]-c1[0]) * local_t)
            g = int(c1[1] + (c2[1]-c1[1]) * local_t)
            b = int(c1[2] + (c2[2]-c1[2]) * local_t)
            draw.line([(x, 0), (x, height)], fill=(r, g, b))
        # esquinas redondeadas fake con máscara rápida
        radius = 18
        mask = Image.new("L", (width, height), 255)
        mdraw = ImageDraw.Draw(mask)
        mdraw.rounded_rectangle([(0,0),(width-1,height-1)], radius, fill=255)
        img.putalpha(mask)
        return ImageTk.PhotoImage(img)

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
            ctk.CTkMessagebox(title="Genika Control",
                              message="No se pudo abrir la cámara.\nCierra Teams/Zoom, revisa permisos de Windows,\n"
                                      "o conecta otra cámara.",
                              icon="warning") if hasattr(ctk, "CTkMessagebox") else None
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

        # centrar
        self.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() // 2) - 180
        y = self.winfo_rooty() + (self.winfo_height() // 2) - 70
        win.geometry(f"+{x}+{y}")

        self._progress_win = win
        self._progress_bar = bar
        self._set_busy(True)

        # animación de puntitos
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
        if not ctk.CTkMessagebox(title="Confirmar", message=txt, icon="question",
                                 option_1="Cancelar", option_2="Aceptar").get() == "Aceptar" \
           if hasattr(ctk, "CTkMessagebox") else not self._legacy_confirm(txt):
            return

        photo_path = self._capture_to_tempfile()
        if not photo_path or not photo_path.exists():
            ctk.CTkMessagebox(title="Genika Control", message="No se pudo capturar la imagen de la cámara.",
                              icon="warning") if hasattr(ctk, "CTkMessagebox") else None
            return

        self._open_progress("Enviando foto y reporte")
        threading.Thread(target=self._do_send_tipo, args=(tipo, photo_path), daemon=True).start()

    def on_click_ayer(self):
        txt = "¿Enviar informe de ActivityWatch de AYER? (sin foto)"
        if not ctk.CTkMessagebox(title="Confirmar", message=txt, icon="question",
                                 option_1="Cancelar", option_2="Enviar").get() == "Enviar" \
           if hasattr(ctk, "CTkMessagebox") else not self._legacy_confirm(txt):
            return
        self._open_progress("Enviando informe de AYER")
        threading.Thread(target=self._do_send_ayer, daemon=True).start()

    def _legacy_confirm(self, txt: str) -> bool:
        # fallback si CTkMessagebox no está disponible en tu versión
        import tkinter.messagebox as mb
        return mb.askyesno("Confirmar", txt)

    def _format_photo_api_response(self, data: Optional[dict]) -> str:
        if not isinstance(data, dict):
            return ""
        parts = []
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
        if not parts:
            try:
                return "\nRespuesta: " + json.dumps(data, ensure_ascii=False)
            except Exception:
                return ""
        return "\n" + " · ".join(parts)

    def _do_send_tipo(self, tipo: str, photo_path: Path):
        try:
            cid = str(uuid.uuid4())
            # 1) Foto
            ok_foto, msg_foto, data_foto = send_photo(
                settings=self.settings,
                photo_path=photo_path,
                tipo=tipo,
                correlation_id=cid,
                umbral=None,
                extra_fields=None
            )
            if ok_foto:
                detalle = self._format_photo_api_response(data_foto)
                self.status.set(f"Foto: OK. {msg_foto}")
                ctk.CTkMessagebox(title="Genika Control", message=f"✅ Foto enviada con éxito.{detalle}",
                                  icon="check") if hasattr(ctk, "CTkMessagebox") else None
            else:
                self.status.set(f"Foto: ERROR. {msg_foto}")
                ctk.CTkMessagebox(title="Genika Control", message=f"❕ {msg_foto}",
                                  icon="warning") if hasattr(ctk, "CTkMessagebox") else None
                return

            # 2) Reporte AW si es salida
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
                    ctk.CTkMessagebox(title="Genika Control", message="✅ Salida enviada con éxito (foto + reporte).",
                                      icon="check") if hasattr(ctk, "CTkMessagebox") else None
                else:
                    self.status.set(f"Foto: OK. Reporte AW: ERROR. {msg_aw}")
                    ctk.CTkMessagebox(title="Genika Control", message=f"❕ Reporte AW con error.\n{msg_aw}",
                                      icon="warning") if hasattr(ctk, "CTkMessagebox") else None

        except Exception as e:
            self.status.set(f"Error inesperado: {e}")
            ctk.CTkMessagebox(title="Genika Control", message=f"❌ Error inesperado:\n{e}",
                              icon="cancel") if hasattr(ctk, "CTkMessagebox") else None
        finally:
            try:
                photo_path.unlink(missing_ok=True)
            except Exception:
                pass
            self._close_progress()

    def _do_send_ayer(self):
        try:
            cid = str(uuid.uuid4())
            self.status.set("Preparando reporte de AYER…")
            payload = build_yesterday_payload(self.settings, meta_extra={
                "correlation_id": cid,
                "marcacion_tipo": "salida_ayer",
            })
            self.status.set("Enviando reporte de AYER…")
            ok_aw, msg_aw = send_payload(self.settings, payload)
            if ok_aw:
                self.status.set("Reporte de AYER: OK.")
                ctk.CTkMessagebox(title="Genika Control", message="✅ Informe de AYER enviado con éxito.",
                                  icon="check") if hasattr(ctk, "CTkMessagebox") else None
            else:
                self.status.set(f"Reporte de AYER: ERROR. {msg_aw}")
                ctk.CTkMessagebox(title="Genika Control", message=f"❕ Error al enviar informe de AYER.\n{msg_aw}",
                                  icon="warning") if hasattr(ctk, "CTkMessagebox") else None
        except Exception as e:
            self.status.set(f"Error inesperado: {e}")
            ctk.CTkMessagebox(title="Genika Control", message=f"❌ Error inesperado:\n{e}",
                              icon="cancel") if hasattr(ctk, "CTkMessagebox") else None
        finally:
            self._close_progress()

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
