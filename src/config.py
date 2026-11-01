"""Gerenciamento e persistência de configurações do EyeControl."""

from __future__ import annotations

import json
from pathlib import Path
import threading
from typing import Any, Dict, List, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
SETTINGS_PATH = ROOT_DIR / "settings.json"

OFFSET_DIRECTIONS = ["Desligado", "Esquerda", "Direita", "Cima", "Baixo"]

MONITOR_LAYOUTS = [
    "Vertical: Secundário Acima",
    "Vertical: Secundário Abaixo",
    "Horizontal: Secundário à Direita",
    "Horizontal: Secundário à Esquerda",
]

DEFAULT_CONFIG: Dict[str, Any] = {
    "fps": 5,
    "monitor_layout": "Vertical: Secundário Acima",
    "offset_direction": "Direita",
    "offset_distance": 200,
    "deadzone": 40,
    "hotkey": "ctrl+f9",
    "camera_index": 0,
    "target_window_title": "",
    "calibration": {
        "is_calibrated": False,
        "primary_point": [0.5, 0.60],
        "secondary_point": [0.5, 0.40],
    },
}


class ConfigManager:
    """Gerencia leitura e escrita thread-safe do arquivo settings.json."""

    def __init__(self, path: Path = SETTINGS_PATH) -> None:
        self.path = path
        self._lock = threading.RLock()
        self.data: Dict[str, Any] = {}
        self.load()

    def load(self) -> Dict[str, Any]:
        """Carrega configurações do disco ou inicializa com os padrões."""
        with self._lock:
            merged = json.loads(json.dumps(DEFAULT_CONFIG))
            if self.path.exists():
                try:
                    with open(self.path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                    if isinstance(loaded, dict):
                        for k, v in loaded.items():
                            if k == "calibration" and isinstance(v, dict):
                                # Retrocompatibilidade com bottom_point / top_point
                                if "bottom_point" in v and "primary_point" not in v:
                                    v["primary_point"] = v["bottom_point"]
                                if "top_point" in v and "secondary_point" not in v:
                                    v["secondary_point"] = v["top_point"]
                                merged["calibration"].update(v)
                            else:
                                merged[k] = v
                except Exception:
                    pass
            self.data = merged
            self._validate()
            return self.data

    def _validate(self) -> None:
        """Garante que os valores estejam dentro das faixas válidas."""
        self.data["fps"] = max(1, min(15, int(self.data.get("fps", 5))))
        if self.data.get("offset_direction") not in OFFSET_DIRECTIONS:
            self.data["offset_direction"] = "Direita"
        if self.data.get("monitor_layout") not in MONITOR_LAYOUTS:
            self.data["monitor_layout"] = "Vertical: Secundário Acima"
        self.data["offset_distance"] = max(
            50, min(600, int(self.data.get("offset_distance", 200)))
        )
        self.data["deadzone"] = max(
            10, min(150, int(self.data.get("deadzone", 40)))
        )
        try:
            self.data["camera_index"] = max(0, min(10, int(self.data.get("camera_index", 0))))
        except Exception:
            self.data["camera_index"] = 0

        hotkey = str(self.data.get("hotkey", "ctrl+f9")).strip().lower()
        self.data["hotkey"] = hotkey if hotkey else "ctrl+f9"

    def save(self) -> None:
        """Persiste as configurações atuais em disco."""
        with self._lock:
            self._validate()
            try:
                with open(self.path, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self.data.get(key, default)

    def set(self, key: str, value: Any, auto_save: bool = True) -> None:
        with self._lock:
            self.data[key] = value
            if auto_save:
                self.save()

    def get_calibration(self) -> Tuple[bool, Tuple[float, float], Tuple[float, float]]:
        with self._lock:
            cal = self.data.get("calibration", {})
            is_cal = bool(cal.get("is_calibrated", False))
            p1: List[float] = cal.get("primary_point", cal.get("bottom_point", [0.5, 0.60]))
            p2: List[float] = cal.get("secondary_point", cal.get("top_point", [0.5, 0.40]))
            return is_cal, (float(p1[0]), float(p1[1])), (float(p2[0]), float(p2[1]))

    def set_calibration(
        self, primary_point: Tuple[float, float], secondary_point: Tuple[float, float]
    ) -> None:
        with self._lock:
            self.data["calibration"] = {
                "is_calibrated": True,
                "primary_point": [round(float(primary_point[0]), 5), round(float(primary_point[1]), 5)],
                "secondary_point": [round(float(secondary_point[0]), 5), round(float(secondary_point[1]), 5)],
            }
            self.save()
