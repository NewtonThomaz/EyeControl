"""Utilitário para criar/atualizar o atalho do EyeControl no Menu Iniciar do Windows."""

from __future__ import annotations

import os
from pathlib import Path


def ensure_start_menu_shortcut() -> bool:
    """Cria ou atualiza o atalho 'EyeControl.lnk' no Menu Iniciar para que o Windows Search o localize."""
    try:
        import win32com.client

        appdata = os.environ.get("APPDATA")
        if not appdata:
            return False

        start_menu_dir = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        start_menu_dir.mkdir(parents=True, exist_ok=True)
        shortcut_path = start_menu_dir / "EyeControl.lnk"

        proj_dir = Path(__file__).resolve().parent.parent
        pythonw_path = proj_dir / ".venv" / "Scripts" / "pythonw.exe"
        icon_path = proj_dir / "src" / "assets" / "icon.ico"

        if not pythonw_path.exists():
            return False

        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(str(shortcut_path))
        shortcut.TargetPath = str(pythonw_path)
        shortcut.Arguments = "-m src.main"
        shortcut.WorkingDirectory = str(proj_dir)
        if icon_path.exists():
            shortcut.IconLocation = f"{icon_path},0"
        shortcut.Description = "EyeControl - Rastreamento e Sobreposicao Multimonitor"
        shortcut.Save()
        return True
    except Exception:
        return False


if __name__ == "__main__":
    ok = ensure_start_menu_shortcut()
    print("Atalho do Menu Iniciar criado/atualizado:", ok)
