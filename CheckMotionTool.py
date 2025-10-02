# -*- coding: utf-8 -*-

"""Utility dialog for creating check motions on joints."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from PySide2 import QtCore, QtGui, QtWidgets
import maya.cmds as cmds


def maya_main_window():
    import maya.OpenMayaUI as omui
    from shiboken2 import wrapInstance

    ptr = omui.MQtUtil.mainWindow()
    if ptr is None:
        raise RuntimeError("Mayaのメインウィンドウが取得できませんでした。")
    return wrapInstance(int(ptr), QtWidgets.QWidget)


EPSILON = 1.0e-4
ROTATE_AXES: Sequence[str] = ("X", "Y", "Z")
MIRROR_KEYWORDS: Sequence[str] = (
    "Clavicle",
    "Upperarm",
    "Forearm",
    "Hand",
    "Thumb",
    "Index",
    "Middle",
    "Ring",
    "Pinky",
    "Thigh",
    "Calf",
    "Foot",
    "Toe",
)
DEFAULT_MATRIX_DATA = [
    {
        "joint": "Spine",
        "min": {"X": -20, "Y": -15, "Z": -10},
        "max": {"X": 20, "Y": 15, "Z": 10},
    },
    {
        "joint": "Clavicle",
        "min": {"X": -30, "Y": -20, "Z": -40},
        "max": {"X": 45, "Y": 90, "Z": 45},
    },
    {
        "joint": "Upperarm",
        "min": {"X": -90, "Y": -80, "Z": -90},
        "max": {"X": 90, "Y": 100, "Z": 90},
    },
    {
        "joint": "Forearm",
        "min": {"X": -5, "Y": 0, "Z": -5},
        "max": {"X": 5, "Y": 135, "Z": 5},
    },
    {
        "joint": "Hand",
        "min": {"X": -45, "Y": -45, "Z": -30},
        "max": {"X": 45, "Y": 45, "Z": 30},
    },
    {
        "joint": ["Thumb", "Thumb1", "Thumb2"],
        "min": {"X": -15, "Y": -10, "Z": -10},
        "max": {"X": 60, "Y": 45, "Z": 45},
    },
    {
        "joint": ["Index", "Index1", "Index2"],
        "min": {"X": -10, "Y": -5, "Z": -5},
        "max": {"X": 90, "Y": 45, "Z": 45},
    },
    {
        "joint": ["Middle", "Middle1", "Middle2"],
        "min": {"X": -10, "Y": -5, "Z": -5},
        "max": {"X": 90, "Y": 45, "Z": 45},
    },
    {
        "joint": ["Ring", "Ring1", "Ring2"],
        "min": {"X": -10, "Y": -5, "Z": -5},
        "max": {"X": 90, "Y": 45, "Z": 45},
    },
    {
        "joint": ["Pinky", "Pinky1", "Pinky2"],
        "min": {"X": -10, "Y": -5, "Z": -5},
        "max": {"X": 90, "Y": 45, "Z": 45},
    },
    {
        "joint": "Thigh",
        "min": {"X": -90, "Y": -45, "Z": -60},
        "max": {"X": 90, "Y": 45, "Z": 60},
    },
    {
        "joint": "Calf",
        "min": {"X": -5, "Y": 0, "Z": -5},
        "max": {"X": 5, "Y": 140, "Z": 5},
    },
    {
        "joint": "Foot",
        "min": {"X": -45, "Y": -35, "Z": -45},
        "max": {"X": 45, "Y": 35, "Z": 45},
    },
    {
        "joint": "Toe",
        "min": {"X": -30, "Y": -20, "Z": -20},
        "max": {"X": 45, "Y": 20, "Z": 20},
    },
    {
        "joint": "Neck",
        "min": {"X": -35, "Y": -60, "Z": -35},
        "max": {"X": 35, "Y": 60, "Z": 35},
    },
]

def _is_non_zero(value: float) -> bool:
    return abs(value) > EPSILON

def _should_attempt_mirror(joint: str) -> bool:
    short_name = joint.split("|")[-1]
    lower = short_name.lower()
    return any(keyword.lower() in lower for keyword in MIRROR_KEYWORDS)


def _chain_group_key_from_joint(joint: str) -> Optional[str]:
    short_name = joint.split("|")[-1]
    base_name, side = _split_side(short_name)
    if side == "C":
        return None

    sequences = [segment for segment in re.findall(r"[A-Za-z]+", base_name) if segment]
    if sequences:
        token = max(sequences, key=len)
    else:
        token = base_name.rstrip("0123456789")

    if not token:
        return None
    return f"{token.lower()}_{side}"

def _cut_rotate_keys(joint: str):
    rotate_attrs = [f"rotate{axis}" for axis in ROTATE_AXES]
    has_keys = False
    for axis in ROTATE_AXES:
        attr = f"{joint}.rotate{axis}"
        if cmds.keyframe(attr, query=True, keyframeCount=True):
            has_keys = True
            break
    if has_keys:
        cmds.cutKey(joint, attribute=rotate_attrs)


def _set_default_keys(joint: str, frame: float, value: float = 0.0):
    for axis in ROTATE_AXES:
        cmds.setKeyframe(joint, attribute=f"rotate{axis}", t=frame, v=value)

def _mirror_axis_values(values: Dict[str, float]) -> Dict[str, float]:
    mirrored: Dict[str, float] = {}
    for axis in ROTATE_AXES:
        value = float(values.get(axis, 0.0))
        if axis == "Z":
            value = -value
        mirrored[axis] = value
    return mirrored


def _list_descendant_joints(root: str) -> List[str]:
    if not cmds.objExists(root):
        return []

    long_names = cmds.ls(root, long=True)
    if not long_names:
        return []

    root_long = long_names[0]
    descendants = cmds.listRelatives(root_long, ad=True, type="joint", fullPath=True) or []
    descendants.append(root_long)
    return descendants


def _to_long_name(node: str) -> Optional[str]:
    names = cmds.ls(node, long=True)
    if names:
        return names[0]
    return None
@dataclass
class CheckMotionResult:
    joint: str
    start_frame: float
    end_frame: float
    has_keys: bool


@dataclass
class _ResolvedConfig:
    entry: str
    joint: str
    rotate_min: Dict[str, float]
    rotate_max: Dict[str, float]
    group_key: Optional[str]


def apply_check_motion(
    joint: str,
    rotate_min: Dict[str, float],
    rotate_max: Dict[str, float],
    start_frame: float,
    interval: float,
    default_value: float = 0.0,
) -> CheckMotionResult:
    if not cmds.objExists(joint):
        raise ValueError(f"Joint '{joint}' does not exist.")

    rotate_min = {axis: float(rotate_min.get(axis, 0.0)) for axis in ROTATE_AXES}
    rotate_max = {axis: float(rotate_max.get(axis, 0.0)) for axis in ROTATE_AXES}

    _cut_rotate_keys(joint)

    current_frame = start_frame
    _set_default_keys(joint, current_frame, default_value)

    steps = 0
    for axis in ROTATE_AXES:
        min_value = rotate_min[axis]
        max_value = rotate_max[axis]
        attribute = f"rotate{axis}"

        if _is_non_zero(min_value):
            current_frame += interval
            cmds.setKeyframe(joint, attribute=attribute, t=current_frame, v=min_value)
            steps += 1

        if _is_non_zero(max_value):
            current_frame += interval
            cmds.setKeyframe(joint, attribute=attribute, t=current_frame, v=max_value)
            steps += 1

    has_keys = steps > 0

    if has_keys:
        current_frame += interval
        _set_default_keys(joint, current_frame, default_value)

    return CheckMotionResult(
        joint=joint,
        start_frame=start_frame,
        end_frame=current_frame,
        has_keys=has_keys,
    )


def _split_side(name: str) -> Tuple[str, str]:
    if name.endswith("_L"):
        return name[:-2], "L"
    if name.endswith("_R"):
        return name[:-2], "R"
    return name, "C"


def _order_joint_configs(
    configs: Iterable[Tuple[str, Dict[str, float], Dict[str, float]]]
) -> List[Tuple[str, Dict[str, float], Dict[str, float]]]:
    grouped: Dict[str, Dict[str, List[Tuple[str, Dict[str, float], Dict[str, float]]]]] = {}
    base_order: List[str] = []

    for config in configs:
        base, side = _split_side(config[0])
        if base not in grouped:
            grouped[base] = {"C": [], "L": [], "R": []}
            base_order.append(base)
        grouped[base][side].append(config)

    ordered: List[Tuple[str, Dict[str, float], Dict[str, float]]] = []
    for base in base_order:
        ordered.extend(grouped[base]["C"])
        ordered.extend(grouped[base]["L"])
        ordered.extend(grouped[base]["R"])
    return ordered


class _AxisInputWidget(QtWidgets.QWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super(_AxisInputWidget, self).__init__(parent)

        layout = QtWidgets.QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(6)

        self.inputs: Dict[str, Tuple[QtWidgets.QDoubleSpinBox, QtWidgets.QDoubleSpinBox]] = {}

        for row, axis in enumerate(ROTATE_AXES):
            label = QtWidgets.QLabel(f"Rotate {axis}")
            label.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)
            min_spin = self._create_spin_box()
            max_spin = self._create_spin_box()
            layout.addWidget(label, row, 0)
            layout.addWidget(min_spin, row, 1)
            layout.addWidget(max_spin, row, 2)
            self.inputs[axis] = (min_spin, max_spin)

    @staticmethod
    def _create_spin_box() -> QtWidgets.QDoubleSpinBox:
        spin = QtWidgets.QDoubleSpinBox()
        spin.setRange(-720.0, 720.0)
        spin.setDecimals(3)
        spin.setSingleStep(1.0)
        return spin

    def set_values(self, values_min: Dict[str, float], values_max: Dict[str, float]):
        for axis in ROTATE_AXES:
            min_spin, max_spin = self.inputs[axis]
            min_spin.setValue(float(values_min.get(axis, 0.0)))
            max_spin.setValue(float(values_max.get(axis, 0.0)))

    def get_values(self) -> Tuple[Dict[str, float], Dict[str, float]]:
        min_values: Dict[str, float] = {}
        max_values: Dict[str, float] = {}
        for axis, (min_spin, max_spin) in self.inputs.items():
            min_values[axis] = min_spin.value()
            max_values[axis] = max_spin.value()
        return min_values, max_values


class CheckMotionToolDialog(QtWidgets.QDialog):
    _instance: Optional["CheckMotionToolDialog"] = None

    @classmethod
    def show_dialog(cls):
        if cls._instance is None:
            cls._instance = CheckMotionToolDialog()
        cls._instance.show()
        cls._instance.raise_()
        cls._instance.activateWindow()
        return cls._instance

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super(CheckMotionToolDialog, self).__init__(parent or maya_main_window())

        self.setWindowTitle(u"Check Motion Tool")
        self.setObjectName("checkMotionToolDialog")
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        self.resize(720, 420)

        self._create_widgets()
        self._create_layout()
        self._create_connections()

        self._copied_row_values: Optional[Dict[str, Dict[str, float]]] = None

        self._populate_default_rows()

    # UI creation ---------------------------------------------------------
    def _create_widgets(self):
        self.tab_widget = QtWidgets.QTabWidget()

        # Batch tab widgets
        self.batch_root_edit = QtWidgets.QLineEdit()
        self.batch_root_edit.setPlaceholderText(u"Search Root (optional)")
        self.batch_root_edit.setReadOnly(True)
        self.batch_root_button = QtWidgets.QPushButton(u"Get Selection")
        self.batch_table = QtWidgets.QTableWidget(0, 7)
        self.batch_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.batch_table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.batch_table.setEditTriggers(QtWidgets.QAbstractItemView.AllEditTriggers)
        self.batch_table.setHorizontalHeaderLabels(
            [
                u"Joint",
                u"Min X",
                u"Max X",
                u"Min Y",
                u"Max Y",
                u"Min Z",
                u"Max Z",
            ]
        )
        self.batch_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        for col in range(1, 7):
            self.batch_table.horizontalHeader().setSectionResizeMode(col, QtWidgets.QHeaderView.ResizeToContents)
        self.table_sign_button = QtWidgets.QPushButton(u"±")
        self.table_copy_button = QtWidgets.QPushButton(u"Copy")
        self.table_paste_button = QtWidgets.QPushButton(u"Paste")
        self.table_value_buttons: List[QtWidgets.QPushButton] = []
        for widget in (self.table_sign_button, self.table_copy_button, self.table_paste_button):
            widget.setFocusPolicy(QtCore.Qt.NoFocus)
        for value in (0, 10, 15, 30, 45, 60, 90):
            button = QtWidgets.QPushButton(str(value))
            button.setProperty("tableValue", value)
            button.setFocusPolicy(QtCore.Qt.NoFocus)
            self.table_value_buttons.append(button)
        self.reset_defaults_button = QtWidgets.QPushButton(u"Reset Defaults")
        self.reset_defaults_button.setFocusPolicy(QtCore.Qt.NoFocus)
        self.load_json_button = QtWidgets.QPushButton(u"Load JSON")
        self.save_json_button = QtWidgets.QPushButton(u"Save JSON")
        self.add_row_button = QtWidgets.QPushButton(u"Add Row")
        self.remove_row_button = QtWidgets.QPushButton(u"Remove Selected")

        self.batch_start_spin = QtWidgets.QSpinBox()
        self.batch_start_spin.setRange(-99999, 999999)
        self.batch_start_spin.setValue(0)
        self.batch_interval_spin = QtWidgets.QSpinBox()
        self.batch_interval_spin.setRange(1, 1000)
        self.batch_interval_spin.setValue(5)

        self.apply_batch_button = QtWidgets.QPushButton(u"Create Check Motion")
        self.batch_mirror_checkbox = QtWidgets.QCheckBox(u"Mirror Opposite Side")
        self.batch_mirror_checkbox.setChecked(True)

        # Single tab widgets
        self.single_joint_edit = QtWidgets.QLineEdit()
        self.single_joint_edit.setPlaceholderText(u"No joint selected")
        self.single_joint_edit.setReadOnly(True)
        self.single_get_button = QtWidgets.QPushButton(u"Get Selection")

        self.single_start_spin = QtWidgets.QSpinBox()
        self.single_start_spin.setRange(-99999, 999999)
        self.single_start_spin.setValue(0)
        self.single_interval_spin = QtWidgets.QSpinBox()
        self.single_interval_spin.setRange(1, 1000)
        self.single_interval_spin.setValue(5)

        self.single_axis_widget = _AxisInputWidget()
        self.single_mirror_checkbox = QtWidgets.QCheckBox(u"Mirror Opposite Side")
        self.single_mirror_checkbox.setChecked(True)

        self.apply_single_button = QtWidgets.QPushButton(u"Create")

    def _create_layout(self):
        batch_tab = QtWidgets.QWidget()
        batch_layout = QtWidgets.QVBoxLayout(batch_tab)
        root_layout = QtWidgets.QHBoxLayout()
        root_layout.addWidget(QtWidgets.QLabel(u"Search Root:"))
        root_layout.addWidget(self.batch_root_edit)
        root_layout.addWidget(self.batch_root_button)
        batch_layout.addLayout(root_layout)

        table_tool_group = QtWidgets.QGroupBox(u"Table Tools")
        table_tool_layout = QtWidgets.QHBoxLayout(table_tool_group)
        table_tool_layout.addWidget(self.table_sign_button)
        table_tool_layout.addWidget(self.table_copy_button)
        table_tool_layout.addWidget(self.table_paste_button)
        for button in self.table_value_buttons:
            table_tool_layout.addWidget(button)
        table_tool_layout.addStretch(1)
        table_tool_layout.addWidget(self.reset_defaults_button)
        table_tool_layout.addWidget(self.load_json_button)
        table_tool_layout.addWidget(self.save_json_button)

        batch_layout.addWidget(table_tool_group)
        batch_layout.addWidget(self.batch_table)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addWidget(self.add_row_button)
        button_layout.addWidget(self.remove_row_button)
        button_layout.addStretch(1)
        batch_layout.addLayout(button_layout)

        settings_layout = QtWidgets.QFormLayout()
        settings_layout.addRow(u"Start Frame:", self.batch_start_spin)
        settings_layout.addRow(u"Interval:", self.batch_interval_spin)
        settings_layout.addRow(self.batch_mirror_checkbox)
        batch_layout.addLayout(settings_layout)

        batch_layout.addWidget(self.apply_batch_button)

        single_tab = QtWidgets.QWidget()
        single_layout = QtWidgets.QVBoxLayout(single_tab)

        joint_layout = QtWidgets.QHBoxLayout()
        joint_layout.addWidget(QtWidgets.QLabel(u"Joint:"))
        joint_layout.addWidget(self.single_joint_edit)
        joint_layout.addWidget(self.single_get_button)
        single_layout.addLayout(joint_layout)

        single_form = QtWidgets.QFormLayout()
        single_form.addRow(u"Start Frame (0 = Current):", self.single_start_spin)
        single_form.addRow(u"Interval:", self.single_interval_spin)
        single_layout.addLayout(single_form)

        single_layout.addWidget(self.single_axis_widget)
        single_layout.addWidget(self.single_mirror_checkbox)

        single_layout.addWidget(self.apply_single_button)
        single_layout.addStretch(1)

        self.tab_widget.addTab(batch_tab, u"Batch")
        self.tab_widget.addTab(single_tab, u"Single Joint")

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addWidget(self.tab_widget)

    def _create_connections(self):
        self.batch_root_button.clicked.connect(self._on_get_batch_root)
        self.add_row_button.clicked.connect(self._on_add_row)
        self.remove_row_button.clicked.connect(self._on_remove_selected_rows)
        self.apply_batch_button.clicked.connect(self._on_apply_batch_clicked)
        self.table_sign_button.clicked.connect(self._on_table_sign_clicked)
        self.table_copy_button.clicked.connect(self._on_table_copy_clicked)
        self.table_paste_button.clicked.connect(self._on_table_paste_clicked)
        for button in self.table_value_buttons:
            button.clicked.connect(self._on_table_value_clicked)
        self.reset_defaults_button.clicked.connect(self._on_reset_defaults_clicked)
        self.load_json_button.clicked.connect(self._on_load_json_clicked)
        self.save_json_button.clicked.connect(self._on_save_json_clicked)
        self.single_get_button.clicked.connect(self._on_get_single_joint)
        self.apply_single_button.clicked.connect(self._on_apply_single_clicked)

    # Batch tab -----------------------------------------------------------
    def _on_get_batch_root(self):
        selection = cmds.ls(selection=True, type="joint") or []
        if not selection:
            cmds.warning(u"検索開始ジョイントを選択してください。")
            return

        long_name = _to_long_name(selection[0])
        if not long_name:
            cmds.warning(u"選択ジョイントのロングネームを取得できませんでした。")
            return

        self.batch_root_edit.setText(long_name)

    def _populate_default_rows(self):
        self.batch_table.setRowCount(0)
        matrix_entries = self._normalize_matrix_entries(DEFAULT_MATRIX_DATA)
        if not matrix_entries:
            fallback_joints = [
                "Spine",
                "Clavicle",
                "Upperarm",
                "Forearm",
                "Hand",
                "Thumb",
                "Index",
                "Middle",
                "Ring",
                "Pinky",
                "Thigh",
                "Calf",
                "Foot",
                "Toe",
                "Neck",
            ]
            for joint in fallback_joints:
                self._add_row(joint)
            return

        for joint, rotate_min, rotate_max in matrix_entries:
            self._add_row(joint)
            self._set_row_values(self.batch_table.rowCount() - 1, rotate_min, rotate_max)
        self._copied_row_values = None

    def _create_spin_cell(self) -> QtWidgets.QDoubleSpinBox:
        spin = QtWidgets.QDoubleSpinBox()
        spin.setRange(-720.0, 720.0)
        spin.setDecimals(3)
        spin.setSingleStep(1.0)
        spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        return spin

    def _add_row(self, joint: str = ""):
        row = self.batch_table.rowCount()
        self.batch_table.insertRow(row)

        item = QtWidgets.QTableWidgetItem(joint)
        item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
        self.batch_table.setItem(row, 0, item)

        for col in range(1, 7):
            spin = self._create_spin_cell()
            self.batch_table.setCellWidget(row, col, spin)

    def _set_row_values(
        self,
        row: int,
        rotate_min: Dict[str, float],
        rotate_max: Dict[str, float],
    ) -> None:
        for axis_index, axis in enumerate(ROTATE_AXES):
            min_widget = self.batch_table.cellWidget(row, 1 + axis_index * 2)
            max_widget = self.batch_table.cellWidget(row, 2 + axis_index * 2)
            if isinstance(min_widget, QtWidgets.QDoubleSpinBox):
                min_widget.setValue(float(rotate_min.get(axis, 0.0)))
            if isinstance(max_widget, QtWidgets.QDoubleSpinBox):
                max_widget.setValue(float(rotate_max.get(axis, 0.0)))

    def _row_spinboxes(self, row: int) -> List[QtWidgets.QDoubleSpinBox]:
        spinboxes: List[QtWidgets.QDoubleSpinBox] = []
        for axis_index in range(len(ROTATE_AXES)):
            min_widget = self.batch_table.cellWidget(row, 1 + axis_index * 2)
            max_widget = self.batch_table.cellWidget(row, 2 + axis_index * 2)
            if isinstance(min_widget, QtWidgets.QDoubleSpinBox):
                spinboxes.append(min_widget)
            if isinstance(max_widget, QtWidgets.QDoubleSpinBox):
                spinboxes.append(max_widget)
        return spinboxes

    def _selected_rows(self) -> List[int]:
        selection_model = self.batch_table.selectionModel()
        if not selection_model:
            return []
        return sorted({index.row() for index in selection_model.selectedRows()})

    def _focused_row(self) -> Optional[int]:
        current_row = self.batch_table.currentRow()
        if current_row >= 0:
            return current_row
        widget = QtWidgets.QApplication.focusWidget()
        if isinstance(widget, QtWidgets.QDoubleSpinBox):
            index = self.batch_table.indexAt(
                widget.mapTo(self.batch_table.viewport(), QtCore.QPoint(0, 0))
            )
            if index.isValid():
                return index.row()
        return None

    def _target_rows(self) -> List[int]:
        rows = self._selected_rows()
        if rows:
            return rows
        focused_row = self._focused_row()
        if focused_row is not None:
            return [focused_row]
        return []

    def _target_spinboxes(self) -> List[QtWidgets.QDoubleSpinBox]:
        rows = self._target_rows()
        if rows:
            spinboxes: List[QtWidgets.QDoubleSpinBox] = []
            for row in rows:
                spinboxes.extend(self._row_spinboxes(row))
            return spinboxes
        widget = QtWidgets.QApplication.focusWidget()
        if isinstance(widget, QtWidgets.QDoubleSpinBox):
            return [widget]
        return []

    def _apply_to_spinboxes(self, transform: Callable[[float], float]) -> None:
        spinboxes = self._target_spinboxes()
        if not spinboxes:
            return
        for spin in spinboxes:
            spin.setValue(transform(spin.value()))

    @staticmethod
    def _normalize_matrix_entries(
        data: object,
    ) -> List[Tuple[str, Dict[str, float], Dict[str, float]]]:
        entries: List[Tuple[str, Dict[str, float], Dict[str, float]]] = []

        if isinstance(data, dict):
            if {"joint", "min", "max"} <= set(data.keys()):
                data = [data]
            elif "entries" in data and isinstance(data["entries"], list):
                data = data["entries"]
            else:
                mapped: List[Dict[str, object]] = []
                for key, value in data.items():
                    if isinstance(value, dict):
                        entry = dict(value)
                        entry.setdefault("joint", key)
                        mapped.append(entry)
                data = mapped

        if not isinstance(data, list):
            return entries

        for item in data:
            if not isinstance(item, dict):
                continue

            names = item.get("joint") or item.get("joints") or item.get("names")
            if isinstance(names, str):
                name_list = [names]
            elif isinstance(names, (list, tuple)):
                name_list = [str(name).strip() for name in names if str(name).strip()]
            else:
                continue
            if not name_list:
                continue

            min_values = (
                item.get("min")
                or item.get("rotateMin")
                or item.get("rotate_min")
            )
            max_values = (
                item.get("max")
                or item.get("rotateMax")
                or item.get("rotate_max")
            )
            if not isinstance(min_values, dict) or not isinstance(max_values, dict):
                continue

            rotate_min = {axis: float(min_values.get(axis, 0.0)) for axis in ROTATE_AXES}
            rotate_max = {axis: float(max_values.get(axis, 0.0)) for axis in ROTATE_AXES}

            for name in name_list:
                stripped = str(name).strip()
                if not stripped:
                    continue
                entries.append((stripped, rotate_min, rotate_max))
        return entries

    def _extract_row_payload(self, row: int) -> Optional[Dict[str, Dict[str, float]]]:
        if row < 0 or row >= self.batch_table.rowCount():
            return None
        item = self.batch_table.item(row, 0)
        if item is None:
            return None
        joint = item.text().strip()
        if not joint:
            return None
        rotate_min: Dict[str, float] = {}
        rotate_max: Dict[str, float] = {}
        for axis_index, axis in enumerate(ROTATE_AXES):
            min_widget = self.batch_table.cellWidget(row, 1 + axis_index * 2)
            max_widget = self.batch_table.cellWidget(row, 2 + axis_index * 2)
            if isinstance(min_widget, QtWidgets.QDoubleSpinBox):
                rotate_min[axis] = float(min_widget.value())
            else:
                rotate_min[axis] = 0.0
            if isinstance(max_widget, QtWidgets.QDoubleSpinBox):
                rotate_max[axis] = float(max_widget.value())
            else:
                rotate_max[axis] = 0.0
        return {"joint": joint, "min": rotate_min, "max": rotate_max}

    def _on_add_row(self):
        self._add_row()

    def _on_remove_selected_rows(self):
        for row in reversed(self._selected_rows()):
            self.batch_table.removeRow(row)

    def _gather_batch_configs(self) -> List[Tuple[str, Dict[str, float], Dict[str, float]]]:
        configs: List[Tuple[str, Dict[str, float], Dict[str, float]]] = []
        for row in range(self.batch_table.rowCount()):
            item = self.batch_table.item(row, 0)
            if item is None:
                continue
            joint = item.text().strip()
            if not joint:
                continue

            rotate_min: Dict[str, float] = {}
            rotate_max: Dict[str, float] = {}
            for axis_index, axis in enumerate(ROTATE_AXES):
                min_widget = self.batch_table.cellWidget(row, 1 + axis_index * 2)
                max_widget = self.batch_table.cellWidget(row, 2 + axis_index * 2)
                if isinstance(min_widget, QtWidgets.QDoubleSpinBox):
                    rotate_min[axis] = min_widget.value()
                if isinstance(max_widget, QtWidgets.QDoubleSpinBox):
                    rotate_max[axis] = max_widget.value()
            configs.append((joint, rotate_min, rotate_max))
        return configs

    def _gather_table_json(self) -> List[Dict[str, object]]:
        def chain_base(name: str) -> str:
            index = len(name)
            while index > 0 and name[index - 1].isdigit():
                index -= 1
            return name[:index] if index > 0 else name

        entries: List[Dict[str, object]] = []
        current_names: List[str] = []
        current_min: Dict[str, float] = {}
        current_max: Dict[str, float] = {}
        current_value_key: Optional[Tuple[float, ...]] = None
        current_base: Optional[str] = None

        def flush_group() -> None:
            nonlocal current_names, current_min, current_max, current_value_key, current_base
            if not current_names:
                return
            entry: Dict[str, object] = {
                "joint": current_names if len(current_names) > 1 else current_names[0],
                "min": current_min,
                "max": current_max,
            }
            entries.append(entry)
            current_names = []
            current_min = {}
            current_max = {}
            current_value_key = None
            current_base = None

        for row in range(self.batch_table.rowCount()):
            payload = self._extract_row_payload(row)
            if payload is None:
                flush_group()
                continue

            value_key = tuple(payload["min"][axis] for axis in ROTATE_AXES) + tuple(
                payload["max"][axis] for axis in ROTATE_AXES
            )
            base_name = chain_base(payload["joint"])

            if (
                current_names
                and current_value_key == value_key
                and current_base == base_name
            ):
                current_names.append(payload["joint"])
            else:
                flush_group()
                current_names = [payload["joint"]]
                current_min = dict(payload["min"])
                current_max = dict(payload["max"])
                current_value_key = value_key
                current_base = base_name

        flush_group()
        return entries

    def _on_table_sign_clicked(self):
        self._apply_to_spinboxes(lambda value: -value)

    def _on_table_value_clicked(self):
        sender = self.sender()
        if not isinstance(sender, QtWidgets.QPushButton):
            return

        value = sender.property("tableValue")
        if value is None:
            return

        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return

        modifiers = QtWidgets.QApplication.keyboardModifiers()
        if modifiers & QtCore.Qt.AltModifier:
            self._apply_to_spinboxes(lambda current, step=numeric_value: current - step)
        elif modifiers & QtCore.Qt.ShiftModifier:
            self._apply_to_spinboxes(lambda current, step=numeric_value: current + step)
        else:
            self._apply_to_spinboxes(lambda _current, target=numeric_value: target)

    def _on_table_copy_clicked(self):
        rows = self._target_rows()
        if not rows:
            return
        payload = self._extract_row_payload(rows[0])
        if payload is None:
            return

        self._copied_row_values = {
            "min": dict(payload["min"]),
            "max": dict(payload["max"]),
        }

        try:
            clipboard_text = json.dumps(payload, ensure_ascii=False)
        except Exception:
            clipboard_text = ""
        if clipboard_text:
            QtWidgets.QApplication.clipboard().setText(clipboard_text)

    def _on_table_paste_clicked(self):
        payload: Optional[Dict[str, Dict[str, float]]] = None
        if self._copied_row_values is not None:
            payload = {
                "min": dict(self._copied_row_values["min"]),
                "max": dict(self._copied_row_values["max"]),
            }
        else:
            clipboard_text = QtWidgets.QApplication.clipboard().text()
            if clipboard_text:
                try:
                    data = json.loads(clipboard_text)
                except ValueError:
                    data = None
                if data is not None:
                    entries = self._normalize_matrix_entries(data)
                    if entries:
                        _, rotate_min, rotate_max = entries[0]
                        payload = {
                            "min": dict(rotate_min),
                            "max": dict(rotate_max),
                        }
        if payload is None:
            return

        rows = self._target_rows()
        if not rows:
            return

        rotate_min = {axis: float(payload["min"].get(axis, 0.0)) for axis in ROTATE_AXES}
        rotate_max = {axis: float(payload["max"].get(axis, 0.0)) for axis in ROTATE_AXES}
        for row in rows:
            self._set_row_values(row, rotate_min, rotate_max)

    def _on_reset_defaults_clicked(self):
        self._copied_row_values = None
        self._populate_default_rows()

    def _on_load_json_clicked(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            u"Load Joint Settings JSON",
            "",
            u"JSON Files (*.json);;All Files (*)",
        )
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception as exc:
            cmds.warning(u"JSONの読み込みに失敗しました: {0}".format(exc))
            return

        entries = self._normalize_matrix_entries(data)
        if not entries:
            cmds.warning(u"JSONに有効なジョイント設定が見つかりません。")
            return

        self.batch_table.setRowCount(0)
        for joint, rotate_min, rotate_max in entries:
            self._add_row(joint)
            self._set_row_values(self.batch_table.rowCount() - 1, rotate_min, rotate_max)
        self._copied_row_values = None

    def _on_save_json_clicked(self):
        entries = self._gather_table_json()
        if not entries:
            cmds.warning(u"保存するジョイント設定がありません。")
            return

        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            u"Save Joint Settings JSON",
            "",
            u"JSON Files (*.json);;All Files (*)",
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump(entries, handle, ensure_ascii=False, indent=2)
        except Exception as exc:
            cmds.warning(u"JSONの書き込みに失敗しました: {0}".format(exc))

    def _get_batch_search_root(self) -> Optional[str]:
        root_text = self.batch_root_edit.text().strip()
        if not root_text:
            return None

        long_name = _to_long_name(root_text)
        if not long_name:
            cmds.warning(u"検索開始ジョイント '{0}' が見つかりません。".format(root_text))
            return None
        return long_name

    def _resolve_joint_entry(self, entry: str, search_root: Optional[str]) -> Optional[str]:
        entry = entry.strip()
        if not entry:
            return None

        long_name = _to_long_name(entry)
        if long_name:
            return long_name

        search_space: List[str] = []
        if search_root and cmds.objExists(search_root):
            search_space = _list_descendant_joints(search_root)
        if not search_space:
            search_space = cmds.ls(type="joint", long=True) or []

        entry_lower = entry.lower()
        exact_matches = [node for node in search_space if node.split("|")[-1] == entry]
        if exact_matches:
            return exact_matches[0]

        partial_matches = [node for node in search_space if entry_lower in node.split("|")[-1].lower()]
        if len(partial_matches) == 1:
            return partial_matches[0]
        if len(partial_matches) > 1:
            def _match_priority(name: str) -> Tuple[int, int]:
                short = name.split("|")[-1]
                base_priority = len(name)
                if short.endswith("_L"):
                    return base_priority, 0
                if short.endswith("_R"):
                    return base_priority, 1
                return base_priority, 2

            partial_matches.sort(key=_match_priority)
            return partial_matches[0]
        return None
      
    def _on_apply_batch_clicked(self):
        configs = _order_joint_configs(self._gather_batch_configs())
        if not configs:
            cmds.warning(u"ジョイントが設定されていません。")
            return

        start_frame = float(self.batch_start_spin.value())
        interval = float(self.batch_interval_spin.value())
        search_root = self._get_batch_search_root()
        mirror_enabled = self.batch_mirror_checkbox.isChecked()

        resolved_configs: List[_ResolvedConfig] = []
        results: List[CheckMotionResult] = []
        errors: List[str] = []

        for entry, rotate_min, rotate_max in configs:
            joint = self._resolve_joint_entry(entry, search_root)
            if not joint:
                errors.append(u"ジョイント '{0}' が見つかりません。".format(entry))
                continue

            resolved_configs.append(
                _ResolvedConfig(
                    entry=entry,
                    joint=joint,
                    rotate_min={axis: float(rotate_min.get(axis, 0.0)) for axis in ROTATE_AXES},
                    rotate_max={axis: float(rotate_max.get(axis, 0.0)) for axis in ROTATE_AXES},
                    group_key=_chain_group_key_from_joint(joint),
                )
            )

        if not resolved_configs:
            if errors:
                for error in errors:
                    cmds.warning(error)
            return

        processed_joints: Set[str] = set()
        processed_groups: Set[str] = set()

        cmds.undoInfo(openChunk=True, chunkName="CreateCheckMotionBatch")
        try:
            current_frame = start_frame
            index = 0
            while index < len(resolved_configs):
                config = resolved_configs[index]
                if config.joint in processed_joints:
                    index += 1
                    continue
                if config.group_key and config.group_key not in processed_groups:
                    group_key = config.group_key
                    group_members = [cfg for cfg in resolved_configs if cfg.group_key == group_key]
                    group_start = current_frame
                    group_end = group_start
                    group_has_keys = False

                    for member in group_members:
                        if member.joint in processed_joints:
                            continue

                        try:
                            result = apply_check_motion(
                                member.joint,
                                member.rotate_min,
                                member.rotate_max,
                                group_start,
                                interval,
                            )
                        except ValueError as exc:
                            errors.append(str(exc))
                            continue

                        results.append(result)
                        processed_joints.add(member.joint)
                        if result.has_keys:
                            group_has_keys = True
                            group_end = max(group_end, result.end_frame)

                        mirror_joint = (
                            self._find_mirror_joint(member.joint, search_root)
                            if mirror_enabled
                            else None
                        )
                        if mirror_joint and mirror_joint not in processed_joints:
                            mirror_min = _mirror_axis_values(member.rotate_min)
                            mirror_max = _mirror_axis_values(member.rotate_max)
                            try:
                                mirror_result = apply_check_motion(
                                    mirror_joint,
                                    mirror_min,
                                    mirror_max,
                                    group_start,
                                    interval,
                                )
                            except ValueError as exc:
                                errors.append(str(exc))
                            else:
                                results.append(mirror_result)
                                processed_joints.add(mirror_joint)
                                if mirror_result.has_keys:
                                    group_has_keys = True
                                    group_end = max(group_end, mirror_result.end_frame)

                    processed_groups.add(group_key)
                    if group_has_keys:
                        current_frame = group_end + interval
                    else:
                        current_frame = group_start + interval
                    index += 1
                    continue

                joint_start = current_frame
                try:
                    result = apply_check_motion(
                        config.joint,
                        config.rotate_min,
                        config.rotate_max,
                        joint_start,
                        interval,
                    )
                except ValueError as exc:
                    errors.append(str(exc))
                    index += 1
                    continue

                results.append(result)
                processed_joints.add(config.joint)
                next_start = result.end_frame + interval if result.has_keys else joint_start + interval

                mirror_joint = (
                    self._find_mirror_joint(config.joint, search_root)
                    if mirror_enabled
                    else None
                )
                if mirror_joint and mirror_joint not in processed_joints:
                    mirror_min = _mirror_axis_values(config.rotate_min)
                    mirror_max = _mirror_axis_values(config.rotate_max)
                    try:
                        mirror_result = apply_check_motion(
                            mirror_joint, mirror_min, mirror_max, next_start, interval
                        )
                    except ValueError as exc:
                        errors.append(str(exc))
                        current_frame = next_start
                    else:
                        results.append(mirror_result)
                        processed_joints.add(mirror_joint)
                        if mirror_result.has_keys:
                            current_frame = mirror_result.end_frame + interval
                        else:
                            current_frame = next_start + interval
                    index += 1
                    continue

                current_frame = next_start
                index += 1
        finally:
            cmds.undoInfo(closeChunk=True)

        if results:
            message = u"{} 件のジョイントにチェックモーションを作成しました。".format(len(results))
            cmds.inViewMessage(amg=message, pos="topCenter", fade=True)

        if errors:
            for error in errors:
                cmds.warning(error)

    # Single tab ----------------------------------------------------------
    @staticmethod
    def _get_joint_root(joint: str) -> Optional[str]:
        long_name = _to_long_name(joint)
        if not long_name:
            return None

        current = long_name
        while True:
            parent = cmds.listRelatives(current, parent=True, type="joint", fullPath=True)
            if not parent:
                return current
            current = parent[0]

    def _on_get_single_joint(self):
        selection = cmds.ls(selection=True, type="joint") or []
        if not selection:
            cmds.warning(u"ジョイントを選択してください。")
            return

        joint = selection[0]
        self.single_joint_edit.setText(joint)
        self._populate_single_from_joint(joint)

    def _populate_single_from_joint(self, joint: str):
        times: List[float] = []
        rotate_min: Dict[str, float] = {}
        rotate_max: Dict[str, float] = {}

        for axis in ROTATE_AXES:
            attr = f"{joint}.rotate{axis}"
            values = cmds.keyframe(attr, query=True, valueChange=True)
            if values:
                rotate_min[axis] = min(values)
                rotate_max[axis] = max(values)
            else:
                rotate_min[axis] = 0.0
                rotate_max[axis] = 0.0

            key_times = cmds.keyframe(attr, query=True, timeChange=True)
            if key_times:
                times.extend(key_times)

        if times:
            start = int(round(min(times)))
            self.single_start_spin.setValue(start)
        else:
            self.single_start_spin.setValue(0)

        self.single_axis_widget.set_values(rotate_min, rotate_max)

    def _on_apply_single_clicked(self):
        joint = self.single_joint_edit.text().strip()
        if not joint:
            cmds.warning(u"ジョイントが選択されていません。")
            return

        joint_long = _to_long_name(joint)
        if joint_long:
            joint = joint_long

        rotate_min, rotate_max = self.single_axis_widget.get_values()
        start_frame = float(self.single_start_spin.value())
        if start_frame == 0:
            start_frame = float(cmds.currentTime(query=True))
        interval = float(self.single_interval_spin.value())
        mirror_enabled = self.single_mirror_checkbox.isChecked()

        search_root = self._get_joint_root(joint)

        cmds.undoInfo(openChunk=True, chunkName="CreateCheckMotionSingle")
        try:
            result = apply_check_motion(joint, rotate_min, rotate_max, start_frame, interval)

            mirror_joint = (
                self._find_mirror_joint(joint, search_root) if mirror_enabled else None
            )
            if mirror_joint:
                mirror_min = _mirror_axis_values(rotate_min)
                mirror_max = _mirror_axis_values(rotate_max)
                mirror_start = result.end_frame + interval if result.has_keys else start_frame + interval
                apply_check_motion(
                    mirror_joint,
                    mirror_min,
                    mirror_max,
                    mirror_start,
                    interval,
                )
        except ValueError as exc:
            cmds.warning(str(exc))
        finally:
            cmds.undoInfo(closeChunk=True)

    @staticmethod
    def _find_mirror_joint(joint: str, search_root: Optional[str] = None) -> Optional[str]:
        long_name = _to_long_name(joint)
        if not long_name:
            return None

        short_name = long_name.split("|")[-1]
        if not _should_attempt_mirror(short_name):
            return None

        base_name, side = _split_side(short_name)
        if side == "C":
            return None

        mirror_side = "R" if side == "L" else "L"
        expected_short = f"{base_name}_{mirror_side}"

        if search_root and cmds.objExists(search_root):
            search_space = _list_descendant_joints(search_root)
        else:
            search_space = cmds.ls(type="joint", long=True) or []

        matches = [node for node in search_space if node.split("|")[-1] == expected_short]
        if matches:
            matches.sort(key=len)
            return matches[0]

        parent_path = "|".join(long_name.split("|")[:-1])
        if parent_path:
            candidate = parent_path + "|" + expected_short
        else:
            candidate = expected_short

        candidate_long = _to_long_name(candidate)
        if candidate_long:
            return candidate_long

        fallback = cmds.ls(f"*{expected_short}", type="joint", long=True) or []
        if fallback:
            fallback.sort(key=len)
            return fallback[0]
        return None


def show_dialog():
    return CheckMotionToolDialog.show_dialog()

