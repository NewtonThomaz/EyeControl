"""Utilitários para descoberta e enumeração de webcams no Windows com nomes reais."""

from __future__ import annotations

from typing import List, Tuple


def get_available_cameras() -> List[Tuple[int, str]]:
    """Retorna uma lista de tuplas (indice_camera, nome_dispositivo).

    Utiliza pygrabber / DirectShow para obter os nomes reais das câmeras (ex.: Logi C270,
    NVIDIA Broadcast, OBS Virtual Camera) na mesma ordem de indexação do OpenCV DirectShow.
    """
    devices: List[Tuple[int, str]] = []

    # Tentativa 1: DirectShow via pygrabber (mais preciso com cv2.CAP_DSHOW)
    try:
        from pygrabber.dshow_graph import FilterGraph

        dshow_names = FilterGraph().get_input_devices()
        if dshow_names:
            for idx, name in enumerate(dshow_names):
                cleaned_name = str(name).strip()
                devices.append((idx, cleaned_name))
            return devices
    except Exception:
        pass

    # Tentativa 2: WMI / PnP (fallback)
    try:
        import win32com.client

        wmi = win32com.client.GetObject("winmgmts:")
        pnp_names: List[str] = []
        for item in wmi.InstancesOf("Win32_PnPEntity"):
            if getattr(item, "PNPClass", "") in ("Camera", "Image"):
                pnp_names.append(str(item.Name).strip())
        if pnp_names:
            for idx, name in enumerate(pnp_names):
                devices.append((idx, name))
            return devices
    except Exception:
        pass

    # Fallback genérico caso nenhum enumerador responda
    return [(0, "Webcam Principal (0)"), (1, "Câmera Secundária (1)")]

