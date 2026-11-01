"""Motor de rastreamento facial em thread dedicada (OpenCV + MediaPipe Face Mesh / FaceLandmarker)."""

from __future__ import annotations

from collections import deque
from pathlib import Path
import statistics
import threading
import time
from typing import Any, Callable, Deque, Optional, Sequence, Tuple
import urllib.request

import cv2
import mediapipe as mp

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
)
MODEL_PATH = Path(__file__).resolve().parent / "models" / "face_landmarker.task"


def _ensure_landmarker_model() -> Path:
    """Garante que o arquivo face_landmarker.task esteja disponível localmente."""
    if not MODEL_PATH.exists():
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    return MODEL_PATH


class _MediaPipeFaceDetector:
    """Abstrai a compatibilidade entre mp.solutions.face_mesh e mp.tasks.vision.FaceLandmarker."""

    def __init__(self) -> None:
        self._use_tasks = not hasattr(mp, "solutions")
        self._detector: Any = None

        if not self._use_tasks:
            self._detector = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=False,
                max_num_faces=1,
                refine_landmarks=False,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
        else:
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision as mp_vision

            model_file = _ensure_landmarker_model()
            with open(model_file, "rb") as f:
                model_buffer = f.read()

            options = mp_vision.FaceLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_buffer=model_buffer),
                running_mode=mp_vision.RunningMode.IMAGE,
                num_faces=1,
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
                min_tracking_confidence=0.5,
                output_face_blendshapes=False,
                output_facial_transformation_matrixes=False,
            )
            self._detector = mp_vision.FaceLandmarker.create_from_options(options)

    def detect_landmarks(self, rgb_frame: Any) -> Optional[Sequence[Any]]:
        """Processa um frame RGB (320x240) e retorna a sequência de 468+ landmarks da face."""
        if not self._use_tasks:
            res = self._detector.process(rgb_frame)
            if res and res.multi_face_landmarks:
                return res.multi_face_landmarks[0].landmark
            return None

        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        res = self._detector.detect(mp_img)
        if res and res.face_landmarks:
            return res.face_landmarks[0]
        return None

    def close(self) -> None:
        if self._detector is not None:
            try:
                self._detector.close()
            except Exception:
                pass


