"""Janela semitransparente em tela cheia para a Calibração em 2 Pontos (Cruz + Barra de Espaço)."""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional, Tuple

from src.tracker import FaceTracker
from src.window_manager import MonitorRect, WindowManager


class CalibrationOverlay:
    """Projeta uma cruz central primeiro no Monitor Principal e depois no Monitor Secundário."""

    def __init__(
        self,
        parent: tk.Misc,
        tracker: FaceTracker,
        on_complete: Callable[[Tuple[float, float], Tuple[float, float]], None],
        on_cancel: Callable[[], None],
        monitor_layout: str = "Vertical: Secundário Acima",
    ) -> None:
        self.parent = parent
        self.tracker = tracker
        self.on_complete = on_complete
        self.on_cancel = on_cancel
        self.monitor_layout = monitor_layout

        self.primary_mon, self.secondary_mon = WindowManager.get_monitors()
        self.step = 1
        self.primary_point: Optional[Tuple[float, float]] = None
        self._closed = False

        self.tracker.set_calibration_mode(True)

        self.win = tk.Toplevel(parent)
        self.win.title("EyeControl - Calibração")
        self.win.configure(bg="#0D1117")
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.88)

        self.canvas = tk.Canvas(
            self.win,
            bg="#0D1117",
            highlightthickness=0,
            bd=0,
            cursor="crosshair",
        )
        self.canvas.pack(fill="both", expand=True)

        self.win.bind("<space>", self._on_space_pressed)
        self.win.bind("<Escape>", self._on_escape_pressed)
        self.canvas.bind("<Button-1>", lambda _e: self.win.focus_force())

        self._show_step_1()
        self._poll_sensor_status()

    def _get_step_titles(self) -> Tuple[str, str]:
        if self.step == 1:
            return (
                "ETAPA 1 DE 2 — MONITOR PRINCIPAL (1)",
                "Foque os olhos exatamente no ponto central da cruz acima",
            )
        layout_name = self.monitor_layout.split(":")[-1].strip().upper()
        return (
            f"ETAPA 2 DE 2 — MONITOR SECUNDÁRIO ({layout_name})",
            "Agora olhe para o centro da cruz neste monitor e pressione ESPAÇO",
        )

    def _apply_monitor_geometry(self, mon: MonitorRect) -> None:
        geom = f"{mon.width}x{mon.height}+{mon.left}+{mon.top}"
        self.win.geometry(geom)
        self.win.update_idletasks()
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()

    def _draw_crosshair(
        self,
        mon: MonitorRect,
        step_title: str,
        subtitle: str,
        sensor_text: str,
        sensor_color: str,
    ) -> None:
        self.canvas.delete("all")
        cx = mon.width // 2
        cy = mon.height // 2
        arm = 48
        gap = 8

        # Círculo externo sutil ao redor da cruz
        self.canvas.create_oval(
            cx - 32,
            cy - 32,
            cx + 32,
            cy + 32,
            outline="#38BDF8",
            width=2,
        )

        # Linhas da cruz central
        self.canvas.create_line(
            cx - arm, cy, cx - gap, cy, fill="#00F5D4", width=4
        )
        self.canvas.create_line(
            cx + gap, cy, cx + arm, cy, fill="#00F5D4", width=4
        )
        self.canvas.create_line(
            cx, cy - arm, cx, cy - gap, fill="#00F5D4", width=4
        )
        self.canvas.create_line(
            cx, cy + gap, cx, cy + arm, fill="#00F5D4", width=4
        )

        # Ponto central exato de fixação
        self.canvas.create_oval(
            cx - 4,
            cy - 4,
            cx + 4,
            cy + 4,
            fill="#FF2A85",
            outline="#FFFFFF",
            width=1,
        )

        # Instruções abaixo da cruz
        self.canvas.create_text(
            cx,
            cy + 85,
            text=step_title,
            fill="#F8FAFC",
            font=("Segoe UI", 18, "bold"),
        )
        self.canvas.create_text(
            cx,
            cy + 120,
            text=subtitle,
            fill="#94A3B8",
            font=("Segoe UI", 13),
        )
        self.canvas.create_text(
            cx,
            cy + 155,
            text=sensor_text,
            fill=sensor_color,
            font=("Segoe UI", 12, "bold"),
            tags="sensor_status",
        )
        self.canvas.create_text(
            cx,
            cy + 190,
            text="Pressione [ESPAÇO] para capturar  •  [ESC] para cancelar",
            fill="#64748B",
            font=("Segoe UI", 11),
        )

    def _get_sensor_label(self) -> Tuple[str, str]:
        if not self.tracker.is_camera_open:
            return ("Iniciando webcam...", "#FBBF24")
        if self.tracker.is_face_detected:
            return (
                "✓ Rosto detectado — Olhe no centro da cruz e aperte ESPAÇO",
                "#34D399",
            )
        return (
            "⚠ Rosto não detectado — Posicione-se de frente para a webcam",
            "#F87171",
        )

    def _show_step_1(self) -> None:
        self.step = 1
        self._apply_monitor_geometry(self.primary_mon)
        s_txt, s_col = self._get_sensor_label()
        title, sub = self._get_step_titles()
        self._draw_crosshair(self.primary_mon, title, sub, s_txt, s_col)

    def _show_step_2(self) -> None:
        self.step = 2
        self.tracker.set_calibration_mode(True)
        self._apply_monitor_geometry(self.secondary_mon)
        s_txt, s_col = self._get_sensor_label()
        title, sub = self._get_step_titles()
        self._draw_crosshair(self.secondary_mon, title, sub, s_txt, s_col)

    def _poll_sensor_status(self) -> None:
        if self._closed or not self.win.winfo_exists():
            return
        mon = self.primary_mon if self.step == 1 else self.secondary_mon
        s_txt, s_col = self._get_sensor_label()
        title, sub = self._get_step_titles()
        self._draw_crosshair(mon, title, sub, s_txt, s_col)
        self.win.after(200, self._poll_sensor_status)

    def _on_space_pressed(self, _event: Optional[tk.Event] = None) -> None:
        if self._closed:
            return
        sample = self.tracker.get_median_sample()
        if sample is None or not self.tracker.is_face_detected:
            self.canvas.delete("sensor_status")
            mon = self.primary_mon if self.step == 1 else self.secondary_mon
            self.canvas.create_text(
                mon.width // 2,
                (mon.height // 2) + 155,
                text="⚠ Nenhum rosto capturado ainda! Aguarde o indicador ficar verde.",
                fill="#EF4444",
                font=("Segoe UI", 12, "bold"),
                tags="sensor_status",
            )
            return

        if self.step == 1:
            self.primary_point = sample
            self._show_step_2()
        elif self.step == 2 and self.primary_point is not None:
            secondary_pt = sample
            primary_pt = self.primary_point
            self._close_internal()
            self.on_complete(primary_pt, secondary_pt)

    def _on_escape_pressed(self, _event: Optional[tk.Event] = None) -> None:
        if self._closed:
            return
        self._close_internal()
        self.on_cancel()

    def _close_internal(self) -> None:
        self._closed = True
        self.tracker.set_calibration_mode(False)
        try:
            if self.win.winfo_exists():
                self.win.destroy()
        except Exception:
            pass
