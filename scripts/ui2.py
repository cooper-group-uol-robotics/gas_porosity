import sys
import os
import threading
import time
import signal
from datetime import datetime

from qtpy.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QSplitter,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QSlider,
    QLineEdit,
    QDoubleSpinBox,
    QSpinBox,
    QFileDialog,
    QDialog,
    QMessageBox,
    QGroupBox,
    QFrame,
    QSizePolicy,
    QButtonGroup,
    QStatusBar,
    QScrollArea,
)
from qtpy.QtCore import Qt, QTimer, Signal, QObject, QThread
from qtpy.QtGui import QImage, QPixmap, QFont, QColor

import pyqtgraph as pg
import cv2
import numpy as np

from gasporosity.data_controller import DataController
from scripts.calculate_porus_Yulin_ui_v2 import calculate_porus


class State:
    def __init__(self, state_dict):
        self.state = 0
        self.state_dict = state_dict

    def set_state(self, s):
        self.state = s

    def state_f(self):
        return self.state_dict[self.state]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def label(text, bold=False, size=14):
    lbl = QLabel(text)
    font = QFont("Segoe UI", size)
    font.setBold(bold)
    lbl.setFont(font)
    return lbl


def group(title):
    gb = QGroupBox(title)
    gb.setFont(QFont("Segoe UI", 10, QFont.Bold))
    lay = QVBoxLayout()
    gb.setLayout(lay)
    return gb, lay


def hline():
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setFrameShadow(QFrame.Sunken)
    return f