class FaceTracker:
    """Executa captura de webcam (320x240) e extração de orientação facial em baixa frequência."""

    def __init__(
        self,
        on_sample_callback: Callable[[Tuple[float, float]], None],
        on_status_change_callback: Callable[[bool, bool, str], None],
        camera_index: int = 0,
        fps: int = 5,
    ) -> None:
        """Inicializa o rastreador.

        on_sample_callback(point): chamado a cada leitura válida (x, y) quando ativo.
        on_status_change_callback(tracking_active, camera_open, message): notifica estado.
        """
        self.on_sample_callback = on_sample_callback
        self.on_status_change_callback = on_status_change_callback
        self.camera_index = max(0, min(10, int(camera_index)))
        self._fps = max(1, min(15, int(fps)))

        self._lock = threading.RLock()
        self._tracking_active = False
        self._calibration_mode = False
        self._running = True
        self._camera_open = False
        self._face_detected = False
        self._reopen_camera_requested = False

        # Buffer circular das últimas 5 leituras válidas para mediana na calibração
        self._sample_buffer: Deque[Tuple[float, float]] = deque(maxlen=5)
        self._latest_sample: Optional[Tuple[float, float]] = None

        self._wake_event = threading.Event()
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()

    @property
    def is_tracking(self) -> bool:
        with self._lock:
            return self._tracking_active

    @property
    def is_calibrating(self) -> bool:
        with self._lock:
            return self._calibration_mode

    @property
    def is_camera_open(self) -> bool:
        with self._lock:
            return self._camera_open

    @property
    def is_face_detected(self) -> bool:
        with self._lock:
            return self._face_detected

    def set_camera_index(self, index: int) -> None:
        """Permite trocar de webcam em tempo de execução sem reiniciar o app."""
        with self._lock:
            idx = max(0, min(10, int(index)))
            if self.camera_index != idx:
                self.camera_index = idx
                if self._camera_open:
                    self._reopen_camera_requested = True
                    self._wake_event.set()

    def set_fps(self, fps: int) -> None:
        with self._lock:
            self._fps = max(1, min(15, int(fps)))

    def get_fps(self) -> int:
        with self._lock:
            return self._fps

    def set_tracking(self, active: bool) -> None:
        """Ativa ou desativa o rastreamento contínuo."""
        with self._lock:
            if self._tracking_active == active:
                return
            self._tracking_active = active
            self._wake_event.set()

    def toggle_tracking(self) -> bool:
        """Alterna o estado do rastreamento (Toggle ON/OFF) e retorna o novo estado."""
        with self._lock:
            self._tracking_active = not self._tracking_active
            new_state = self._tracking_active
            self._wake_event.set()
            return new_state

    def set_calibration_mode(self, active: bool) -> None:
        """Ativa a câmera temporariamente para a calibração de 2 pontos."""
        with self._lock:
            self._calibration_mode = active
            if active:
                self._sample_buffer.clear()
            self._wake_event.set()

    def get_median_sample(self) -> Optional[Tuple[float, float]]:
        """Retorna a mediana das últimas 5 leituras válidas no buffer circular."""
        with self._lock:
            if not self._sample_buffer:
                return self._latest_sample
            xs = [pt[0] for pt in self._sample_buffer]
            ys = [pt[1] for pt in self._sample_buffer]
            return (float(statistics.median(xs)), float(statistics.median(ys)))

    def stop(self) -> None:
        """Encerra a thread do rastreador e libera recursos."""
        with self._lock:
            self._running = False
            self._tracking_active = False
            self._calibration_mode = False
            self._wake_event.set()

    @staticmethod
    def extract_head_vector(landmarks: Sequence[Any]) -> Optional[Tuple[float, float]]:
        """Extrai o vetor normalizado (x, y) combinando rotação (yaw/pitch) e posição facial."""
        try:
            # Pontos chave do MediaPipe Face Mesh (468 pontos):
            # 1: Ponta do nariz
            # 10: Topo da testa | 152: Base do queixo
            # 234: Lateral esquerda do rosto | 454: Lateral direita do rosto
            nose_x, nose_y = float(landmarks[1].x), float(landmarks[1].y)
            forehead_y = float(landmarks[10].y)
            chin_y = float(landmarks[152].y)
            left_cheek_x = float(landmarks[234].x)
            right_cheek_x = float(landmarks[454].x)

            face_w = max(abs(right_cheek_x - left_cheek_x), 0.02)
            face_h = max(abs(chin_y - forehead_y), 0.02)

            rel_yaw = (nose_x - left_cheek_x) / face_w
            rel_pitch = (nose_y - forehead_y) / face_h

            # Combina inclinação angular da cabeça (65%) com posição no quadro (35%)
            combined_x = (0.65 * rel_yaw) + (0.35 * nose_x)
            combined_y = (0.65 * rel_pitch) + (0.35 * nose_y)
            return (combined_x, combined_y)
        except Exception:
            return None

    def _worker_loop(self) -> None:
        cap: Optional[cv2.VideoCapture] = None
        detector: Optional[_MediaPipeFaceDetector] = None

        try:
            detector = _MediaPipeFaceDetector()
        except Exception as exc:
            self.on_status_change_callback(
                False, False, f"Erro ao iniciar MediaPipe: {exc}"
            )
            return

        try:
            while True:
                with self._lock:
                    if not self._running:
                        break
                    should_capture = self._tracking_active or self._calibration_mode
                    current_fps = self._fps
                    tracking_now = self._tracking_active
                    cam_idx = self.camera_index
                    reopen_cam = self._reopen_camera_requested
                    if reopen_cam:
                        self._reopen_camera_requested = False

                if reopen_cam and cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass
                    cap = None

                if not should_capture:
                    if cap is not None:
                        try:
                            cap.release()
                        except Exception:
                            pass
                        cap = None
                    with self._lock:
                        self._camera_open = False
                        self._face_detected = False
                    self.on_status_change_callback(False, False, "Webcam: Liberada")
                    self._wake_event.clear()
                    self._wake_event.wait(timeout=0.5)
                    continue

                # Abre a webcam se ainda não estiver aberta
                if cap is None or not cap.isOpened():
                    self.on_status_change_callback(
                        tracking_now, False, f"Iniciando webcam (Câmera {cam_idx})..."
                    )
                    cap = cv2.VideoCapture(cam_idx, cv2.CAP_DSHOW)
                    if not cap.isOpened():
                        cap = cv2.VideoCapture(cam_idx)
                    if not cap.isOpened():
                        with self._lock:
                            self._camera_open = False
                            self._face_detected = False
                        self.on_status_change_callback(
                            tracking_now,
                            False,
                            f"Erro: Câmera {cam_idx} indisponível ou em uso",
                        )
                        time.sleep(1.0)
                        continue

                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    with self._lock:
                        self._camera_open = True
                    self.on_status_change_callback(
                        tracking_now, True, f"Webcam {cam_idx}: Ativa (320x240)"
                    )

                cycle_start = time.perf_counter()
                ret, frame = cap.read()
                if not ret or frame is None:
                    time.sleep(0.1)
                    continue

                # Redimensionamento explícito para 320x240 (RNF-03) e espelhamento natural
                if frame.shape[1] != 320 or frame.shape[0] != 240:
                    frame = cv2.resize(
                        frame, (320, 240), interpolation=cv2.INTER_NEAREST
                    )
                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                landmarks = detector.detect_landmarks(rgb)

                if landmarks:
                    vec = self.extract_head_vector(landmarks)
                    if vec is not None:
                        with self._lock:
                            self._sample_buffer.append(vec)
                            self._latest_sample = vec
                            self._face_detected = True
                            is_trk = self._tracking_active

                        if is_trk:
                            self.on_sample_callback(vec)
                else:
                    with self._lock:
                        self._face_detected = False

                with self._lock:
                    cal_mode = self._calibration_mode
                effective_fps = max(current_fps, 10) if cal_mode else current_fps
                target_interval = 1.0 / float(effective_fps)
                elapsed = time.perf_counter() - cycle_start
                sleep_time = max(0.005, target_interval - elapsed)
                time.sleep(sleep_time)
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass
            if detector is not None:
                detector.close()
