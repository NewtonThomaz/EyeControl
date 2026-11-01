"""Testes automatizados dos módulos centrais do EyeControl (Suporta layouts Horizontais e Verticais)."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
import statistics
import tempfile
import unittest

import numpy as np

from src.config import ConfigManager
from src.coordinate_mapper import CoordinateMapper
from src.hotkey_manager import format_hotkey_display
from src.tracker import FaceTracker, _MediaPipeFaceDetector
from src.window_manager import MonitorRect, WindowManager


@dataclass
class _DummyLandmark:
    x: float
    y: float
    z: float = 0.0


class TestEyeControlCore(unittest.TestCase):
    def setUp(self) -> None:
        self.mon1 = MonitorRect(0, 0, 1920, 1080, is_primary=True, device="DISPLAY1")
        self.mon2 = MonitorRect(
            1920, 0, 3840, 1080, is_primary=False, device="DISPLAY2"
        )
        self.win_size = (400, 300)

    def test_vertical_layout_zero_delta_x(self) -> None:
        """Layout Vertical: Calibração com mesmo X (0.50) nos 2 monitores empilhados."""
        mapper = CoordinateMapper()
        p1 = (0.50, 0.65)
        p2 = (0.50, 0.35)

        # Olhando no centro do Monitor 1 (Inferior) sem offset
        x1, y1, mon_idx1, moved1 = mapper.compute_position(
            raw_point=(0.50, 0.65),
            primary_point=p1,
            secondary_point=p2,
            primary_mon=self.mon1,
            secondary_mon=self.mon2,
            window_size=self.win_size,
            offset_direction="Desligado",
            offset_distance=200,
            deadzone=30,
            monitor_layout="Vertical: Secundário Acima",
        )
        self.assertTrue(moved1)
        self.assertEqual(mon_idx1, 1)
        self.assertEqual(x1, 960 - 200)
        self.assertEqual(y1, 540 - 150)

        # Olhando no centro do Monitor 2 (Superior) sem offset
        x2, y2, mon_idx2, moved2 = mapper.compute_position(
            raw_point=(0.50, 0.35),
            primary_point=p1,
            secondary_point=p2,
            primary_mon=self.mon1,
            secondary_mon=self.mon2,
            window_size=self.win_size,
            offset_direction="Desligado",
            offset_distance=200,
            deadzone=30,
            monitor_layout="Vertical: Secundário Acima",
        )
        self.assertTrue(moved2)
        self.assertEqual(mon_idx2, 2)
        self.assertEqual(x2, 1920 + 960 - 200)
        self.assertEqual(y2, 540 - 150)

    def test_horizontal_layout_zero_delta_y(self) -> None:
        """Layout Horizontal: Monitores lado a lado com mesmo Y (0.50) e transição no eixo X."""
        mapper = CoordinateMapper()
        # Monitor 1 à esquerda (x=0.40), Monitor 2 à direita (x=0.60), ambos na mesma altura (y=0.50)
        p1 = (0.40, 0.50)
        p2 = (0.60, 0.50)

        # Olhando no centro do Monitor 1
        x1, y1, mon_idx1, moved1 = mapper.compute_position(
            raw_point=(0.40, 0.50),
            primary_point=p1,
            secondary_point=p2,
            primary_mon=self.mon1,
            secondary_mon=self.mon2,
            window_size=self.win_size,
            offset_direction="Desligado",
            offset_distance=200,
            deadzone=30,
            monitor_layout="Horizontal: Secundário à Direita",
        )
        self.assertTrue(moved1)
        self.assertEqual(mon_idx1, 1)
        self.assertEqual(x1, 960 - 200)
        self.assertEqual(y1, 540 - 150)

        # Olhando no centro do Monitor 2
        x2, y2, mon_idx2, moved2 = mapper.compute_position(
            raw_point=(0.60, 0.50),
            primary_point=p1,
            secondary_point=p2,
            primary_mon=self.mon1,
            secondary_mon=self.mon2,
            window_size=self.win_size,
            offset_direction="Desligado",
            offset_distance=200,
            deadzone=30,
            monitor_layout="Horizontal: Secundário à Direita",
        )
        self.assertTrue(moved2)
        self.assertEqual(mon_idx2, 2)
        self.assertEqual(x2, 1920 + 960 - 200)
        self.assertEqual(y2, 540 - 150)

    def test_median_filter_discards_blink_outlier(self) -> None:
        """Buffer circular de 5 amostras filtra piscadas/outliers via mediana."""
        buf: deque[tuple[float, float]] = deque(maxlen=5)
        samples = [
            (0.50, 0.60),
            (0.51, 0.61),
            (0.95, 0.10),  # Outlier
            (0.49, 0.60),
            (0.50, 0.59),
        ]
        for s in samples:
            buf.append(s)

        med_x = statistics.median(pt[0] for pt in buf)
        med_y = statistics.median(pt[1] for pt in buf)
        self.assertAlmostEqual(med_x, 0.50, places=2)
        self.assertAlmostEqual(med_y, 0.60, places=2)

    def test_deadzone_prevents_micro_jitter(self) -> None:
        """RF-09: Pequenas oscilações abaixo da deadzone não devem mover a janela."""
        mapper = CoordinateMapper()
        p1 = (0.50, 0.65)
        p2 = (0.50, 0.35)

        x1, y1, _, moved1 = mapper.compute_position(
            raw_point=(0.50, 0.65),
            primary_point=p1,
            secondary_point=p2,
            primary_mon=self.mon1,
            secondary_mon=self.mon2,
            window_size=self.win_size,
            offset_direction="Direita",
            offset_distance=150,
            deadzone=50,
        )
        self.assertTrue(moved1)

        # Oscilação mínima de olhar (< 50px)
        x2, y2, _, moved2 = mapper.compute_position(
            raw_point=(0.502, 0.648),
            primary_point=p1,
            secondary_point=p2,
            primary_mon=self.mon1,
            secondary_mon=self.mon2,
            window_size=self.win_size,
            offset_direction="Direita",
            offset_distance=150,
            deadzone=50,
        )
        self.assertFalse(moved2)
        self.assertEqual((x1, y1), (x2, y2))

    def test_clamping_keeps_window_inside_monitor_bounds(self) -> None:
        """RF-12: O offset nunca pode empurrar a janela para fora do monitor ativo."""
        mapper = CoordinateMapper()
        p1 = (0.50, 0.65)
        p2 = (0.50, 0.35)

        # Olhando bem para a direita no Monitor 1 com offset de +600px para a Direita
        x, y, mon_idx, _ = mapper.compute_position(
            raw_point=(0.95, 0.65),
            primary_point=p1,
            secondary_point=p2,
            primary_mon=self.mon1,
            secondary_mon=self.mon2,
            window_size=self.win_size,
            offset_direction="Direita",
            offset_distance=600,
            deadzone=10,
        )
        self.assertEqual(mon_idx, 1)
        self.assertLessEqual(x + self.win_size[0], self.mon1.right)
        self.assertGreaterEqual(x, self.mon1.left)
        self.assertGreaterEqual(y, self.mon1.top)
        self.assertLessEqual(y + self.win_size[1], self.mon1.bottom)

    def test_extract_head_vector_and_mediapipe_detector(self) -> None:
        fake_lms = [_DummyLandmark(0.5, 0.5) for _ in range(468)]
        fake_lms[1] = _DummyLandmark(0.5, 0.5)
        fake_lms[10] = _DummyLandmark(0.5, 0.3)
        fake_lms[152] = _DummyLandmark(0.5, 0.7)
        fake_lms[234] = _DummyLandmark(0.3, 0.5)
        fake_lms[454] = _DummyLandmark(0.7, 0.5)

        vec = FaceTracker.extract_head_vector(fake_lms)
        self.assertIsNotNone(vec)
        assert vec is not None
        self.assertAlmostEqual(vec[0], 0.5, places=3)
        self.assertAlmostEqual(vec[1], 0.5, places=3)

        detector = _MediaPipeFaceDetector()
        blank = np.zeros((240, 320, 3), dtype=np.uint8)
        res = detector.detect_landmarks(blank)
        self.assertIsNone(res)
        detector.close()

    def test_config_persistence_and_median_calibration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = Path(tmpdir) / "settings.json"
            cfg = ConfigManager(path=cfg_path)
            self.assertEqual(cfg.get("fps"), 5)
            self.assertEqual(cfg.get("monitor_layout"), "Vertical: Secundário Acima")
            cfg.set("monitor_layout", "Horizontal: Secundário à Direita")
            cfg.set_calibration((0.48, 0.62), (0.51, 0.38))

            cfg2 = ConfigManager(path=cfg_path)
            self.assertEqual(cfg2.get("monitor_layout"), "Horizontal: Secundário à Direita")
            is_cal, p1, p2 = cfg2.get_calibration()
            self.assertTrue(is_cal)
            self.assertAlmostEqual(p1[0], 0.48, places=4)
            self.assertAlmostEqual(p2[1], 0.38, places=4)

    def test_win32_monitors_and_windows_enumeration(self) -> None:
        m1, m2 = WindowManager.get_monitors()
        self.assertGreater(m1.width, 0)
        self.assertGreater(m2.width, 0)
        wins = WindowManager.list_visible_windows()
        self.assertIsInstance(wins, list)

    def test_hotkey_display_formatting(self) -> None:
        self.assertEqual(format_hotkey_display("ctrl+f9"), "Ctrl + F9")
        self.assertEqual(format_hotkey_display("alt+shift+x"), "Alt + Shift + X")


if __name__ == "__main__":
    unittest.main()