# ---------------------------------------------------------------------------
# Camera worker - runs capture in a QThread
# ---------------------------------------------------------------------------
class CameraWorker(QObject):
    frame_ready = Signal(np.ndarray)

    def __init__(self, controller):
        super().__init__()
        self._ctrl = controller
        self._running = False

    def start(self):
        self._running = True
        self._loop()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            frame = self._ctrl.get_frame()
            self.frame_ready.emit(frame)
            time.sleep(0.033)  # ~30 fps


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------
class GasPorosityWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gas Porosity")
        self.resize(1600, 900)

        self.controller = DataController()
        self.state = State(
            {
                0: self.controller.probe,
                1: self.controller.edit_corners,
                2: self.controller.edit_wells,
            }
        )

        self.dosing_done_waiting = False
        self.degas_start_time = None
        self._pressure_data = []  # rolling buffer for pressure plot
        self._cam_thread = None

        self._build_ui()
        self._connect_timers()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        # Root splitter  left | right
        root = QSplitter(Qt.Horizontal)
        root.setHandleWidth(6)
        root.addWidget(self._build_left_panel())
        root.addWidget(self._build_right_panel())
        root.setSizes([700, 900])
        self.setCentralWidget(root)

        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready")

        # Dark-ish stylesheet
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #1e1e2e; color: #cdd6f4; }
            QGroupBox {
                border: 1px solid #45475a;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 6px;
                color: #89b4fa;
                font-weight: bold;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; }
            QPushButton {
                background: #313244; border: 1px solid #585b70;
                border-radius: 4px; padding: 5px 12px; color: #cdd6f4;
            }
            QPushButton:hover  { background: #45475a; }
            QPushButton:pressed { background: #585b70; }
            QPushButton:disabled { color: #585b70; border-color: #313244; }
            QLabel { color: #cdd6f4; }
            QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {
                background: #313244; border: 1px solid #45475a;
                border-radius: 4px; padding: 3px 6px; color: #cdd6f4;
            }
            QSlider::groove:horizontal { background: #313244; height: 6px; border-radius: 3px; }
            QSlider::handle:horizontal {
                background: #89b4fa; width: 14px; height: 14px;
                margin: -4px 0; border-radius: 7px;
            }
            QSlider::sub-page:horizontal { background: #89b4fa; border-radius: 3px; }
            QSplitter::handle { background: #45475a; }
            QFrame[frameShape="4"] { color: #45475a; }   /* HLine */
        """)

    # ── LEFT PANEL ────────────────────────────────────────────────────────────

    def _build_left_panel(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 4, 8)
        layout.setSpacing(8)

        # ── Arduino Controls ─────────────────────────────────────────────────
        ard_gb, ard_lay = group("Arduino Controls")

        btn_row = QHBoxLayout()
        self.btn_start_arduino = QPushButton("Start Listening")
        self.btn_dose = QPushButton("Dose")
        self.btn_stop_arduino = QPushButton("Stop Listening")
        self.btn_dose.setEnabled(False)
        self.btn_stop_arduino.setEnabled(False)
        for b in (self.btn_start_arduino, self.btn_dose, self.btn_stop_arduino):
            btn_row.addWidget(b)

        cycle_row = QHBoxLayout()
        cycle_row.addWidget(QLabel("Dosing Cycles:"))
        self.number_of_cycles = QComboBox()
        self.number_of_cycles.addItems([str(i) for i in range(1, 11)])
        self.number_of_cycles.setCurrentIndex(6)  # default 7
        cycle_row.addWidget(self.number_of_cycles)
        self.btn_dose_stop = QPushButton("Stop Cycling")
        cycle_row.addWidget(self.btn_dose_stop)
        cycle_row.addWidget(QLabel("Current Cycle:"))
        self.lbl_cycle = QLabel("")
        cycle_row.addWidget(self.lbl_cycle)
        cycle_row.addStretch()

        # Pressure plot
        pg.setConfigOption("background", "#1e1e2e")
        pg.setConfigOption("foreground", "#cdd6f4")
        self.pressure_plot = pg.PlotWidget(title="Pressure")
        self.pressure_plot.setLabel("left", "Pressure")
        self.pressure_plot.setLabel("bottom", "Sample")
        self.pressure_plot.addLegend()
        self.pressure_curve = self.pressure_plot.plot(
            [], [], pen=pg.mkPen("#89b4fa", width=2), name="pressure"
        )
        self.pressure_plot.setMinimumHeight(180)

        ard_lay.addLayout(btn_row)
        ard_lay.addLayout(cycle_row)
        ard_lay.addWidget(self.pressure_plot)
        layout.addWidget(ard_gb)

        # ── Circulator Controls ──────────────────────────────────────────────
        circ_gb, circ_lay = group("Circulator Controls")
        circ_h = QHBoxLayout()

        # Left side: buttons + timer
        circ_left = QVBoxLayout()
        self.btn_degas = QPushButton("Degas")
        self.lbl_timer = QLabel("--:--:--")
        self.lbl_timer.setFont(QFont("Courier New", 14, QFont.Bold))
        self.btn_cancel = QPushButton("Cancel")
        circ_left.addWidget(self.btn_degas)
        circ_left.addWidget(QLabel("Degas Timer:"))
        circ_left.addWidget(self.lbl_timer)
        circ_left.addWidget(self.btn_cancel)
        circ_left.addStretch()

        # Right side: numeric inputs
        circ_right = QVBoxLayout()
        self.degas_heat_temp = self._spinbox(100, -200, 600, "Degas Heat Temp (°C)")
        self.degas_cool_temp = self._spinbox(-10, -200, 100, "Degas Cool Temp (°C)")
        self.degas_stab_temp = self._spinbox(20, -200, 600, "Degas Stabilise Temp (°C)")
        self.degas_heat_time = self._spinbox(480, 0, 9999, "Degas Heat Time (min)")
        self.degas_cool_time = self._spinbox(60, 0, 9999, "Degas Cool Time (min)")
        self.degas_stab_time = self._spinbox(60, 0, 9999, "Degas Stabilise Time (min)")
        for sb in (
            self.degas_heat_temp,
            self.degas_cool_temp,
            self.degas_stab_temp,
            self.degas_heat_time,
            self.degas_cool_time,
            self.degas_stab_time,
        ):
            circ_right.addWidget(sb)
        circ_right.addStretch()

        circ_h.addLayout(circ_left)
        circ_h.addLayout(circ_right)
        circ_lay.addLayout(circ_h)
        layout.addWidget(circ_gb)

        # ── File Config ──────────────────────────────────────────────────────
        file_gb, file_lay = group("File Config")
        file_grid = QHBoxLayout()

        fc_left = QVBoxLayout()
        fc_left.addWidget(QLabel("Temp File Name:"))
        self.temp_file_input = QLineEdit("Temperature")
        fc_left.addWidget(self.temp_file_input)
        fc_left.addWidget(QLabel("Pressure File Name:"))
        self.pres_file_input = QLineEdit("Pressure")
        fc_left.addWidget(self.pres_file_input)
        fc_left.addStretch()

        file_grid.addLayout(fc_left)
        file_lay.addLayout(file_grid)
        layout.addWidget(file_gb)

        # ── Data Analysis ────────────────────────────────────────────────────
        layout.addWidget(hline())
        layout.addWidget(label("Data Analysis (beta)", bold=True, size=13))
        layout.addWidget(
            label(
                "Produces a temperature graph and exports peak areas/heights to CSV.",
                size=10,
            )
        )
        layout.addWidget(label("Only works with standard dosing procedure.", size=10))

        da_row = QHBoxLayout()
        self.threshold = QDoubleSpinBox()
        self.threshold.setValue(0.1)
        self.threshold.setDecimals(3)
        self.threshold.setPrefix("Threshold: ")
        da_row.addWidget(self.threshold)

        self.normalize_well_input = QLineEdit("1A")
        self.normalize_well_input.setPlaceholderText("Normalize Well")
        da_row.addWidget(self.normalize_well_input)

        self.lbl_file_to_run = QLabel("No file selected")
        self.lbl_file_to_run.setWordWrap(True)
        da_row.addWidget(self.lbl_file_to_run)

        self.btn_pick_file = QPushButton("Choose File")
        self.btn_run_script = QPushButton("Run Analysis")
        da_row.addWidget(self.btn_pick_file)
        da_row.addWidget(self.btn_run_script)
        layout.addLayout(da_row)

        layout.addStretch()
        return w

    # ── RIGHT PANEL ───────────────────────────────────────────────────────────

    def _build_right_panel(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 8, 8, 8)
        layout.setSpacing(8)

        layout.addWidget(label("Camera Controls", bold=True, size=14))

        # Camera buttons
        cam_row = QHBoxLayout()
        self.btn_start_camera = QPushButton("Start Camera")
        self.btn_corners = QPushButton("Edit Corners")
        self.btn_wells = QPushButton("Edit Wells")
        self.btn_probe = QPushButton("Probe")
        self.btn_focus = QPushButton("Focus")
        self.btn_save = QPushButton("Save Image")
        for btn in (
            self.btn_corners,
            self.btn_wells,
            self.btn_probe,
            self.btn_focus,
            self.btn_save,
        ):
            btn.setEnabled(False)
        for btn in (
            self.btn_start_camera,
            self.btn_corners,
            self.btn_wells,
            self.btn_probe,
            self.btn_focus,
            self.btn_save,
        ):
            cam_row.addWidget(btn)
        cam_row.addStretch()
        layout.addLayout(cam_row)

        # Data capture buttons
        data_row = QHBoxLayout()
        self.btn_start_data = QPushButton("Start Data Capture")
        self.btn_stop_data = QPushButton("Stop Data Capture")
        self.btn_start_data.setEnabled(False)
        self.btn_stop_data.setEnabled(False)
        self.video_save_toggle = QPushButton("Video Save: OFF")
        self.video_save_toggle.setCheckable(True)
        self.video_save_toggle.setEnabled(False)
        for btn in (self.btn_start_data, self.btn_stop_data, self.video_save_toggle):
            data_row.addWidget(btn)
        data_row.addStretch()
        layout.addLayout(data_row)

        # Well size slider
        ws_row = QHBoxLayout()
        ws_row.addWidget(QLabel("Well Size:"))
        self.slider_well = QSlider(Qt.Horizontal)
        self.slider_well.setRange(0, 200)
        self.slider_well.setValue(100)  # 10.0 * 10
        self.lbl_well_val = QLabel("10.0")
        ws_row.addWidget(self.slider_well)
        ws_row.addWidget(self.lbl_well_val)
        layout.addLayout(ws_row)

        # Camera view
        self.camera_label = QLabel()
        self.camera_label.setAlignment(Qt.AlignCenter)
        self.camera_label.setMinimumSize(640, 480)
        self.camera_label.setStyleSheet("background: #000; border: 1px solid #45475a;")
        self.camera_label.mousePressEvent = self._camera_mouse_press
        layout.addWidget(self.camera_label, stretch=1)

        # Well count sliders
        well_row = QHBoxLayout()
        well_row.addWidget(QLabel("X Wells:"))
        self.slider_x_wells = QSlider(Qt.Horizontal)
        self.slider_x_wells.setRange(4, 12)
        self.slider_x_wells.setValue(12)
        self.lbl_x_wells = QLabel("12")
        well_row.addWidget(self.slider_x_wells)
        well_row.addWidget(self.lbl_x_wells)

        well_row.addSpacing(20)
        well_row.addWidget(QLabel("Y Wells:"))
        self.slider_y_wells = QSlider(Qt.Horizontal)
        self.slider_y_wells.setRange(4, 8)
        self.slider_y_wells.setValue(8)
        self.lbl_y_wells = QLabel("8")
        well_row.addWidget(self.slider_y_wells)
        well_row.addWidget(self.lbl_y_wells)
        layout.addLayout(well_row)

        return w

    # ── Spinbox helper ────────────────────────────────────────────────────────

    def _spinbox(self, value, lo, hi, tip):
        sb = QDoubleSpinBox()
        sb.setRange(lo, hi)
        sb.setValue(value)
        sb.setToolTip(tip)
        sb.setPrefix(tip.split("(")[0].strip() + ": ")
        return sb

    # ── Timers ────────────────────────────────────────────────────────────────

    def _connect_timers(self):
        # Camera update (~30 fps) — driven by CameraWorker thread
        self._cam_timer = QTimer(self)
        self._cam_timer.setInterval(33)
        # Not started until camera is on

        # Degas countdown (1 s)
        self._degas_timer = QTimer(self)
        self._degas_timer.setInterval(1000)
        self._degas_timer.timeout.connect(self._degas_timer_tick)

        # Cycle updater (5 s)
        self._cycle_timer = QTimer(self)
        self._cycle_timer.setInterval(5000)
        self._cycle_timer.timeout.connect(self._update_cycle)

        # Auto-stop poll (500 ms)
        self._auto_stop_timer = QTimer(self)
        self._auto_stop_timer.setInterval(500)
        self._auto_stop_timer.timeout.connect(self._check_done)

        # Writer (1 s)
        self._writer_timer = QTimer(self)
        self._writer_timer.setInterval(1000)
        self._writer_timer.timeout.connect(self._write_data)

        self._connect_signals()

    def _connect_signals(self):
        # Arduino
        self.btn_start_arduino.clicked.connect(self._arduino_on)
        self.btn_stop_arduino.clicked.connect(self._arduino_off)
        self.btn_dose.clicked.connect(self._dose)
        self.btn_dose_stop.clicked.connect(self._dose_stop)

        # Circulator
        self.btn_degas.clicked.connect(self._degas)
        self.btn_cancel.clicked.connect(self._degas_cancel)

        # Camera
        self.btn_start_camera.clicked.connect(self._start_camera)
        self.btn_corners.clicked.connect(lambda: self.state.set_state(1))
        self.btn_wells.clicked.connect(lambda: self.state.set_state(2))
        self.btn_probe.clicked.connect(lambda: self.state.set_state(0))
        self.btn_focus.clicked.connect(self.controller.focus)
        self.btn_save.clicked.connect(self._save_image_dialog)

        # Data capture
        self.btn_start_data.clicked.connect(self._start_data_capture)
        self.btn_stop_data.clicked.connect(self._stop_data_capture)
        self.video_save_toggle.toggled.connect(self._toggle_video_save)

        # Sliders
        self.slider_well.valueChanged.connect(
            lambda v: self.lbl_well_val.setText(f"{v / 10:.1f}")
        )
        self.slider_x_wells.valueChanged.connect(
            lambda v: (
                self.lbl_x_wells.setText(str(v)),
                self.controller.set_well_count(x=v),
            )
        )
        self.slider_y_wells.valueChanged.connect(
            lambda v: (
                self.lbl_y_wells.setText(str(v)),
                self.controller.set_well_count(y=v),
            )
        )

        # Analysis
        self.btn_pick_file.clicked.connect(self._pick_file)
        self.btn_run_script.clicked.connect(self._run_analysis)

    # ── Arduino ───────────────────────────────────────────────────────────────

    def _arduino_on(self):
        try:
            fname = f"data/{self.pres_file_input.text()}.csv"
            self.controller.start_reading_arduino(self._append_pressure, fname)
            self.btn_start_arduino.setEnabled(False)
            self.btn_stop_arduino.setEnabled(True)
            self.btn_dose.setEnabled(True)
        except Exception as e:
            self._notify(str(e))

    def _arduino_off(self):
        try:
            self.controller.stop_reading()
            self.btn_start_arduino.setEnabled(True)
            self.btn_stop_arduino.setEnabled(False)
            self.btn_dose.setEnabled(False)
        except Exception as e:
            self._notify(str(e))

    def _append_pressure(self, value):
        """Called by arduino reader thread with new pressure value."""
        self._pressure_data.append(value)
        if len(self._pressure_data) > 5000:
            self._pressure_data = self._pressure_data[-5000:]
        self.pressure_curve.setData(self._pressure_data)

    # ── Dose ──────────────────────────────────────────────────────────────────

    def _dose(self):
        cycles = int(self.number_of_cycles.currentText())
        self.controller.dose(cycles)
        self._cycle_timer.start()
        self._auto_stop_timer.start()

    def _dose_stop(self):
        self.controller.stop_dose()
        self.lbl_cycle.setText("")
        self._cycle_timer.stop()

    def _update_cycle(self):
        self.lbl_cycle.setText(self.controller.read_cycle())

    def _check_done(self):
        if not self.controller.dose_thread.is_alive():
            if not self.dosing_done_waiting:
                self.dosing_done_waiting = True
                return
            self.lbl_cycle.setText("Dosing Complete")
            self._stop_data_capture()
            self._arduino_off()
            self._auto_stop_timer.stop()
            self.dosing_done_waiting = False

    # ── Degas ─────────────────────────────────────────────────────────────────

    def _degas(self):
        heat = self.degas_heat_temp.value()
        cool = self.degas_cool_temp.value()
        stab = self.degas_stab_temp.value()
        heat_t = int(self.degas_heat_time.value() * 12)
        cool_t = int(self.degas_cool_time.value() * 12)
        stab_t = int(self.degas_stab_time.value() * 12)

        t = threading.Thread(
            target=self.controller.degas,
            args=[heat, cool, stab, heat_t, cool_t, stab_t],
            daemon=True,
        )
        t.start()
        time.sleep(1)
        if t.is_alive():
            self.degas_start_time = datetime.now()
            self._degas_timer.start()
        else:
            self._notify("Degas failed - see console.")

    def _degas_cancel(self):
        self.degas_start_time = None
        self.lbl_timer.setText("Cancelled")
        self._degas_timer.stop()
        self.controller.cancel_degas()

    def _degas_timer_tick(self):
        if self.degas_start_time is None:
            return
        diff = datetime.now() - self.degas_start_time
        self.lbl_timer.setText(str(diff).split(".")[0])
        if self.controller.degas_done:
            self.lbl_timer.setText(f"Done - {str(diff).split('.')[0]}")
            self._degas_timer.stop()
            self.controller.degas_done = False
            self.degas_start_time = None

    # ── Camera ────────────────────────────────────────────────────────────────

    def _start_camera(self):
        try:
            self.controller.start_camera()
            self.btn_start_camera.setEnabled(False)
            for b in (
                self.btn_corners,
                self.btn_wells,
                self.btn_probe,
                self.btn_focus,
                self.btn_save,
            ):
                b.setEnabled(True)

            # Start camera worker thread
            self._cam_worker_thread = QThread()
            self._cam_worker = CameraWorker(self.controller)
            self._cam_worker.moveToThread(self._cam_worker_thread)
            self._cam_worker.frame_ready.connect(self._update_camera_frame)
            self._cam_worker_thread.started.connect(self._cam_worker.start)
            self._cam_worker_thread.start()
        except Exception as e:
            self._notify(str(e))

    def _update_camera_frame(self, frame):
        """Receive RGB frame from worker, paint on QLabel with overlay."""
        # Draw well circles overlay
        frame = frame.copy()
        LETTERS = "ABCDEFGH"
        radius = int(self.slider_well.value() / 10)
        for i, row in enumerate(self.controller.coords):
            for j, (cx, cy) in enumerate(row):
                cv2.circle(frame, (int(cx), int(cy)), radius, (135, 206, 235), 2)
                cv2.putText(
                    frame,
                    f"{i + 1}{LETTERS[j]}",
                    (int(cx) + radius, int(cy) + radius),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.35,
                    (255, 255, 255),
                    1,
                )
        for corner in self.controller.corners:
            cv2.circle(frame, (int(corner[0]), int(corner[1])), radius, (0, 200, 0), 2)

        h, w, ch = frame.shape
        qt_img = QImage(frame.data, w, h, ch * w, QImage.Format_RGB888)
        pix = QPixmap.fromImage(qt_img).scaled(
            self.camera_label.width(),
            self.camera_label.height(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.camera_label.setPixmap(pix)

    def _camera_mouse_press(self, event):
        """Map click on QLabel back to image coordinates and call state function."""
        lbl = self.camera_label
        pix = lbl.pixmap()
        if pix is None:
            return
        # Compute image rect inside label (centred, aspect-kept)
        lw, lh = lbl.width(), lbl.height()
        pw, ph = pix.width(), pix.height()
        ox = (lw - pw) // 2
        oy = (lh - ph) // 2
        ix = event.x() - ox
        iy = event.y() - oy
        if 0 <= ix < pw and 0 <= iy < ph:
            # Scale back to original frame coords
            orig_w = self.controller.get_frame().shape[1]
            orig_h = self.controller.get_frame().shape[0]
            fx = ix * orig_w / pw
            fy = iy * orig_h / ph
            fn = self.state.state_f()
            ret = fn(fx, fy)
            if ret:
                self._notify(ret)
            if len(self.controller.coords) > 0:
                self.btn_start_data.setEnabled(True)
                self.video_save_toggle.setEnabled(True)

    # ── Data capture ─────────────────────────────────────────────────────────

    def _start_data_capture(self):
        self.btn_start_data.setEnabled(False)
        self.controller.radius = self.slider_well.value() / 10
        self._notify("Calculating mask, please wait…")
        t = threading.Thread(target=self._calculate_mask, daemon=True)
        t.start()

    def _calculate_mask(self):
        self.controller.calculate_mask()
        fname = f"data/{self.temp_file_input.text()}.csv"
        self.controller.create_file(fname)
        # Re-enable stop button from main thread
        QTimer.singleShot(
            0, lambda: (self.btn_stop_data.setEnabled(True), self._writer_timer.start())
        )

    def _stop_data_capture(self):
        self.btn_start_data.setEnabled(True)
        self.btn_stop_data.setEnabled(False)
        self._writer_timer.stop()

    def _write_data(self):
        fname = f"data/{self.temp_file_input.text()}.csv"
        self.controller.write(fname, datetime.now().time())

    def _toggle_video_save(self, checked):
        val = "On" if checked else "Off"
        self.video_save_toggle.setText(f"Video Save: {val}")
        self.controller.set_save_video(val)

    # ── Save image dialog ─────────────────────────────────────────────────────

    def _save_image_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Save Image")
        dlg.setStyleSheet(self.styleSheet())
        lay = QVBoxLayout(dlg)
        inp = QLineEdit("CameraCapture")
        lay.addWidget(QLabel("File Name:"))
        lay.addWidget(inp)
        btn = QPushButton("Save")
        lay.addWidget(btn)
        btn.clicked.connect(
            lambda: (
                self.controller.save_image(inp.text()),
                self._notify("Saved"),
                dlg.accept(),
            )
        )
        dlg.exec_()

    # ── File analysis ─────────────────────────────────────────────────────────

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose File", os.getcwd())
        if path:
            self.lbl_file_to_run.setText(path)

    def _run_analysis(self):
        path = self.lbl_file_to_run.text()
        if path == "No file selected":
            self._notify("Please choose a file first.")
            return
        calculate_porus(path, self.threshold.value(), self.normalize_well_input.text())
        self._notify(f"Analysis files created at: {os.getcwd()}")

    # ── Utilities ─────────────────────────────────────────────────────────────

    def _notify(self, msg):
        self.status.showMessage(msg, 5000)

    def closeEvent(self, event):
        # Stop all timers
        for t in (
            self._degas_timer,
            self._cycle_timer,
            self._auto_stop_timer,
            self._writer_timer,
        ):
            t.stop()
        # Stop camera worker
        if self._cam_worker_thread and self._cam_worker_thread.isRunning():
            self._cam_worker.stop()
            self._cam_worker_thread.quit()
            self._cam_worker_thread.wait(2000)
        self.controller.cleanup()
        event.accept()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Gas Porosity")
    app.setStyle("Fusion")

    win = GasPorosityWindow()
    win.show()

    # Ctrl-C in terminal
    signal.signal(signal.SIGINT, lambda *_: app.quit())

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
