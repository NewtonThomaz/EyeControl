"""Mapeamento matemático Físico -> Virtual (Suporta layouts Verticais e Horizontais).

Compatível com:
- Vertical: Secundário Acima (ex.: monitor empilhado no topo)
- Vertical: Secundário Abaixo
- Horizontal: Secundário à Direita (padrão mais comum)
- Horizontal: Secundário à Esquerda
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

from src.window_manager import MonitorRect


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class CoordinateMapper:
    """Converte vetores faciais normalizados em coordenadas virtuais do Windows."""

    MIN_DELTA = 0.015

    def __init__(self) -> None:
        self._last_position: Optional[Tuple[int, int]] = None
        self._last_monitor_idx: Optional[int] = None

    def reset_state(self) -> None:
        """Limpa a última posição registrada (ex.: após recalibrar ou mudar configuração)."""
        self._last_position = None
        self._last_monitor_idx = None

    def compute_position(
        self,
        raw_point: Tuple[float, float],
        primary_point: Tuple[float, float],
        secondary_point: Tuple[float, float],
        primary_mon: MonitorRect,
        secondary_mon: MonitorRect,
        window_size: Tuple[int, int],
        offset_direction: str,
        offset_distance: int,
        deadzone: int,
        monitor_layout: str = "Vertical: Secundário Acima",
    ) -> Tuple[int, int, int, bool]:
        """Calcula a nova posição (x, y, monitor_idx, should_move).

        monitor_idx: 1 para Monitor Principal, 2 para Monitor Secundário.
        should_move: True se o deslocamento superou a Zona Morta (deadzone).
        """
        raw_x, raw_y = raw_point
        x1, y1 = primary_point
        x2, y2 = secondary_point

        is_horizontal = monitor_layout.startswith("Horizontal")

        if is_horizontal:
            # Eixo dominante de transição entre telas: Horizontal (X)
            d_signed = x2 - x1
            if abs(d_signed) < self.MIN_DELTA:
                d_signed = self.MIN_DELTA if d_signed >= 0 else -self.MIN_DELTA

            # t = 0.0 -> Centro do Monitor 1 (Principal)
            # t = 0.5 -> Borda divisória entre os dois monitores
            # t = 1.0 -> Centro do Monitor 2 (Secundário)
            t = (raw_x - x1) / d_signed
            monitor_idx = 1 if t < 0.5 else 2
            active_mon = primary_mon if monitor_idx == 1 else secondary_mon

            # Razão de aspecto real do monitor ativo (ex.: 16/9, 21/9, etc.)
            aspect_ratio = max(0.5, active_mon.width / max(1, active_mon.height))
            span_x = max(abs(d_signed), self.MIN_DELTA)
            span_y = span_x / aspect_ratio

            # Posição X normalizada dentro do monitor ativo [0..1]
            center_x = x1 if monitor_idx == 1 else x2
            norm_x = _clamp(0.5 + (raw_x - center_x) / span_x, 0.0, 1.0)

            # Eixo Y de referência (alinhamento central proporcional)
            t_clamped = _clamp(t, 0.0, 1.0)
            y_center_ref = y1 + t_clamped * (y2 - y1)
            norm_y = _clamp(0.5 + (raw_y - y_center_ref) / span_y, 0.0, 1.0)

        else:
            # Eixo dominante de transição entre telas: Vertical (Y)
            d_signed = y2 - y1
            if abs(d_signed) < self.MIN_DELTA:
                d_signed = -self.MIN_DELTA if d_signed <= 0 else self.MIN_DELTA

            # t = 0.0 -> Centro do Monitor 1 (Principal)
            # t = 0.5 -> Borda divisória entre os dois monitores
            # t = 1.0 -> Centro do Monitor 2 (Secundário)
            t = (raw_y - y1) / d_signed
            monitor_idx = 1 if t < 0.5 else 2
            active_mon = primary_mon if monitor_idx == 1 else secondary_mon

            # Razão de aspecto real do monitor ativo
            aspect_ratio = max(0.5, active_mon.width / max(1, active_mon.height))
            span_y = max(abs(d_signed), self.MIN_DELTA)
            span_x = span_y * aspect_ratio

            # Posição Y normalizada dentro do monitor ativo [0..1]
            center_y = y1 if monitor_idx == 1 else y2
            norm_y = _clamp(0.5 + (raw_y - center_y) / span_y, 0.0, 1.0)

            # Eixo X de referência (compensação para câmera móvel/diagonal)
            t_clamped = _clamp(t, 0.0, 1.0)
            x_center_ref = x1 + t_clamped * (x2 - x1)
            norm_x = _clamp(0.5 + (raw_x - x_center_ref) / span_x, 0.0, 1.0)

        # Converte posições normalizadas para pixels virtuais do monitor ativo
        gaze_px_x = active_mon.left + norm_x * active_mon.width
        gaze_px_y = active_mon.top + norm_y * active_mon.height

        win_w, win_h = window_size
        target_x = gaze_px_x - (win_w / 2.0)
        target_y = gaze_px_y - (win_h / 2.0)

        # Deslocamento Periférico (RF-10 e RF-11)
        dist = float(max(0, offset_distance))
        if offset_direction == "Esquerda":
            target_x -= dist
        elif offset_direction == "Direita":
            target_x += dist
        elif offset_direction == "Cima":
            target_y -= dist
        elif offset_direction == "Baixo":
            target_y += dist

        # Clamping / Bounding Box (RF-12)
        min_x = float(active_mon.left)
        max_x = float(max(active_mon.left, active_mon.right - win_w))
        min_y = float(active_mon.top)
        max_y = float(max(active_mon.top, active_mon.bottom - win_h))

        final_x = int(round(_clamp(target_x, min_x, max_x)))
        final_y = int(round(_clamp(target_y, min_y, max_y)))

        # Zona Morta / Deadzone (RF-09)
        if self._last_position is None:
            self._last_position = (final_x, final_y)
            self._last_monitor_idx = monitor_idx
            return final_x, final_y, monitor_idx, True

        last_x, last_y = self._last_position
        displacement = math.hypot(final_x - last_x, final_y - last_y)

        if displacement < float(deadzone):
            return last_x, last_y, self._last_monitor_idx or monitor_idx, False

        self._last_position = (final_x, final_y)
        self._last_monitor_idx = monitor_idx
        return final_x, final_y, monitor_idx, True
