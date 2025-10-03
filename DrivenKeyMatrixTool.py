# -*- coding: utf-8 -*-
"""Driven key matrix editor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from PySide2 import QtCore, QtGui, QtWidgets
import maya.cmds as cmds


def maya_main_window() -> QtWidgets.QWidget:
    import maya.OpenMayaUI as omui  # type: ignore
    from shiboken2 import wrapInstance  # type: ignore

    ptr = omui.MQtUtil.mainWindow()
    if ptr is None:
        raise RuntimeError("Mayaのメインウィンドウが取得できませんでした。")
    return wrapInstance(int(ptr), QtWidgets.QWidget)


def _short_name(node: str) -> str:
    return node.split("|")[-1]


ANIM_CURVE_TYPES: Sequence[str] = (
    "animCurveUL",
    "animCurveUA",
    "animCurveUT",
    "animCurveUU",
)

TARGET_ATTRIBUTES: Sequence[str] = tuple(
    f"{prefix}{axis}"
    for prefix in ("translate", "rotate", "scale")
    for axis in ("X", "Y", "Z")
)

TARGET_ATTRIBUTE_MAP: Dict[str, str] = {
    attr.lower(): attr for attr in TARGET_ATTRIBUTES
}


@dataclass
class DrivenKeyEntry:
    joint: str
    attribute: str
    anim_curve: str
    key_index: int
    input_value: float
    output_value: float
    driver_attribute: str = ""
    driver_node: str = ""


class DrivenKeyMatrixDialog(QtWidgets.QDialog):
    COLUMN_DRIVER = 0
    COLUMN_ATTRIBUTE = 1
    COLUMN_INPUT = 2
    COLUMN_OUTPUT = 3

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent or maya_main_window())

        self.setWindowTitle("Driven Key Matrix")
        self.setObjectName("drivenKeyMatrixDialog")
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)

        self._row_entries: List[DrivenKeyEntry] = []
        self._preview_attr: Optional[str] = None
        self._preview_original_value: Optional[float] = None
        self._block_selection_preview = False

        self._create_widgets()
        self._create_layout()
        self._create_connections()

        self.resize(420, 380)

    # ------------------------------------------------------------------
    # UI setup
    def _create_widgets(self) -> None:
        self.refresh_button = QtWidgets.QPushButton("Refresh From Selection")
        self.refresh_button.setToolTip("選択中のジョイントに設定されたドリブンキーを一覧表示します。")

        self.add_input_label = QtWidgets.QLabel("Input:")
        self.add_input_spinbox = QtWidgets.QDoubleSpinBox()
        self.add_input_spinbox.setDecimals(3)
        self.add_input_spinbox.setRange(-1000000.0, 1000000.0)
        self.add_input_spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.add_key_button = QtWidgets.QPushButton("Add Key")
        self.add_key_button.setToolTip(
            "指定したInput値で選択中のアトリビュートに新しいキーを追加します。"
        )
        self.collect_button = QtWidgets.QPushButton("Collect")
        self.collect_button.setToolTip(
            "選択行のOutput値を、現在のジョイントのアトリビュート値で更新します。"
        )

        self.auto_mirror_checkbox = QtWidgets.QCheckBox("Mirror to opposite joints automatically")
        self.auto_mirror_checkbox.setToolTip(
            "オンの場合、値を変更した際にミラー側のジョイントにも自動で反映します。"
        )

        self.mirror_button = QtWidgets.QPushButton("Apply Mirror Updates")
        self.mirror_button.setToolTip(
            "選択した行(未選択の場合は全て)の値をミラー側のジョイントに反映します。"
        )

        self.table_widget = QtWidgets.QTableWidget(0, 4)
        self.table_widget.setAlternatingRowColors(True)
        self.table_widget.setHorizontalHeaderLabels(["Driver", "Attr", "Input", "Output"])
        header = self.table_widget.horizontalHeader()
        header.setSectionResizeMode(self.COLUMN_DRIVER, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COLUMN_ATTRIBUTE, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COLUMN_INPUT, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(self.COLUMN_OUTPUT, QtWidgets.QHeaderView.Stretch)
        header.setStretchLastSection(False)
        self.table_widget.verticalHeader().setMinimumWidth(110)
        self.table_widget.verticalHeader().setDefaultAlignment(
            QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft
        )
        self.table_widget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table_widget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table_widget.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked)

        self.info_label = QtWidgets.QLabel("")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color: #ff9933;")

        self.close_button = QtWidgets.QPushButton("Close")

    def _create_layout(self) -> None:
        main_layout = QtWidgets.QVBoxLayout(self)
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addWidget(self.refresh_button)
        button_layout.addWidget(self.add_input_label)
        button_layout.addWidget(self.add_input_spinbox)
        button_layout.addWidget(self.add_key_button)
        button_layout.addWidget(self.collect_button)
        button_layout.addWidget(self.auto_mirror_checkbox)
        button_layout.addStretch(1)
        button_layout.addWidget(self.mirror_button)
        button_layout.addWidget(self.close_button)

        main_layout.addLayout(button_layout)
        main_layout.addWidget(self.table_widget)
        main_layout.addWidget(self.info_label)

    def _create_connections(self) -> None:
        self.refresh_button.clicked.connect(self.refresh_from_selection)
        self.add_key_button.clicked.connect(self.add_key_for_selection)
        self.collect_button.clicked.connect(self.collect_output_for_selection)
        self.close_button.clicked.connect(self.close)
        self.mirror_button.clicked.connect(self.apply_mirror_from_selection)
        self.table_widget.itemChanged.connect(self._on_item_changed)
        selection_model = self.table_widget.selectionModel()
        if selection_model is not None:
            selection_model.selectionChanged.connect(self._on_selection_changed)

    # ------------------------------------------------------------------
    # Data helpers
    def _mirror_node_name(self, name: str) -> Optional[str]:
        mirrored = self._mirror_path(name)
        if mirrored:
            return mirrored
        short_mirror = self._mirror_simple_name(_short_name(name))
        if short_mirror and "|" in name:
            parts = name.split("|")
            if parts:
                parts[-1] = short_mirror
                candidate = "|".join(parts)
                if candidate != name:
                    return candidate
        return short_mirror

    def _mirror_joint_name(self, joint: str) -> Optional[str]:
        return self._mirror_node_name(joint)

    def _mirror_attribute_plug(self, plug: str) -> Optional[str]:
        if "." not in plug:
            return None
        node, attr = plug.rsplit(".", 1)
        mirror_node = self._mirror_node_name(node)
        if not mirror_node:
            return None
        mirror_plug = f"{mirror_node}.{attr}"
        if not cmds.objExists(mirror_node) or not cmds.objExists(mirror_plug):
            return None
        return mirror_plug

    def _should_negate_attribute(self, attribute: str) -> bool:
        if not attribute:
            return False
        attr_name = attribute.split(".")[-1]
        return attr_name.lower().endswith("y")

    def _duplicate_anim_curve_for_mirror(
        self, entry: DrivenKeyEntry, mirror_joint: str
    ) -> Optional[str]:
        target_attr = f"{mirror_joint}.{entry.attribute}"
        if not cmds.objExists(target_attr):
            return None

        try:
            duplicated = cmds.duplicate(entry.anim_curve, rc=True)[0]
        except RuntimeError:
            try:
                duplicated = cmds.duplicate(entry.anim_curve)[0]
            except RuntimeError:
                return None

        try:
            cmds.connectAttr(f"{duplicated}.output", target_attr, f=True)
        except RuntimeError:
            try:
                cmds.delete(duplicated)
            except RuntimeError:
                pass
            return None

        driver_plugs = cmds.listConnections(
            f"{entry.anim_curve}.input", s=True, d=False, p=True, scn=True
        ) or []

        connected_driver = False
        for plug in driver_plugs:
            mirror_plug = self._mirror_attribute_plug(plug)
            if not mirror_plug:
                continue
            try:
                cmds.connectAttr(mirror_plug, f"{duplicated}.input", f=True)
                connected_driver = True
                break
            except RuntimeError:
                continue

        if not connected_driver:
            for plug in driver_plugs:
                if not cmds.objExists(plug):
                    continue
                try:
                    cmds.connectAttr(plug, f"{duplicated}.input", f=True)
                    connected_driver = True
                    break
                except RuntimeError:
                    continue

        if not connected_driver:
            try:
                cmds.delete(duplicated)
            except RuntimeError:
                pass
            return None

        if self._should_negate_attribute(entry.attribute):
            try:
                cmds.scaleKey(mirror_joint, attribute=entry.attribute, valueScale=-1)
            except Exception:
                pass

        return duplicated

    def _mirror_simple_name(self, name: str) -> Optional[str]:
        if "_L" in name:
            return name.replace("_L", "_R", 1)
        if "_R" in name:
            return name.replace("_R", "_L", 1)
        return None

    def _mirror_path(self, path: str) -> Optional[str]:
        parts = [part for part in path.split("|") if part]
        mirrored_parts: List[str] = []
        changed = False
        for part in parts:
            mirrored = self._mirror_simple_name(part)
            if mirrored:
                mirrored_parts.append(mirrored)
                changed = True
            else:
                mirrored_parts.append(part)
        if not changed:
            return None
        prefix = "|" if path.startswith("|") else ""
        return prefix + "|".join(mirrored_parts)

    def _find_mirror_entry(self, entry: DrivenKeyEntry) -> Optional[DrivenKeyEntry]:
        mirror_joint = self._mirror_joint_name(entry.joint)
        if not mirror_joint:
            return None

        mirror_long = cmds.ls(mirror_joint, l=True) or [mirror_joint]
        mirror_name = mirror_long[0]

        for candidate in self._row_entries:
            candidate_long = cmds.ls(candidate.joint, l=True) or [candidate.joint]
            if candidate_long[0] != mirror_name:
                continue
            if candidate.attribute != entry.attribute:
                continue
            if abs(candidate.input_value - entry.input_value) > 1e-5:
                continue
            return candidate

        if not cmds.objExists(mirror_name):
            return None

        mirror_entries = self._build_entries_for_joint(mirror_name)
        if not mirror_entries:
            duplicated = self._duplicate_anim_curve_for_mirror(entry, mirror_name)
            if duplicated:
                mirror_entries = self._build_entries_for_joint(mirror_name)
        for candidate in mirror_entries:
            if candidate.attribute != entry.attribute:
                continue
            if abs(candidate.input_value - entry.input_value) > 1e-5:
                continue
            return candidate
        return None

    def _mirror_axis_multiplier(self, attribute: str) -> float:
        """Return the multiplier to apply when mirroring a value for *attribute*."""

        attr_lower = attribute.lower()
        if attr_lower.endswith("y"):
            return -1.0
        return 1.0

    def _mirror_value_for_column(
        self, entry: DrivenKeyEntry, column: int, value: float
    ) -> float:
        """Adjust *value* when sending to the mirrored entry for the given column."""

        if column == self.COLUMN_OUTPUT:
            return value * self._mirror_axis_multiplier(entry.attribute)
        if column == self.COLUMN_INPUT and entry.driver_attribute:
            return value * self._mirror_axis_multiplier(entry.driver_attribute)
        return value

    def _update_mirror_entry(
        self, entry: DrivenKeyEntry, values: Dict[int, float]
    ) -> bool:
        mirror_entry = self._find_mirror_entry(entry)
        if not mirror_entry:
            return False

        try:
            if self.COLUMN_INPUT in values:
                mirrored_input = self._mirror_value_for_column(
                    mirror_entry, self.COLUMN_INPUT, values[self.COLUMN_INPUT]
                )
                cmds.keyframe(
                    mirror_entry.anim_curve,
                    index=(mirror_entry.key_index, mirror_entry.key_index),
                    edit=True,
                    float=(mirrored_input,),
                )
                mirror_entry.input_value = mirrored_input
            if self.COLUMN_OUTPUT in values:
                mirrored_output = self._mirror_value_for_column(
                    mirror_entry, self.COLUMN_OUTPUT, values[self.COLUMN_OUTPUT]
                )
                cmds.keyframe(
                    mirror_entry.anim_curve,
                    index=(mirror_entry.key_index, mirror_entry.key_index),
                    edit=True,
                    valueChange=mirrored_output,
                )
                mirror_entry.output_value = mirrored_output
        except Exception as exc:  # pragma: no cover - Maya依存のため
            self.info_label.setText(f"ミラー更新中にエラー: {exc}")
            return False

        return True

    def refresh_from_selection(self) -> None:
        self._restore_input_preview()
        self._block_selection_preview = True
        self.table_widget.blockSignals(True)
        try:
            self._row_entries = []
            self.table_widget.setRowCount(0)
            self.info_label.clear()

            joints = cmds.ls(selection=True, type="joint") or []
            if not joints:
                self.info_label.setText("ジョイントを選択してからRefreshしてください。")
                return

            for joint in joints:
                entries = self._build_entries_for_joint(joint)
                if not entries:
                    continue

                start_row = self.table_widget.rowCount()
                self._append_entries(entries)
                self._set_joint_headers(start_row, len(entries), entries[0].joint)

            if not self._row_entries:
                self.info_label.setText("選択したジョイントにドリブンキーは見つかりませんでした。")
        finally:
            self.table_widget.blockSignals(False)
            self._block_selection_preview = False

    def _append_entries(self, entries: Sequence[DrivenKeyEntry]) -> None:
        current_rows = self.table_widget.rowCount()
        self.table_widget.setRowCount(current_rows + len(entries))

        for offset, entry in enumerate(entries):
            row = current_rows + offset
            self._row_entries.append(entry)

            previous_entry = self._row_entries[row - 1] if row > 0 else None

            driver_text = self._driver_display_text(entry)
            if self._is_same_driver_group(entry, previous_entry):
                driver_text = ""
            driver_item = QtWidgets.QTableWidgetItem(driver_text)
            driver_item.setFlags(driver_item.flags() & ~QtCore.Qt.ItemIsEditable)
            driver_tooltip = self._driver_tooltip(entry)
            if driver_tooltip:
                driver_item.setToolTip(driver_tooltip)
            self.table_widget.setItem(row, self.COLUMN_DRIVER, driver_item)

            attr_text = self._attribute_short_name(entry.attribute)
            if self._is_same_attribute_group(entry, previous_entry):
                attr_text = ""
            attr_item = QtWidgets.QTableWidgetItem(attr_text)
            attr_item.setFlags(attr_item.flags() & ~QtCore.Qt.ItemIsEditable)
            attr_item.setToolTip(entry.attribute)
            self.table_widget.setItem(row, self.COLUMN_ATTRIBUTE, attr_item)

            input_item = QtWidgets.QTableWidgetItem()
            input_item.setData(QtCore.Qt.EditRole, entry.input_value)
            input_item.setToolTip(
                "入力値(ドライバー値)。ダブルクリックして編集できます。"
            )
            self.table_widget.setItem(row, self.COLUMN_INPUT, input_item)

            output_item = QtWidgets.QTableWidgetItem()
            output_item.setData(QtCore.Qt.EditRole, entry.output_value)
            output_item.setToolTip(
                "出力値(ターゲット値)。ダブルクリックして編集できます。"
            )
            self.table_widget.setItem(row, self.COLUMN_OUTPUT, output_item)

    def _set_joint_headers(self, start_row: int, row_count: int, joint: str) -> None:
        short = _short_name(joint)
        for index in range(row_count):
            row = start_row + index
            header = QtWidgets.QTableWidgetItem(short if index == 0 else "")
            header.setToolTip(joint)
            self.table_widget.setVerticalHeaderItem(row, header)

    def _build_entries_for_joint(self, joint: str) -> List[DrivenKeyEntry]:
        entries: List[DrivenKeyEntry] = []
        joint_long = cmds.ls(joint, l=True) or [joint]
        joint_name = joint_long[0]
        anim_curves: List[str] = []
        for curve_type in ANIM_CURVE_TYPES:
            anim_curves.extend(
                cmds.listConnections(joint_name, type=curve_type, s=True, d=False) or []
            )
        seen_curves = set()
        for anim_curve in anim_curves:
            if anim_curve in seen_curves:
                continue
            seen_curves.add(anim_curve)
            inputs = cmds.keyframe(anim_curve, query=True, floatChange=True) or []
            outputs = cmds.keyframe(anim_curve, query=True, valueChange=True) or []
            if len(inputs) != len(outputs):
                continue

            attribute = self._anim_curve_attribute(joint_name, anim_curve)
            driver_node, driver_attribute = self._anim_curve_driver_info(anim_curve)
            for index, (input_value, output_value) in enumerate(zip(inputs, outputs)):
                entries.append(
                    DrivenKeyEntry(
                        joint=joint_name,
                        attribute=attribute,
                        anim_curve=anim_curve,
                        key_index=index,
                        input_value=float(input_value),
                        output_value=float(output_value),
                        driver_attribute=driver_attribute,
                        driver_node=driver_node,
                    )
                )
        return entries

    def _anim_curve_attribute(self, joint: str, anim_curve: str) -> str:
        outputs = cmds.listConnections(
            f"{anim_curve}.output", plugs=True, s=False, d=True
        ) or []
        joint_long = cmds.ls(joint, l=True) or [joint]
        joint_long_name = joint_long[0]
        joint_short = _short_name(joint_long_name)
        fallback_attr = ""
        for plug in outputs:
            if "." not in plug:
                continue
            node, attr = plug.split(".", 1)
            node_long = cmds.ls(node, l=True) or [node]
            node_long_name = node_long[0]
            node_short = _short_name(node_long_name)
            if node_long_name == joint_long_name or node_short == joint_short:
                return attr
            if not fallback_attr:
                fallback_attr = attr

        name_attr = self._attribute_from_curve_name(anim_curve)
        if name_attr:
            return name_attr
        if fallback_attr:
            return fallback_attr
        return _short_name(anim_curve)

    def _anim_curve_driver_info(self, anim_curve: str) -> Tuple[str, str]:
        inputs = cmds.listConnections(
            f"{anim_curve}.input", plugs=True, s=True, d=False
        ) or []
        for plug in inputs:
            if "." not in plug:
                continue
            node, attr = plug.split(".", 1)
            node_long = cmds.ls(node, l=True) or [node]
            return node_long[0], attr
        return "", ""

    def _attribute_from_curve_name(self, anim_curve: str) -> str:
        short_name = _short_name(anim_curve)
        parts = short_name.split("_")
        for part in reversed(parts):
            key = part.lower()
            if key in TARGET_ATTRIBUTE_MAP:
                return TARGET_ATTRIBUTE_MAP[key]
        return ""

    def _attribute_short_name(self, attribute: str) -> str:
        attr_lower = attribute.lower()
        for prefix, short in ("translate", "t"), ("rotate", "r"), ("scale", "s"):
            if attr_lower.startswith(prefix):
                axis = attribute[len(prefix) :].upper()
                return f"{short}{axis}"
        return attribute

    def _driver_display_text(self, entry: DrivenKeyEntry) -> str:
        if entry.driver_node and entry.driver_attribute:
            return f"{_short_name(entry.driver_node)}.{entry.driver_attribute}"
        if entry.driver_node:
            return _short_name(entry.driver_node)
        return entry.driver_attribute

    def _driver_tooltip(self, entry: DrivenKeyEntry) -> str:
        if entry.driver_node and entry.driver_attribute:
            return f"{entry.driver_node}.{entry.driver_attribute}"
        if entry.driver_attribute:
            return entry.driver_attribute
        return entry.driver_node

    def _is_same_driver_group(
        self, entry: DrivenKeyEntry, previous: Optional[DrivenKeyEntry]
    ) -> bool:
        if previous is None:
            return False
        return (
            previous.joint == entry.joint
            and previous.driver_node == entry.driver_node
            and previous.driver_attribute == entry.driver_attribute
        )

    def _is_same_attribute_group(
        self, entry: DrivenKeyEntry, previous: Optional[DrivenKeyEntry]
    ) -> bool:
        if previous is None:
            return False
        return previous.joint == entry.joint and previous.attribute == entry.attribute

    # ------------------------------------------------------------------
    # Editing
    def _driver_attribute_plug(self, entry: DrivenKeyEntry) -> Optional[str]:
        if entry.driver_node and entry.driver_attribute:
            return f"{entry.driver_node}.{entry.driver_attribute}"
        if entry.driver_attribute:
            return entry.driver_attribute
        return None

    def _restore_input_preview(self) -> None:
        if self._preview_attr is None:
            return
        if self._preview_original_value is None:
            self._preview_attr = None
            return
        try:
            cmds.setAttr(self._preview_attr, self._preview_original_value)
        except Exception:  # pragma: no cover - Maya依存のため
            pass
        finally:
            self._preview_attr = None
            self._preview_original_value = None

    def _apply_input_preview(self, entry: DrivenKeyEntry) -> None:
        attr_plug = self._driver_attribute_plug(entry)
        if not attr_plug:
            return
        try:
            current_value = cmds.getAttr(attr_plug)
        except Exception:  # pragma: no cover - Maya依存のため
            return

        try:
            cmds.setAttr(attr_plug, entry.input_value)
        except Exception:  # pragma: no cover - Maya依存のため
            return

        self._preview_attr = attr_plug
        self._preview_original_value = current_value

    def _on_selection_changed(
        self,
        selected: QtCore.QItemSelection,
        deselected: QtCore.QItemSelection,
    ) -> None:
        if self._block_selection_preview:
            return
        self._restore_input_preview()
        selection_model = self.table_widget.selectionModel()
        if selection_model is None:
            return
        rows = [index.row() for index in selection_model.selectedRows()]
        if not rows:
            return
        row = rows[-1]
        if not (0 <= row < len(self._row_entries)):
            return
        entry = self._row_entries[row]
        self._apply_input_preview(entry)

    def _on_item_changed(self, item: QtWidgets.QTableWidgetItem) -> None:
        column = item.column()
        if column not in (self.COLUMN_INPUT, self.COLUMN_OUTPUT):
            return

        row = item.row()
        if not (0 <= row < len(self._row_entries)):
            return

        entry = self._row_entries[row]
        text = item.text()
        try:
            value = float(text)
        except ValueError:
            self._restore_item_value(row, column, entry)
            self.info_label.setText("数値のみ入力できます。")
            return

        joint_label = _short_name(entry.joint)
        attribute_label = entry.attribute
        message: Optional[str] = None
        try:
            if column == self.COLUMN_INPUT:
                cmds.keyframe(
                    entry.anim_curve,
                    index=(entry.key_index, entry.key_index),
                    edit=True,
                    float=(value,),
                )
                entry.input_value = value
            else:
                cmds.keyframe(
                    entry.anim_curve,
                    index=(entry.key_index, entry.key_index),
                    edit=True,
                    valueChange=value,
                )
                entry.output_value = value
            if self.auto_mirror_checkbox.isChecked():
                mirrored = self._update_mirror_entry(entry, {column: value})
                if mirrored:
                    message = (
                        f"{joint_label}.{attribute_label} とミラー側のキーを更新しました。"
                    )
                else:
                    message = (
                        f"{joint_label}.{attribute_label} のキーを更新しました。(ミラーなし)"
                    )
        except Exception as exc:  # pragma: no cover - Maya依存のため
            self.info_label.setText(f"キー更新中にエラー: {exc}")
            self._restore_item_value(row, column, entry)
            return

        self.refresh_from_selection()
        if message is None:
            message = f"{joint_label}.{attribute_label} のキーを更新しました。"
        self.info_label.setText(message)

    def _restore_item_value(
        self, row: int, column: int, entry: DrivenKeyEntry
    ) -> None:
        self.table_widget.blockSignals(True)
        try:
            if column == self.COLUMN_INPUT:
                value = entry.input_value
            else:
                value = entry.output_value
            item = self.table_widget.item(row, column)
            if item is not None:
                item.setData(QtCore.Qt.EditRole, value)
        finally:
            self.table_widget.blockSignals(False)

    # ------------------------------------------------------------------
    def _find_entry_for_anim_curve(
        self, anim_curve: str, input_value: float
    ) -> Optional[DrivenKeyEntry]:
        for entry in self._row_entries:
            if entry.anim_curve != anim_curve:
                continue
            if abs(entry.input_value - input_value) > 1e-5:
                continue
            return entry
        return None

    def add_key_for_selection(self) -> None:
        if not self._row_entries:
            self.info_label.setText("キーを追加する前にRefreshしてください。")
            return

        selection_model = self.table_widget.selectionModel()
        if selection_model is None:
            self.info_label.setText("キー追加対象の行を選択してください。")
            return

        rows = {index.row() for index in selection_model.selectedRows()}
        if not rows:
            self.info_label.setText("キー追加対象の行を選択してください。")
            return

        input_value = self.add_input_spinbox.value()

        added_entries = []
        errors = []
        for row in sorted(rows):
            if not (0 <= row < len(self._row_entries)):
                continue
            entry = self._row_entries[row]
            try:
                output_value = float(cmds.getAttr(f"{entry.joint}.{entry.attribute}"))
            except Exception as exc:  # pragma: no cover - Maya依存のため
                errors.append(str(exc))
                continue

            try:
                cmds.setKeyframe(
                    entry.anim_curve,
                    float=input_value,
                    value=output_value,
                )
                added_entries.append((entry.anim_curve, input_value, output_value))
            except Exception as exc:  # pragma: no cover - Maya依存のため
                errors.append(str(exc))

        self.refresh_from_selection()

        mirror_updates = 0
        if self.auto_mirror_checkbox.isChecked():
            for anim_curve, new_input, new_output in added_entries:
                entry = self._find_entry_for_anim_curve(anim_curve, new_input)
                if not entry:
                    continue
                if self._update_mirror_entry(
                    entry,
                    {
                        self.COLUMN_INPUT: new_input,
                        self.COLUMN_OUTPUT: new_output,
                    },
                ):
                    mirror_updates += 1

        if added_entries:
            message = f"{len(added_entries)} 件のキーを追加しました。"
            if mirror_updates:
                message += f" (ミラー {mirror_updates} 件)"
            self.info_label.setText(message)
        elif errors:
            self.info_label.setText(f"キー追加中にエラー: {errors[0]}")
        else:
            self.info_label.setText("キーを追加できませんでした。")

    def collect_output_for_selection(self) -> None:
        if not self._row_entries:
            self.info_label.setText("Collectする前にRefreshしてください。")
            return

        selection_model = self.table_widget.selectionModel()
        if selection_model is None:
            self.info_label.setText("Collect対象の行を選択してください。")
            return

        rows = {index.row() for index in selection_model.selectedRows()}
        if not rows:
            self.info_label.setText("Collect対象の行を選択してください。")
            return

        collected = 0
        errors: List[str] = []
        for row in sorted(rows):
            if not (0 <= row < len(self._row_entries)):
                continue
            entry = self._row_entries[row]
            attr_plug = f"{entry.joint}.{entry.attribute}"
            try:
                current_value = float(cmds.getAttr(attr_plug))
            except Exception as exc:  # pragma: no cover - Maya依存のため
                errors.append(str(exc))
                continue

            try:
                cmds.keyframe(
                    entry.anim_curve,
                    index=(entry.key_index, entry.key_index),
                    edit=True,
                    valueChange=current_value,
                )
            except Exception as exc:  # pragma: no cover - Maya依存のため
                errors.append(str(exc))
                continue

            entry.output_value = current_value
            collected += 1
            if self.auto_mirror_checkbox.isChecked():
                self._update_mirror_entry(
                    entry, {self.COLUMN_OUTPUT: current_value}
                )

        self.refresh_from_selection()

        if collected:
            self.info_label.setText(f"{collected} 行のOutputを現在値で更新しました。")
        elif errors:
            self.info_label.setText(f"Collect中にエラー: {errors[0]}")
        else:
            self.info_label.setText("Outputを更新できませんでした。")

    # ------------------------------------------------------------------
    def apply_mirror_from_selection(self) -> None:
        if not self._row_entries:
            self.info_label.setText("ミラー更新対象がありません。")
            return

        rows = {index.row() for index in self.table_widget.selectionModel().selectedRows()}
        if not rows:
            rows = set(range(len(self._row_entries)))

        updated = 0
        for row in sorted(rows):
            if not (0 <= row < len(self._row_entries)):
                continue
            entry = self._row_entries[row]
            values = {
                self.COLUMN_INPUT: entry.input_value,
                self.COLUMN_OUTPUT: entry.output_value,
            }
            if self._update_mirror_entry(entry, values):
                updated += 1

        self.refresh_from_selection()

        if updated:
            self.info_label.setText(f"{updated} 件のミラーキーを更新しました。")
        else:
            self.info_label.setText("ミラー先のジョイントが見つかりませんでした。")

    # ------------------------------------------------------------------
    def showEvent(self, event: QtGui.QShowEvent) -> None:  # type: ignore
        super().showEvent(event)
        if not self._row_entries:
            QtCore.QTimer.singleShot(0, self.refresh_from_selection)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore
        self._restore_input_preview()
        super().closeEvent(event)
        global _dialog
        if _dialog is self:
            _dialog = None


_dialog: Optional[DrivenKeyMatrixDialog] = None


def show_dialog() -> DrivenKeyMatrixDialog:
    global _dialog
    if _dialog is None:
        _dialog = DrivenKeyMatrixDialog()

    _dialog.refresh_from_selection()
    _dialog.show()
    _dialog.raise_()
    _dialog.activateWindow()
    return _dialog


def close_dialog() -> None:
    global _dialog
    if _dialog is not None:
        _dialog.close()
        _dialog = None
