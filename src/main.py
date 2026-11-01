"""Ponto de entrada do EyeControl.

IMPORTANTE (Ajuste Crítico #4):
A chamada SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
DEVE ser executada na primeira linha, antes de qualquer import do CustomTkinter/Tkinter,
para evitar ERROR_ACCESS_DENIED na API Win32.
"""

from __future__ import annotations

import ctypes
from pathlib import Path
import sys


def _enable_per_monitor_dpi_v2() -> None:
    """Ativa DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 (-4) antes de carregar a GUI."""
    try:
        # -4 corresponde a DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 no Windows 10/11
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            # Fallback para PROCESS_PER_MONITOR_DPI_AWARE (2) via shcore
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass


def _set_app_user_model_id() -> None:
    """Configura o AppUserModelID para o Windows exibir o ícone customizado na barra de tarefas."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "newtonthomaz.eyecontrol.desktop.1.0"
        )
    except Exception:
        pass


# Execução prioritária na linha 1 antes de importar CustomTkinter
_enable_per_monitor_dpi_v2()
_set_app_user_model_id()

# Garante que a raiz do projeto esteja no sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config import ConfigManager  # noqa: E402
from src.shortcut_utils import ensure_start_menu_shortcut  # noqa: E402
from src.ui import EyeControlApp  # noqa: E402


def main() -> None:
    # Garante que o atalho no Menu Iniciar do Windows esteja ativo para pesquisa rápida
    try:
        ensure_start_menu_shortcut()
    except Exception:
        pass

    config = ConfigManager()
    app = EyeControlApp(config)
    app.mainloop()


if __name__ == "__main__":
    main()
