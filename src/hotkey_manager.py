"""Gerenciador de atalhos globais em modo de usuário padrão (sem privilégios de Admin)."""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional, Set

from pynput import keyboard

MODIFIER_MAP = {
    "ctrl_l": "ctrl",
    "ctrl_r": "ctrl",
    "ctrl": "ctrl",
    "alt_l": "alt",
    "alt_r": "alt",
    "alt_gr": "alt",
    "alt": "alt",
    "shift_l": "shift",
    "shift_r": "shift",
    "shift": "shift",
    "cmd": "win",
    "cmd_l": "win",
    "cmd_r": "win",
}

MODIFIER_ORDER = ["ctrl", "alt", "shift", "win"]


def _normalize_key(key: keyboard.Key | keyboard.KeyCode | None) -> Optional[str]:
    """Converte uma tecla do pynput em token textual padronizado."""
    if key is None:
        return None
    if isinstance(key, keyboard.Key):
        name = str(key.name).lower()
        return MODIFIER_MAP.get(name, name)
    if isinstance(key, keyboard.KeyCode):
        if key.char:
            # Trata caracteres de controle quando Ctrl está pressionado (ex.: \x01 -> 'a')
            code = ord(key.char)
            if 1 <= code <= 26:
                return chr(code + 96)
            return key.char.lower()
        if key.vk is not None:
            vk = int(key.vk)
            if 65 <= vk <= 90:
                return chr(vk + 32)
            if 48 <= vk <= 57:
                return chr(vk)
            if 112 <= vk <= 135:
                return f"f{vk - 111}"
    return None


def format_hotkey_display(hotkey_str: str) -> str:
    """Formata 'ctrl+f9' para exibição amigável 'Ctrl + F9'."""
    parts = [p.strip().lower() for p in hotkey_str.split("+") if p.strip()]
    formatted = [p.upper() if p.startswith("f") and len(p) <= 3 else p.capitalize() for p in parts]
    return " + ".join(formatted) if formatted else "Ctrl + F9"


class HotkeyManager:
    """Monitora o atalho global de alternância (Toggle) e permite gravar novos atalhos."""

    def __init__(
        self,
        hotkey_str: str,
        on_toggle_callback: Callable[[], None],
        on_recorded_callback: Callable[[str], None],
    ) -> None:
        self.on_toggle_callback = on_toggle_callback
        self.on_recorded_callback = on_recorded_callback

        self._lock = threading.RLock()
        self._target_keys: Set[str] = set()
        self._hotkey_str = "ctrl+f9"
        self.set_hotkey(hotkey_str)

        self._pressed_keys: Set[str] = set()
        self._recording = False
        self._recorded_modifiers: Set[str] = set()
        self._last_trigger_ts = 0.0

        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()

    @property
    def hotkey_str(self) -> str:
        with self._lock:
            return self._hotkey_str

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._recording

    def set_hotkey(self, hotkey_str: str) -> None:
        parts = {p.strip().lower() for p in hotkey_str.split("+") if p.strip()}
        if not parts:
            parts = {"ctrl", "f9"}
        with self._lock:
            self._target_keys = parts
            ordered = [m for m in MODIFIER_ORDER if m in parts] + sorted(
                k for k in parts if k not in MODIFIER_ORDER
            )
            self._hotkey_str = "+".join(ordered)

    def start_recording(self) -> None:
        with self._lock:
            self._recording = True
            self._recorded_modifiers.clear()
            self._pressed_keys.clear()

    def cancel_recording(self) -> None:
        with self._lock:
            self._recording = False
            self._recorded_modifiers.clear()

    def stop(self) -> None:
        try:
            self._listener.stop()
        except Exception:
            pass

    def _on_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        token = _normalize_key(key)
        if not token:
            return

        with self._lock:
            if self._recording:
                if token == "esc":
                    self._recording = False
                    self._recorded_modifiers.clear()
                    self.on_recorded_callback(self._hotkey_str)
                    return

                if token in MODIFIER_ORDER:
                    self._recorded_modifiers.add(token)
                    return

                # Tecla final pressionada durante a gravação
                mods = [m for m in MODIFIER_ORDER if m in self._recorded_modifiers]
                new_hotkey = "+".join(mods + [token])
                self._recording = False
                self._recorded_modifiers.clear()
                self.set_hotkey(new_hotkey)
                self.on_recorded_callback(self._hotkey_str)
                return

            self._pressed_keys.add(token)
            if self._target_keys and self._target_keys.issubset(self._pressed_keys):
                now = time.monotonic()
                if now - self._last_trigger_ts >= 0.45:
                    self._last_trigger_ts = now
                    self.on_toggle_callback()

    def _on_release(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        token = _normalize_key(key)
        if not token:
            return
        with self._lock:
            self._pressed_keys.discard(token)
            if self._recording and token in MODIFIER_ORDER:
                self._recorded_modifiers.discard(token)

