# -*- coding: utf-8 -*-

"""Utility dialog for creating check motions on joints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from PySide2 import QtCore, QtWidgets
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


def _is_non_zero(value: float) -> bool:
    return abs(value) > EPSILON


def _should_attempt_mirror(joint: str) -> bool:
    short_name = joint.split("|")[-1]
    lower = short_name.lower()
    return any(keyword.lower() in lower for keyword in MIRROR_KEYWORDS)


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

        self.add_row_button = QtWidgets.QPushButton(u"Add Row")
        self.remove_row_button = QtWidgets.QPushButton(u"Remove Selected")

        self.batch_start_spin = QtWidgets.QSpinBox()
        self.batch_start_spin.setRange(-99999, 999999)
        self.batch_start_spin.setValue(0)
        self.batch_interval_spin = QtWidgets.QSpinBox()
        self.batch_interval_spin.setRange(1, 1000)
        self.batch_interval_spin.setValue(5)

        self.apply_batch_button = QtWidgets.QPushButton(u"Create Check Motion")

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

        self.apply_single_button = QtWidgets.QPushButton(u"Create")

    def _create_layout(self):
        batch_tab = QtWidgets.QWidget()
        batch_layout = QtWidgets.QVBoxLayout(batch_tab)
        root_layout = QtWidgets.QHBoxLayout()
        root_layout.addWidget(QtWidgets.QLabel(u"Search Root:"))
        root_layout.addWidget(self.batch_root_edit)
        root_layout.addWidget(self.batch_root_button)
        batch_layout.addLayout(root_layout)
        batch_layout.addWidget(self.batch_table)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addWidget(self.add_row_button)
        button_layout.addWidget(self.remove_row_button)
        button_layout.addStretch(1)
        batch_layout.addLayout(button_layout)

        settings_layout = QtWidgets.QFormLayout()
        settings_layout.addRow(u"Start Frame:", self.batch_start_spin)
        settings_layout.addRow(u"Interval:", self.batch_interval_spin)
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
        default_joints = [
            "Spine",
            "Clavicle_L",
            "Upperarm_L",
            "Forearm_L",
            "Hand_L",
            "Thumb_L",
            "Index_L",
            "Middle_L",
            "Ring_L",
            "Pinky_L",
            "Thigh_L",
            "Calf_L",
            "Foot_L",
            "Toe_L",
            "Neck",
        ]

        for joint in default_joints:
            self._add_row(joint)

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

    def _on_add_row(self):
        self._add_row()

    def _on_remove_selected_rows(self):
        selected_rows = sorted({index.row() for index in self.batch_table.selectionModel().selectedRows()}, reverse=True)
        for row in selected_rows:
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
            partial_matches.sort(key=len)
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

        results: List[CheckMotionResult] = []
        errors: List[str] = []
        processed: Set[str] = set()

        cmds.undoInfo(openChunk=True, chunkName="CreateCheckMotionBatch")
        try:
            current_frame = start_frame
            for entry, rotate_min, rotate_max in configs:
                joint = self._resolve_joint_entry(entry, search_root)
                if not joint:
                    errors.append(u"ジョイント '{0}' が見つかりません。".format(entry))
                    continue

                if joint in processed:
                    continue

                joint_start = current_frame
                try:
                    result = apply_check_motion(joint, rotate_min, rotate_max, joint_start, interval)
                except ValueError as exc:
                    errors.append(str(exc))
                    continue

                results.append(result)
                processed.add(joint)
                next_start = result.end_frame + interval if result.has_keys else joint_start + interval

                mirror_joint = self._find_mirror_joint(joint, search_root)
                if mirror_joint and mirror_joint not in processed:
                    mirror_min = _mirror_axis_values(rotate_min)
                    mirror_max = _mirror_axis_values(rotate_max)
                    try:
                        mirror_result = apply_check_motion(
                            mirror_joint, mirror_min, mirror_max, next_start, interval
                        )
                    except ValueError as exc:
                        errors.append(str(exc))
                        current_frame = next_start
                    else:
                        results.append(mirror_result)
                        processed.add(mirror_joint)
                        if mirror_result.has_keys:
                            current_frame = mirror_result.end_frame + interval
                        else:
                            current_frame = next_start + interval
                    continue

                current_frame = next_start
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

        search_root = self._get_joint_root(joint)

        cmds.undoInfo(openChunk=True, chunkName="CreateCheckMotionSingle")
        try:
            result = apply_check_motion(joint, rotate_min, rotate_max, start_frame, interval)

            mirror_joint = self._find_mirror_joint(joint, search_root)
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

