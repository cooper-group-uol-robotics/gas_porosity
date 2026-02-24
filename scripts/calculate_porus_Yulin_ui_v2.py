from __future__ import annotations

import os
import re
import sys
from typing import Dict, List

import numpy as np
import pandas as pd
from scipy import integrate, signal

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

try:
    import plotly.express as px
    import plotly.graph_objects as go

    HAS_PLOTLY = True
except Exception:
    HAS_PLOTLY = False

FIRST_PEAK_MIN_TIME_S = 0.0
FIRST_PEAK_MAX_TIME_S = 300.0
PEAK_WINDOW_STEP_S = 380.0


def parse_well_name(name: str):
    m = re.match(r"^([A-Za-z])\s*(\d+)$", str(name))
    if m:
        return m.group(1).upper(), int(m.group(2))
    m = re.match(r"^(\d+)\s*([A-Za-z])$", str(name))
    if m:
        return m.group(2).upper(), int(m.group(1))
    return None, None


def find_right_min_at_oscillation(
    y,
    peak_idx,
    end_idx,
    min_offset=5,
    osc_window=12,
    min_turns=3,
    min_rise_points=15,
):
    start_idx = min(end_idx, peak_idx + min_offset)
    max_idx = end_idx - osc_window
    if start_idx >= end_idx or max_idx <= start_idx:
        return peak_idx + int(np.argmin(y[peak_idx : end_idx + 1]))

    for idx in range(start_idx + 1, max_idx):
        is_local_min = y[idx] <= y[idx - 1] and y[idx] <= y[idx + 1]
        if not is_local_min:
            continue
        if idx + min_rise_points >= len(y):
            continue
        if not np.all(y[idx + 1 : idx + 1 + min_rise_points] > y[idx]):
            continue

        d = np.diff(y[idx : idx + osc_window + 1])
        d = d[np.abs(d) > 1e-9]
        if len(d) < 2:
            continue
        turns = int(np.sum(d[:-1] * d[1:] < 0))
        if turns >= min_turns:
            return idx

    return peak_idx + int(np.argmin(y[peak_idx : end_idx + 1]))


def find_left_min_at_oscillation(
    y,
    start_idx,
    peak_idx,
    min_offset=5,
    osc_window=12,
    min_turns=3,
    min_rise_points=8,
):
    candidate_end = peak_idx - min_offset
    if start_idx >= peak_idx or candidate_end <= start_idx:
        return start_idx + int(np.argmin(y[start_idx : peak_idx + 1]))

    for idx in range(candidate_end, start_idx, -1):
        is_local_min = y[idx] <= y[idx - 1] and y[idx] <= y[idx + 1]
        if not is_local_min:
            continue
        if idx + min_rise_points >= len(y):
            continue
        if not np.all(y[idx + 1 : idx + 1 + min_rise_points] > y[idx]):
            continue

        osc_end = min(peak_idx, idx + osc_window)
        d = np.diff(y[idx : osc_end + 1])
        d = d[np.abs(d) > 1e-9]
        if len(d) < 2:
            continue
        turns = int(np.sum(d[:-1] * d[1:] < 0))
        if turns >= min_turns:
            return idx

    return start_idx + int(np.argmin(y[start_idx : peak_idx + 1]))


def get_peak_order_from_time(time_seconds: float):
    if time_seconds < FIRST_PEAK_MIN_TIME_S:
        return None
    if time_seconds <= FIRST_PEAK_MAX_TIME_S:
        return 1
    if time_seconds <= FIRST_PEAK_MAX_TIME_S + PEAK_WINDOW_STEP_S:
        return 2
    return 2 + int(
        np.ceil(
            (time_seconds - (FIRST_PEAK_MAX_TIME_S + PEAK_WINDOW_STEP_S))
            / PEAK_WINDOW_STEP_S
        )
    )



