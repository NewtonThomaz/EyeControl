"""Gerenciamento de janelas e monitores via Win32 API (pywin32)."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from typing import List, Optional, Tuple

import win32api
import win32con
import win32gui

DWMWA_CLOAKED = 14

IGNORED_TITLES = {
    "Program Manager",
    "Windows Input Experience",
    "Microsoft Text Input Application",
    "EyeControl",
    "EyeControl - Calibração",
}


@dataclass(frozen=True)
class MonitorRect:
    """Representa as coordenadas virtuais de um monitor no Windows."""

    left: int
    top: int
    right: int
    bottom: int
    is_primary: bool
    device: str = ""

    @property
    def width(self) -> int:
        return max(1, self.right - self.left)

    @property
    def height(self) -> int:
        return max(1, self.bottom - self.top)

    @property
    def center(self) -> Tuple[int, int]:
        return (self.left + self.width // 2, self.top + self.height // 2)


@dataclass(frozen=True)
class WindowInfo:
    """Representa uma janela visível selecionável pelo usuário."""

    hwnd: int
    title: str

    @property
    def label(self) -> str:
        short_title = self.title if len(self.title) <= 55 else self.title[:52] + "..."
        return f"{short_title} (HWND: {self.hwnd})"


def _is_window_cloaked(hwnd: int) -> bool:
    """Verifica se a janela está oculta/cloaked pelo DWM do Windows 10/11."""
    try:
        cloaked = ctypes.c_int(0)
        hr = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            int(hwnd),
            DWMWA_CLOAKED,
            ctypes.byref(cloaked),
            ctypes.sizeof(cloaked),
        )
        return hr == 0 and cloaked.value != 0
    except Exception:
        return False


class WindowManager:
    """Encapsula operações de consulta de monitores, listagem e movimentação Win32."""

    @staticmethod
    def get_monitors() -> Tuple[MonitorRect, MonitorRect]:
        """Retorna (monitor_inferior_principal, monitor_superior_secundario).

        Consulta dinamicamente os retângulos virtuais configurados no Windows.
        Caso apenas 1 monitor seja detectado no momento, projeta um segundo monitor
        virtual de 1920x1080 à direita para evitar falhas.
        """
        monitors: List[MonitorRect] = []
        try:
            for hmon, _hdc, _rect in win32api.EnumDisplayMonitors():
                info = win32api.GetMonitorInfo(hmon)
                rc = info.get("Monitor", (0, 0, 1920, 1080))
                flags = info.get("Flags", 0)
                is_primary = bool(flags & win32con.MONITORINFOF_PRIMARY)
                device = str(info.get("Device", ""))
                monitors.append(
                    MonitorRect(
                        left=int(rc[0]),
                        top=int(rc[1]),
                        right=int(rc[2]),
                        bottom=int(rc[3]),
                        is_primary=is_primary,
                        device=device,
                    )
                )
        except Exception:
            pass

        primary: Optional[MonitorRect] = None
        secondary: Optional[MonitorRect] = None

        for m in monitors:
            if m.is_primary and primary is None:
                primary = m
            elif not m.is_primary and secondary is None:
                secondary = m

        if primary is None:
            if monitors:
                primary = monitors[0]
            else:
                primary = MonitorRect(0, 0, 1920, 1080, True, "DISPLAY1")

        if secondary is None:
            if len(monitors) > 1:
                secondary = [m for m in monitors if m != primary][0]
            else:
                secondary = MonitorRect(
                    left=primary.right,
                    top=primary.top,
                    right=primary.right + 1920,
                    bottom=primary.top + 1080,
                    is_primary=False,
                    device="DISPLAY2_VIRTUAL",
                )

        return primary, secondary

    @staticmethod
    def list_visible_windows(exclude_hwnds: Optional[set[int]] = None) -> List[WindowInfo]:
        """Lista todas as janelas visíveis de nível superior com título ativo."""
        results: List[WindowInfo] = []
        exclude = exclude_hwnds or set()

        def _enum_cb(hwnd: int, _extra: object) -> bool:
            if hwnd in exclude:
                return True
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd).strip()
            if not title or title in IGNORED_TITLES:
                return True
            if title.startswith("EyeControl"):
                return True
            if _is_window_cloaked(hwnd):
                return True

            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            if ex_style & win32con.WS_EX_TOOLWINDOW and not (
                ex_style & win32con.WS_EX_TOPMOST
            ):
                # Ignora toolwindows invisíveis do sistema, mas preserva overlays/PiP TOPMOST
                return True

            results.append(WindowInfo(hwnd=hwnd, title=title))
            return True

        try:
            win32gui.EnumWindows(_enum_cb, None)
        except Exception:
            pass

        results.sort(key=lambda w: w.title.lower())
        return results

    @staticmethod
    def is_valid_window(hwnd: Optional[int]) -> bool:
        if not hwnd:
            return False
        try:
            return bool(win32gui.IsWindow(int(hwnd)))
        except Exception:
            return False

    @staticmethod
    def get_window_rect(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
        """Retorna (left, top, right, bottom) da janela alvo."""
        try:
            if not win32gui.IsWindow(hwnd):
                return None
            return win32gui.GetWindowRect(hwnd)
        except Exception:
            return None

    @staticmethod
    def get_window_size(hwnd: int) -> Tuple[int, int]:
        """Retorna (largura, altura) atual da janela alvo, preservando redimensionamento do usuário."""
        rect = WindowManager.get_window_rect(hwnd)
        if rect is None:
            return (400, 300)
        w = max(50, rect[2] - rect[0])
        h = max(50, rect[3] - rect[1])
        return (w, h)

    @staticmethod
    def move_window(hwnd: int, x: int, y: int) -> bool:
        """Move a janela para (x, y) sem alterar tamanho, Z-Order ou foco de digitação."""
        if not hwnd:
            return False
        try:
            if not win32gui.IsWindow(hwnd):
                return False
            win32gui.SetWindowPos(
                int(hwnd),
                0,
                int(x),
                int(y),
                0,
                0,
                win32con.SWP_NOSIZE
                | win32con.SWP_NOZORDER
                | win32con.SWP_NOACTIVATE
                | win32con.SWP_SHOWWINDOW,
            )
            return True
        except Exception:
            return False

