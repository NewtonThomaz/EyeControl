"""Interface gráfica principal do EyeControl em CustomTkinter (Thread-Safe e Configurável)."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import customtkinter as ctk

from src.calibration_overlay import CalibrationOverlay
from src.config import MONITOR_LAYOUTS, OFFSET_DIRECTIONS, ConfigManager
from src.coordinate_mapper import CoordinateMapper
from src.hotkey_manager import HotkeyManager, format_hotkey_display
from src.tracker import FaceTracker
from src.window_manager import WindowInfo, WindowManager

CAMERA_OPTIONS = ["Câmera 0", "Câmera 1", "Câmera 2", "Câmera 3"]


class EyeControlApp(ctk.CTk):
    """Janela principal do EyeControl com gerenciamento thread-safe de eventos."""

    def __init__(self, config: ConfigManager) -> None:
        super().__init__()
        self.config_mgr = config
        self.mapper = CoordinateMapper()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("EyeControl — Rastreamento e Sobreposição Multimonitor")
        self.geometry("580x700")
        self.minsize(540, 640)

        self._windows_map: Dict[str, WindowInfo] = {}
        self._selected_hwnd: Optional[int] = None
        self._active_overlay: Optional[CalibrationOverlay] = None
        self._primary_mon, self._secondary_mon = WindowManager.get_monitors()

        self._build_ui()

        # Inicializa motor de rastreamento (worker thread)
        self.tracker = FaceTracker(
            on_sample_callback=self._on_tracker_sample_threadsafe,
            on_status_change_callback=self._on_tracker_status_threadsafe,
            camera_index=int(self.config_mgr.get("camera_index", 0)),
            fps=int(self.config_mgr.get("fps", 5)),
        )

        # Inicializa gerenciador de atalhos globais (worker thread)
        self.hotkey_mgr = HotkeyManager(
            hotkey_str=str(self.config_mgr.get("hotkey", "ctrl+f9")),
            on_toggle_callback=self._on_hotkey_toggle_threadsafe,
            on_recorded_callback=self._on_hotkey_recorded_threadsafe,
        )

        self.refresh_windows_list()
        self._update_calibration_badge()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # Construção da Interface Gráfica
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        main_container = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
        main_container.grid(row=0, column=0, sticky="nsew", padx=14, pady=(10, 6))
        main_container.grid_columnconfigure(0, weight=1)

        # Cabeçalho
        header_frame = ctk.CTkFrame(main_container, corner_radius=10)
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header_frame.grid_columnconfigure(0, weight=1)

        title_lbl = ctk.CTkLabel(
            header_frame,
            text="EyeControl",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        title_lbl.grid(row=0, column=0, sticky="w", padx=14, pady=(10, 2))

        mon_text = (
            f"Mon 1 (Principal): {self._primary_mon.width}×{self._primary_mon.height}  |  "
            f"Mon 2: {self._secondary_mon.width}×{self._secondary_mon.height}"
        )
        self.monitors_lbl = ctk.CTkLabel(
            header_frame,
            text=mon_text,
            font=ctk.CTkFont(size=12),
            text_color="#94A3B8",
        )
        self.monitors_lbl.grid(row=1, column=0, sticky="w", padx=14, pady=(0, 10))

        self.toggle_btn = ctk.CTkButton(
            header_frame,
            text="▶ INICIAR RASTREAMENTO",
            fg_color="#10B981",
            hover_color="#059669",
            text_color="#06281E",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=36,
            command=self._toggle_tracking_ui,
        )
        self.toggle_btn.grid(row=0, column=1, rowspan=2, padx=14, pady=10)

        # 1. Seção Janela Alvo (RF-01, RF-02)
        target_frame = ctk.CTkFrame(main_container, corner_radius=10)
        target_frame.grid(row=1, column=0, sticky="ew", pady=6)
        target_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            target_frame,
            text="1. Janela Alvo (scrcpy, PiP, Player)",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(10, 6))

        self.window_dropdown = ctk.CTkOptionMenu(
            target_frame,
            values=["Nenhuma janela selecionada"],
            command=self._on_window_selected,
            dynamic_resizing=False,
        )
        self.window_dropdown.grid(row=1, column=0, sticky="ew", padx=(14, 8), pady=(0, 12))

        self.refresh_btn = ctk.CTkButton(
            target_frame,
            text="↻ Atualizar",
            width=105,
            command=self.refresh_windows_list,
        )
        self.refresh_btn.grid(row=1, column=1, padx=(0, 14), pady=(0, 12))

        # 2. Seção Disposição Física dos Monitores
        layout_frame = ctk.CTkFrame(main_container, corner_radius=10)
        layout_frame.grid(row=2, column=0, sticky="ew", pady=6)
        layout_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            layout_frame,
            text="2. Disposição Física do Monitor Secundário (2)",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(10, 2))

        ctk.CTkLabel(
            layout_frame,
            text="Como o Monitor 2 está posicionado na sua mesa em relação ao Monitor 1:",
            font=ctk.CTkFont(size=12),
            text_color="#94A3B8",
        ).grid(row=1, column=0, sticky="w", padx=14, pady=(0, 6))

        current_layout = str(self.config_mgr.get("monitor_layout", "Vertical: Secundário Acima"))
        self.layout_dropdown = ctk.CTkOptionMenu(
            layout_frame,
            values=MONITOR_LAYOUTS,
            command=self._on_layout_changed,
            dynamic_resizing=False,
        )
        self.layout_dropdown.set(current_layout)
        self.layout_dropdown.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 12))

        # 3. Seção Calibração de 2 Pontos (RF-04 a RF-07)
        cal_frame = ctk.CTkFrame(main_container, corner_radius=10)
        cal_frame.grid(row=3, column=0, sticky="ew", pady=6)
        cal_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            cal_frame,
            text="3. Calibração de 2 Pontos (Cruz + Barra de Espaço)",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(10, 2))

        self.cal_status_lbl = ctk.CTkLabel(
            cal_frame,
            text="Status: Verificando...",
            font=ctk.CTkFont(size=12),
            text_color="#FBBF24",
        )
        self.cal_status_lbl.grid(row=1, column=0, sticky="w", padx=14, pady=(0, 8))

        self.calibrate_btn = ctk.CTkButton(
            cal_frame,
            text="🎯 Iniciar Calibração de 2 Pontos",
            height=34,
            command=self._start_calibration,
        )
        self.calibrate_btn.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 12))

        # 4. Seção Câmera e Desempenho (RNF-02)
        perf_frame = ctk.CTkFrame(main_container, corner_radius=10)
        perf_frame.grid(row=4, column=0, sticky="ew", pady=6)
        perf_frame.grid_columnconfigure(0, weight=1)
        perf_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            perf_frame,
            text="4. Câmera e Desempenho",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(10, 6))

        # Seletor de Câmera
        cam_idx = int(self.config_mgr.get("camera_index", 0))
        cam_label = f"Câmera {cam_idx}" if 0 <= cam_idx < len(CAMERA_OPTIONS) else CAMERA_OPTIONS[0]
        ctk.CTkLabel(
            perf_frame,
            text="Dispositivo de Webcam:",
            font=ctk.CTkFont(size=12),
            text_color="#CBD5E1",
        ).grid(row=1, column=0, sticky="w", padx=14, pady=(0, 2))

        self.cam_dropdown = ctk.CTkOptionMenu(
            perf_frame,
            values=CAMERA_OPTIONS,
            command=self._on_camera_changed,
            dynamic_resizing=False,
            width=140,
        )
        self.cam_dropdown.set(cam_label)
        self.cam_dropdown.grid(row=2, column=0, sticky="w", padx=14, pady=(0, 10))

        # Slider de FPS
        initial_fps = int(self.config_mgr.get("fps", 5))
        self.fps_lbl = ctk.CTkLabel(
            perf_frame,
            text=f"Amostragem: {initial_fps} FPS ({int(1000 / initial_fps)} ms)",
            font=ctk.CTkFont(size=12),
        )
        self.fps_lbl.grid(row=3, column=0, columnspan=2, sticky="w", padx=14, pady=(4, 2))

        self.fps_slider = ctk.CTkSlider(
            perf_frame,
            from_=1,
            to=15,
            number_of_steps=14,
            command=self._on_fps_changed,
        )
        self.fps_slider.set(initial_fps)
        self.fps_slider.grid(row=4, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 12))

        # 5. Seção Deslocamento Periférico (Offset) e Zona Morta (RF-09 a RF-12)
        offset_frame = ctk.CTkFrame(main_container, corner_radius=10)
        offset_frame.grid(row=5, column=0, sticky="ew", pady=6)
        offset_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            offset_frame,
            text="5. Deslocamento Periférico (Offset) e Zona Morta",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(10, 6))

        ctk.CTkLabel(
            offset_frame,
            text="Direção do Offset:",
            font=ctk.CTkFont(size=12),
            text_color="#CBD5E1",
        ).grid(row=1, column=0, sticky="w", padx=14, pady=(0, 4))

        initial_dir = str(self.config_mgr.get("offset_direction", "Direita"))
        self.direction_seg = ctk.CTkSegmentedButton(
            offset_frame,
            values=OFFSET_DIRECTIONS,
            command=self._on_direction_changed,
        )
        self.direction_seg.set(initial_dir)
        self.direction_seg.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 10))

        initial_dist = int(self.config_mgr.get("offset_distance", 200))
        self.dist_lbl = ctk.CTkLabel(
            offset_frame,
            text=f"Distância do Offset: {initial_dist} px",
            font=ctk.CTkFont(size=12),
        )
        self.dist_lbl.grid(row=3, column=0, sticky="w", padx=14, pady=(0, 2))

        self.dist_slider = ctk.CTkSlider(
            offset_frame,
            from_=50,
            to=600,
            number_of_steps=110,
            command=self._on_distance_changed,
        )
        self.dist_slider.set(initial_dist)
        self.dist_slider.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 10))

        initial_dz = int(self.config_mgr.get("deadzone", 40))
        self.dz_lbl = ctk.CTkLabel(
            offset_frame,
            text=f"Zona Morta (Deadzone anti-tremor): {initial_dz} px",
            font=ctk.CTkFont(size=12),
        )
        self.dz_lbl.grid(row=5, column=0, sticky="w", padx=14, pady=(0, 2))

        self.dz_slider = ctk.CTkSlider(
            offset_frame,
            from_=10,
            to=150,
            number_of_steps=140,
            command=self._on_deadzone_changed,
        )
        self.dz_slider.set(initial_dz)
        self.dz_slider.grid(row=6, column=0, sticky="ew", padx=14, pady=(0, 12))

        # 6. Seção de Atalho Global (RF-13, RF-14)
        hk_frame = ctk.CTkFrame(main_container, corner_radius=10)
        hk_frame.grid(row=6, column=0, sticky="ew", pady=6)
        hk_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            hk_frame,
            text="6. Atalho Global de Alternância (Toggle ON/OFF)",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(10, 6))

        hk_display = format_hotkey_display(str(self.config_mgr.get("hotkey", "ctrl+f9")))
        self.hotkey_entry_lbl = ctk.CTkLabel(
            hk_frame,
            text=f"Atalho Atual:  {hk_display}",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#1E293B",
            corner_radius=6,
            height=34,
        )
        self.hotkey_entry_lbl.grid(row=1, column=0, sticky="ew", padx=(14, 8), pady=(0, 12))

        self.record_hk_btn = ctk.CTkButton(
            hk_frame,
            text="⌨ Alterar Atalho",
            width=130,
            height=34,
            command=self._start_hotkey_recording,
        )
        self.record_hk_btn.grid(row=1, column=1, padx=(0, 14), pady=(0, 12))

        # 7. Barra de Status no Rodapé
        footer = ctk.CTkFrame(self, height=40, corner_radius=0, fg_color="#0F172A")
        footer.grid(row=1, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        footer.grid_columnconfigure(1, weight=1)

        self.tracking_status_lbl = ctk.CTkLabel(
            footer,
            text="● Rastreamento: DESATIVADO",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#94A3B8",
        )
        self.tracking_status_lbl.grid(row=0, column=0, sticky="w", padx=16, pady=8)

        self.camera_status_lbl = ctk.CTkLabel(
            footer,
            text="Webcam: Liberada",
            font=ctk.CTkFont(size=12),
            text_color="#38BDF8",
        )
        self.camera_status_lbl.grid(row=0, column=1, sticky="e", padx=16, pady=8)

    # ------------------------------------------------------------------
    # Eventos da UI (Main Thread)
    # ------------------------------------------------------------------
    def refresh_windows_list(self) -> None:
        """Atualiza a listagem de janelas abertas e os retângulos dos monitores."""
        self._primary_mon, self._secondary_mon = WindowManager.get_monitors()
        mon_text = (
            f"Mon 1 (Principal): {self._primary_mon.width}×{self._primary_mon.height}  |  "
            f"Mon 2: {self._secondary_mon.width}×{self._secondary_mon.height}"
        )
        self.monitors_lbl.configure(text=mon_text)

        windows: List[WindowInfo] = WindowManager.list_visible_windows()
        self._windows_map = {w.label: w for w in windows}

        if not windows:
            self.window_dropdown.configure(values=["Nenhuma janela visível encontrada"])
            self.window_dropdown.set("Nenhuma janela visível encontrada")
            self._selected_hwnd = None
            return

        labels = list(self._windows_map.keys())
        self.window_dropdown.configure(values=labels)

        saved_title = str(self.config_mgr.get("target_window_title", "")).lower()
        chosen_label = labels[0]

        for lbl, winfo in self._windows_map.items():
            t_low = winfo.title.lower()
            if self._selected_hwnd and winfo.hwnd == self._selected_hwnd:
                chosen_label = lbl
                break
            if saved_title and saved_title in t_low:
                chosen_label = lbl
                break
            if any(k in t_low for k in ("scrcpy", "sm-", "picture-in-picture", "pip")):
                chosen_label = lbl

        self.window_dropdown.set(chosen_label)
        self._on_window_selected(chosen_label)

    def _on_window_selected(self, label: str) -> None:
        winfo = self._windows_map.get(label)
        if winfo:
            self._selected_hwnd = winfo.hwnd
            self.config_mgr.set("target_window_title", winfo.title)
            self.mapper.reset_state()

    def _on_layout_changed(self, layout: str) -> None:
        self.config_mgr.set("monitor_layout", layout)
        self.mapper.reset_state()
        self._update_calibration_badge()

    def _on_camera_changed(self, cam_label: str) -> None:
        try:
            idx = int(cam_label.split()[-1])
        except Exception:
            idx = 0
        self.config_mgr.set("camera_index", idx)
        self.tracker.set_camera_index(idx)

    def _on_fps_changed(self, value: float) -> None:
        fps = max(1, min(15, int(round(value))))
        self.fps_lbl.configure(
            text=f"Amostragem: {fps} FPS ({int(1000 / fps)} ms)"
        )
        self.tracker.set_fps(fps)
        self.config_mgr.set("fps", fps)

    def _on_direction_changed(self, direction: str) -> None:
        self.config_mgr.set("offset_direction", direction)
        self.mapper.reset_state()

    def _on_distance_changed(self, value: float) -> None:
        dist = int(round(value))
        self.dist_lbl.configure(text=f"Distância do Offset: {dist} px")
        self.config_mgr.set("offset_distance", dist)

    def _on_deadzone_changed(self, value: float) -> None:
        dz = int(round(value))
        self.dz_lbl.configure(text=f"Zona Morta (Deadzone anti-tremor): {dz} px")
        self.config_mgr.set("deadzone", dz)

    def _start_hotkey_recording(self) -> None:
        self.hotkey_entry_lbl.configure(
            text="Pressione a nova combinação... (ESC cancela)",
            text_color="#FBBF24",
        )
        self.record_hk_btn.configure(state="disabled")
        self.hotkey_mgr.start_recording()

    def _start_calibration(self) -> None:
        if self._active_overlay is not None:
            return
        # Pausa o rastreamento de movimentação enquanto calibra os 2 pontos
        self.tracker.set_tracking(False)
        self._sync_toggle_visual(False)
        layout = str(self.config_mgr.get("monitor_layout", "Vertical: Secundário Acima"))
        self._active_overlay = CalibrationOverlay(
            parent=self,
            tracker=self.tracker,
            on_complete=self._on_calibration_completed,
            on_cancel=self._on_calibration_cancelled,
            monitor_layout=layout,
        )

    def _on_calibration_completed(
        self, primary_pt: Tuple[float, float], secondary_pt: Tuple[float, float]
    ) -> None:
        self._active_overlay = None
        self.config_mgr.set_calibration(primary_pt, secondary_pt)
        self.mapper.reset_state()
        self._update_calibration_badge()

    def _on_calibration_cancelled(self) -> None:
        self._active_overlay = None
        self._update_calibration_badge()

    def _update_calibration_badge(self) -> None:
        is_cal, p1, p2 = self.config_mgr.get_calibration()
        if is_cal:
            self.cal_status_lbl.configure(
                text=(
                    f"✓ Calibrado — P1: ({p1[0]:.3f}, {p1[1]:.3f})  |  "
                    f"P2: ({p2[0]:.3f}, {p2[1]:.3f})"
                ),
                text_color="#34D399",
            )
        else:
            self.cal_status_lbl.configure(
                text="⚠ Calibração pendente (Clique abaixo para calibrar com a cruz)",
                text_color="#FBBF24",
            )

    def _toggle_tracking_ui(self) -> None:
        if self._active_overlay is not None:
            return
        new_state = self.tracker.toggle_tracking()
        if new_state:
            self._primary_mon, self._secondary_mon = WindowManager.get_monitors()
        self._sync_toggle_visual(new_state)

    def _sync_toggle_visual(self, active: bool) -> None:
        if active:
            self.toggle_btn.configure(
                text="⏹ PAUSAR RASTREAMENTO",
                fg_color="#EF4444",
                hover_color="#DC2626",
                text_color="#FFFFFF",
            )
            self.tracking_status_lbl.configure(
                text="● Rastreamento: ATIVO",
                text_color="#34D399",
            )
        else:
            self.toggle_btn.configure(
                text="▶ INICIAR RASTREAMENTO",
                fg_color="#10B981",
                hover_color="#059669",
                text_color="#06281E",
            )
            self.tracking_status_lbl.configure(
                text="● Rastreamento: DESATIVADO (Posição Congelada)",
                text_color="#94A3B8",
            )

    # ------------------------------------------------------------------
    # Callbacks Thread-Safe (Despacho via self.after)
    # ------------------------------------------------------------------
    def _on_hotkey_toggle_threadsafe(self) -> None:
        self.after(0, self._toggle_tracking_ui)

    def _on_hotkey_recorded_threadsafe(self, new_hotkey: str) -> None:
        def _apply() -> None:
            self.config_mgr.set("hotkey", new_hotkey)
            hk_display = format_hotkey_display(new_hotkey)
            self.hotkey_entry_lbl.configure(
                text=f"Atalho Atual:  {hk_display}",
                text_color="#F8FAFC",
            )
            self.record_hk_btn.configure(state="normal")

        self.after(0, _apply)

    def _on_tracker_status_threadsafe(
        self, tracking_active: bool, _camera_open: bool, message: str
    ) -> None:
        def _apply() -> None:
            self.camera_status_lbl.configure(text=message)
            self._sync_toggle_visual(tracking_active)

        self.after(0, _apply)

    def _on_tracker_sample_threadsafe(self, sample: Tuple[float, float]) -> None:
        """Recebe leitura facial da worker thread e agenda processamento na Main Thread."""
        self.after(0, lambda: self._process_gaze_sample(sample))

    def _process_gaze_sample(self, sample: Tuple[float, float]) -> None:
        if not self.tracker.is_tracking:
            return
        hwnd = self._selected_hwnd
        if not WindowManager.is_valid_window(hwnd):
            return

        assert hwnd is not None
        _is_cal, primary_pt, secondary_pt = self.config_mgr.get_calibration()
        win_size = WindowManager.get_window_size(hwnd)
        offset_dir = str(self.config_mgr.get("offset_direction", "Direita"))
        offset_dist = int(self.config_mgr.get("offset_distance", 200))
        deadzone = int(self.config_mgr.get("deadzone", 40))
        layout = str(self.config_mgr.get("monitor_layout", "Vertical: Secundário Acima"))

        target_x, target_y, mon_idx, should_move = self.mapper.compute_position(
            raw_point=sample,
            primary_point=primary_pt,
            secondary_point=secondary_pt,
            primary_mon=self._primary_mon,
            secondary_mon=self._secondary_mon,
            window_size=win_size,
            offset_direction=offset_dir,
            offset_distance=offset_dist,
            deadzone=deadzone,
            monitor_layout=layout,
        )

        if should_move:
            moved = WindowManager.move_window(hwnd, target_x, target_y)
            if moved:
                self.camera_status_lbl.configure(
                    text=f"Webcam: Ativa  •  Mon {mon_idx} ({target_x}, {target_y})"
                )

    def _on_close(self) -> None:
        try:
            self.hotkey_mgr.stop()
        except Exception:
            pass
        try:
            self.tracker.stop()
        except Exception:
            pass
        self.destroy()
