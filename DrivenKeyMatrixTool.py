# -*- coding: utf-8 -*-
"""Driven key matrix editor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

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


@dataclass
class DrivenKeyEntry:
    joint: str
    attribute: str
    anim_curve: str
    key_index: int
    input_value: float
    output_value: float


class DrivenKeyMatrixDialog(QtWidgets.QDialog):
    COLUMN_ATTRIBUTE = 0
    COLUMN_INPUT = 1
    COLUMN_OUTPUT = 2

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent or maya_main_window())

        self.setWindowTitle("Driven Key Matrix")
        self.setObjectName("drivenKeyMatrixDialog")
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)

        self._row_entries: List[DrivenKeyEntry] = []

        self._create_widgets()
        self._create_layout()
        self._create_connections()

        self.resize(520, 420)

    # ------------------------------------------------------------------
    # UI setup
    def _create_widgets(self) -> None:
        self.refresh_button = QtWidgets.QPushButton("Refresh From Selection")
        self.refresh_button.setToolTip("選択中のジョイントに設定されたドリブンキーを一覧表示します。")

        self.table_widget = QtWidgets.QTableWidget(0, 3)
        self.table_widget.setAlternatingRowColors(True)
        self.table_widget.setHorizontalHeaderLabels(["Attr", "Input", "Output"])
        self.table_widget.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.Stretch
        )
        self.table_widget.verticalHeader().setMinimumWidth(140)
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
        button_layout.addStretch(1)
        button_layout.addWidget(self.close_button)

        main_layout.addLayout(button_layout)
        main_layout.addWidget(self.table_widget)
        main_layout.addWidget(self.info_label)

    def _create_connections(self) -> None:
        self.refresh_button.clicked.connect(self.refresh_from_selection)
        self.close_button.clicked.connect(self.close)
        self.table_widget.itemChanged.connect(self._on_item_changed)

    # ------------------------------------------------------------------
    # Data helpers
    def refresh_from_selection(self) -> None:
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
                self._set_joint_headers(start_row, len(entries), joint)

            if not self._row_entries:
                self.info_label.setText("選択したジョイントにドリブンキーは見つかりませんでした。")
        finally:
            self.table_widget.blockSignals(False)

    def _append_entries(self, entries: Sequence[DrivenKeyEntry]) -> None:
        current_rows = self.table_widget.rowCount()
        self.table_widget.setRowCount(current_rows + len(entries))

        for offset, entry in enumerate(entries):
            row = current_rows + offset
            self._row_entries.append(entry)

            attr_item = QtWidgets.QTableWidgetItem(self._attribute_short_name(entry.attribute))
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
        attributes = cmds.listAttr(joint, keyable=True) or []
        for attr in attributes:
            if not attr.lower().startswith(("translate", "rotate", "scale")):
                continue
            plug = f"{joint}.{attr}"
            anim_curves = cmds.listConnections(
                plug, source=True, destination=False, type="animCurve"
            ) or []
            for anim_curve in anim_curves:
                inputs = cmds.keyframe(anim_curve, query=True, floatChange=True) or []
                outputs = cmds.keyframe(anim_curve, query=True, valueChange=True) or []
                if len(inputs) != len(outputs):
                    continue

                for index, (input_value, output_value) in enumerate(zip(inputs, outputs)):
                    entries.append(
                        DrivenKeyEntry(
                            joint=joint,
                            attribute=attr,
                            anim_curve=anim_curve,
                            key_index=index,
                            input_value=float(input_value),
                            output_value=float(output_value),
                        )
                    )
        return entries

    def _attribute_short_name(self, attribute: str) -> str:
        attr_lower = attribute.lower()
        for prefix, short in ("translate", "t"), ("rotate", "r"), ("scale", "s"):
            if attr_lower.startswith(prefix):
                axis = attribute[len(prefix) :].upper()
                return f"{short}{axis}"
        return attribute

    # ------------------------------------------------------------------
    # Editing
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
        try:
            if column == self.COLUMN_INPUT:
                cmds.keyframe(
                    entry.anim_curve,
                    index=(entry.key_index, entry.key_index),
                    edit=True,
                    float=value,
                )
            else:
                cmds.keyframe(
                    entry.anim_curve,
                    index=(entry.key_index, entry.key_index),
                    edit=True,
                    valueChange=value,
                )
        except Exception as exc:  # pragma: no cover - Maya依存のため
            self.info_label.setText(f"キー更新中にエラー: {exc}")
            self._restore_item_value(row, column, entry)
            return

        self.refresh_from_selection()
        self.info_label.setText(f"{joint_label}.{attribute_label} のキーを更新しました。")

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
    def showEvent(self, event: QtGui.QShowEvent) -> None:  # type: ignore
        super().showEvent(event)
        if not self._row_entries:
            QtCore.QTimer.singleShot(0, self.refresh_from_selection)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore
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