def calculate_porus(
    csv_path: str,
    threshold: float,
    normalize_well: str,
    do_plot: bool = True,
) -> List[str]:
    data = pd.read_csv(csv_path)
    unnamed_cols = [c for c in data.columns if str(c).startswith("Unnamed")]
    if unnamed_cols:
        data = data.drop(columns=unnamed_cols)

    if "Timestamp" not in data.columns:
        raise ValueError("CSV must contain a 'Timestamp' column.")
    if normalize_well not in data.columns:
        raise ValueError(f"Reference well '{normalize_well}' not found in columns.")

    time_delta = pd.to_timedelta(data["Timestamp"])
    data["Timestamp"] = (time_delta - time_delta.iloc[0]).dt.total_seconds()

    well_columns = [c for c in data.columns if c != "Timestamp"]
    color_sequence = (
        px.colors.qualitative.Plotly
        if HAS_PLOTLY
        else ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
    )
    well_color = {col: color_sequence[i % len(color_sequence)] for i, col in enumerate(well_columns)}

    fig = go.Figure() if (do_plot and HAS_PLOTLY) else None
    n_peaks_dict: Dict[str, int] = {}
    integral_dict: Dict[str, List[float]] = {}
    first_peak_height: Dict[str, object] = {}
    first_peak_area: Dict[str, object] = {}
    top_peak_heights: Dict[str, Dict[int, float]] = {}
    top_peak_areas: Dict[str, Dict[int, float]] = {}
    integral_details = []

    for column in data.columns:
        if column == "Timestamp":
            continue

        normalized = data[column] - data[normalize_well]
        normalized = normalized - normalized.iloc[0]
        filtered = signal.medfilt(normalized, kernel_size=5)

        if fig is not None:
            fig.add_trace(
                go.Scatter(
                    x=data["Timestamp"],
                    y=filtered,
                    mode="lines",
                    name=column,
                    line=dict(color=well_color[column]),
                    legendgroup=column,
                )
            )

        candidate_peaks, _ = signal.find_peaks(
            filtered,
            distance=200,
        )
        valid_peaks = []
        integrals = []
        peak_height_by_order = {}
        peak_area_by_order = {}
        peak_prom_by_order = {}

        for peak in candidate_peaks:
            start = max(0, peak - 30)
            end = min(len(filtered) - 1, peak + 300)

            left_min_idx = find_left_min_at_oscillation(filtered, start, peak)
            right_min_idx = find_right_min_at_oscillation(filtered, peak, end)
            if right_min_idx <= left_min_idx:
                left_min_idx = start
                right_min_idx = end

            peak_height_abs = float(filtered[peak])
            left_base_height = float(filtered[left_min_idx])
            prominence_i = float(peak_height_abs - left_base_height)
            if prominence_i < threshold:
                continue
            valid_peaks.append(int(peak))

            x_seg = data["Timestamp"][left_min_idx : right_min_idx + 1].to_numpy()
            y_seg = filtered[left_min_idx : right_min_idx + 1]

            x_left = x_seg[0]
            x_right = x_seg[-1]
            y_left = y_seg[0]
            y_right = y_seg[-1]
            if x_right == x_left:
                peak_baseline = np.full_like(y_seg, y_left)
            else:
                peak_baseline = y_left + (y_right - y_left) * (x_seg - x_left) / (x_right - x_left)

            raw_area = integrate.trapezoid(y_seg, x_seg)
            peak_baseline_area = integrate.trapezoid(peak_baseline, x_seg)
            corrected_area = raw_area - peak_baseline_area
            peak_relative_height = prominence_i
            peak_time_i = float(data["Timestamp"][peak])

            peak_order = get_peak_order_from_time(peak_time_i)
            if peak_order is not None and (
                peak_order not in peak_prom_by_order
                or prominence_i > peak_prom_by_order[peak_order]
            ):
                peak_prom_by_order[peak_order] = prominence_i
                peak_height_by_order[peak_order] = peak_relative_height
                peak_area_by_order[peak_order] = corrected_area

            if fig is not None:
                fig.add_trace(
                    go.Scatter(
                        x=x_seg,
                        y=peak_baseline,
                        mode="lines",
                        line=dict(color=well_color[column], width=2, dash="dash"),
                        name=f"{column} baseline",
                        legendgroup=column,
                        showlegend=False,
                    )
                )

            integrals.append(corrected_area)
            peak_order_export = int(peak_order) if peak_order is not None else np.nan
            integral_details.append(
                {
                    "well": column,
                    "peak_order": peak_order_export,
                    "peak_index": int(peak),
                    "peak_time": float(data["Timestamp"][peak]),
                    "peak_height": peak_height_abs,
                    "peak_prominence": prominence_i,
                    "prominence_left_base_index": int(left_min_idx),
                    "prominence_left_base_time": float(data["Timestamp"][left_min_idx]),
                    "prominence_left_base_height": left_base_height,
                    "prominence_right_base_index": int(right_min_idx),
                    "prominence_right_base_time": float(data["Timestamp"][right_min_idx]),
                    "prominence_right_base_height": float(filtered[right_min_idx]),
                    "prominence_base_height": left_base_height,
                    "prominence_recalc": float(peak_height_abs - left_base_height),
                    "start_time": float(data["Timestamp"][left_min_idx]),
                    "end_time": float(data["Timestamp"][right_min_idx]),
                    "raw_area": float(raw_area),
                    "peak_baseline_area": float(peak_baseline_area),
                    "area": float(corrected_area),
                }
            )

            if fig is not None:
                fig.add_trace(
                    go.Scatter(
                        x=[data["Timestamp"][peak]],
                        y=[filtered[peak]],
                        mode="text",
                        text=[f"{integrals[-1]:.2f}"],
                        textposition="top center",
                        name=f"{column} area label",
                        legendgroup=column,
                        showlegend=False,
                    )
                )

        if len(valid_peaks) == 0:
            first_peak_height[column] = f"<{threshold}"
            first_peak_area[column] = "N/A"
        elif 1 not in peak_height_by_order or 1 not in peak_area_by_order:
            first_peak_height[column] = "N/A(0-300s)"
            first_peak_area[column] = "N/A(0-300s)"
        else:
            first_peak_height[column] = float(peak_height_by_order[1])
            first_peak_area[column] = float(peak_area_by_order[1])

        top_peak_heights[column] = peak_height_by_order
        top_peak_areas[column] = peak_area_by_order
        n_peaks_dict[column] = len(valid_peaks)
        integral_dict[column] = integrals

        if fig is not None:
            fig.add_trace(
                go.Scatter(
                    x=[data["Timestamp"][peak] for peak in valid_peaks],
                    y=[filtered[i] for i in valid_peaks],
                    mode="markers",
                    marker=dict(size=8, color="red", symbol="cross"),
                    name=f"{column} peaks",
                    legendgroup=column,
                    showlegend=False,
                )
            )

    if fig is not None:
        fig.update_layout(
            title=dict(text=os.path.basename(csv_path), x=0.5, xanchor="center"),
            legend=dict(groupclick="togglegroup"),
        )
        fig.show()

    out_dir = os.path.dirname(csv_path) or "."
    base = os.path.splitext(os.path.basename(csv_path))[0]
    output_paths: List[str] = []

    rows = []
    cols = []
    for col in data.columns:
        if col == "Timestamp":
            continue
        r, c = parse_well_name(col)
        if r is not None:
            rows.append(r)
            cols.append(c)
    if rows and cols:
        row_labels = sorted(set(rows))
        col_labels = sorted(set(cols))
        height_plate = pd.DataFrame(index=row_labels, columns=col_labels)
        area_plate = pd.DataFrame(index=row_labels, columns=col_labels)
        for col in data.columns:
            if col == "Timestamp":
                continue
            r, c = parse_well_name(col)
            if r is None:
                continue
            height_plate.loc[r, c] = first_peak_height.get(col, f"<{threshold}")
            area_plate.loc[r, c] = first_peak_area.get(col, "N/A")

        height_path = os.path.join(out_dir, f"{base}_first_peak_height.csv")
        area_path = os.path.join(out_dir, f"{base}_first_peak_area.csv")
        height_plate.to_csv(height_path)
        area_plate.to_csv(area_path)
        output_paths.extend([height_path, area_path])

    details_df = pd.DataFrame(integral_details)
    if not details_df.empty:
        details_path = os.path.join(out_dir, f"{base}_integral_details.csv")
        details_df.to_csv(details_path, index=False)
        output_paths.append(details_path)

    peak_cols = [f"peak_{i}" for i in range(1, 11)]
    height_top10_df = pd.DataFrame(index=well_columns, columns=peak_cols)
    area_top10_df = pd.DataFrame(index=well_columns, columns=peak_cols)
    top10_records = []
    for well in well_columns:
        heights = top_peak_heights.get(well, {})
        areas = top_peak_areas.get(well, {})
        for i in range(10):
            order = i + 1
            height_val = float(heights[order]) if order in heights else np.nan
            area_val = float(areas[order]) if order in areas else np.nan
            height_top10_df.loc[well, f"peak_{i+1}"] = height_val
            area_top10_df.loc[well, f"peak_{i+1}"] = area_val
            top10_records.append(
                {
                    "well": well,
                    "peak_order": order,
                    "peak_height": height_val,
                    "peak_area": area_val,
                }
            )

    top10_height_path = os.path.join(out_dir, f"{base}_top10_peak_height.csv")
    top10_area_path = os.path.join(out_dir, f"{base}_top10_peak_area.csv")
    top10_info_path = os.path.join(out_dir, f"{base}_top10_peak_info.csv")
    height_top10_df.to_csv(top10_height_path)
    area_top10_df.to_csv(top10_area_path)
    pd.DataFrame(top10_records).to_csv(top10_info_path, index=False)
    output_paths.extend([top10_height_path, top10_area_path, top10_info_path])

    return output_paths


class DropLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                paths = []
                for url in urls:
                    path = url.toLocalFile()
                    if path and (os.path.isdir(path) or os.path.isfile(path)):
                        paths.append(path)
                if paths:
                    self.setText("; ".join(paths))
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Porus Peak Integration Tool (PyQt)")

        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        grid = QGridLayout()
        layout.addLayout(grid)

        grid.addWidget(QLabel("Folders:"), 0, 0)
        self.folder_edit = DropLineEdit()
        self.folder_edit.setPlaceholderText("Select or drag one/more folders (separate by ';')")
        grid.addWidget(self.folder_edit, 0, 1)
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self.browse_folders)
        grid.addWidget(self.browse_btn, 0, 2)

        grid.addWidget(QLabel("Prominence threshold:"), 1, 0)
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setDecimals(6)
        self.threshold_spin.setRange(-1e9, 1e9)
        self.threshold_spin.setValue(0.2)
        self.threshold_spin.setSingleStep(0.01)
        grid.addWidget(self.threshold_spin, 1, 1)

        grid.addWidget(QLabel("Reference well:"), 2, 0)
        self.ref_edit = QLineEdit()
        self.ref_edit.setText("9B")
        self.ref_edit.setPlaceholderText("e.g. 9B")
        grid.addWidget(self.ref_edit, 2, 1)

        self.plot_check = QCheckBox("Show interactive plot (Plotly)")
        self.plot_check.setChecked(True)
        self.plot_check.setEnabled(HAS_PLOTLY)
        if not HAS_PLOTLY:
            self.plot_check.setText("Show interactive plot (Plotly not installed)")
        grid.addWidget(self.plot_check, 3, 1)

        btn_row = QHBoxLayout()
        layout.addLayout(btn_row)
        self.run_btn = QPushButton("Run")
        self.run_btn.clicked.connect(self.run_analysis)
        btn_row.addStretch(1)
        btn_row.addWidget(self.run_btn)

        note = QLabel(
            "Peak windows: peak1=0-300 s; then each next window is +380 s (300-680, 680-1060, ...)."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self.resize(920, 240)

    def browse_folders(self):
        paths = self.select_multiple_folders()
        if paths:
            self.folder_edit.setText("; ".join(paths))

    def select_multiple_folders(self) -> List[str]:
        dialog = QFileDialog(self, "Select one or more folders")
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)

        for view in dialog.findChildren((QListView, QTreeView)):
            view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        if dialog.exec():
            return [p for p in dialog.selectedFiles() if os.path.isdir(p)]
        return []

    def run_analysis(self):
        raw_folders = self.folder_edit.text().strip()
        folder_paths = [p.strip() for p in raw_folders.split(";") if p.strip()]
        if not folder_paths:
            QMessageBox.critical(self, "Error", "Please select at least one valid folder.")
            return
        folder_paths = [os.path.normpath(p) for p in folder_paths]

        invalid_folders = [p for p in folder_paths if not os.path.isdir(p)]
        if invalid_folders:
            QMessageBox.critical(
                self,
                "Error",
                "These paths are not valid folders:\n" + "\n".join(invalid_folders),
            )
            return

        csv_paths: List[str] = []
        for folder in folder_paths:
            for name in sorted(os.listdir(folder)):
                if name.lower().endswith("_t.csv"):
                    full_path = os.path.join(folder, name)
                    if os.path.isfile(full_path):
                        csv_paths.append(full_path)

        if not csv_paths:
            QMessageBox.critical(self, "Error", "No files ending with '_T.csv' were found.")
            return

        threshold = float(self.threshold_spin.value())
        normalize_well = self.ref_edit.text().strip()
        if not normalize_well:
            QMessageBox.critical(self, "Error", "Please input a reference well (e.g. 9B).")
            return

        try:
            all_outputs: List[str] = []
            failed_files: List[str] = []
            for csv_path in csv_paths:
                try:
                    output_paths = calculate_porus(
                        csv_path=csv_path,
                        threshold=threshold,
                        normalize_well=normalize_well,
                        do_plot=self.plot_check.isChecked(),
                    )
                    all_outputs.extend(output_paths)
                except Exception as exc:
                    failed_files.append(f"{csv_path} -> {exc}")

            if all_outputs:
                saved_text = "\n".join(f"{i + 1}) {p}" for i, p in enumerate(all_outputs))
            else:
                saved_text = "(No output files generated)"

            fail_text = ""
            if failed_files:
                fail_text = "\n\nFailed files:\n" + "\n".join(failed_files)

            QMessageBox.information(
                self,
                "Done",
                f"Analysis completed.\nProcessed CSV files: {len(csv_paths) - len(failed_files)}/{len(csv_paths)}"
                + "\n\nSaved:\n"
                + saved_text
                + fail_text,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))


def main():
    if getattr(sys, "frozen", False):
        os.chdir(os.path.dirname(sys.executable))

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
