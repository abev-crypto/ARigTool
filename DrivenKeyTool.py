# -*- coding: utf-8 -*-

from typing import Dict, List, Optional

from PySide2 import QtCore, QtWidgets
import maya.cmds as cmds
import maya.mel as mel


def maya_main_window():
    import maya.OpenMayaUI as omui
    from shiboken2 import wrapInstance

    ptr = omui.MQtUtil.mainWindow()
    if ptr is None:
        raise RuntimeError("Mayaのメインウィンドウが取得できませんでした。")
    return wrapInstance(int(ptr), QtWidgets.QWidget)


def _short_name(node: str) -> str:
    return node.split("|")[-1]


class DrivenKeyToolDialog(QtWidgets.QDialog):
    MODE_TWIST = "twist"
    MODE_HALF = "half"
    MODE_SUPPORT = "support"
    MODE_MANUAL = "manual"

    def __init__(self, parent=None):
        super(DrivenKeyToolDialog, self).__init__(parent or maya_main_window())

        self.setWindowTitle(u"Driven Key Helper")
        self.setObjectName("drivenKeyToolDialog")
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)

        self._target_items: List[str] = []
        self._current_source: str = ""
        self._manual_source: str = ""
        self._manual_targets: List[str] = []

        self._create_widgets()
        self._create_layout()
        self._create_connections()
        self._update_targets()

    def _create_widgets(self):
        self._target_attr_list = [
            f"{prefix}{axis}"
            for prefix in ("translate", "rotate", "scale")
            for axis in ("X", "Y", "Z")
        ]

        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItem("Twist", self.MODE_TWIST)
        self.mode_combo.addItem("Half", self.MODE_HALF)
        self.mode_combo.addItem("Support", self.MODE_SUPPORT)
        self.mode_combo.addItem("Manual", self.MODE_MANUAL)

        self.source_axis_combo = QtWidgets.QComboBox()
        self.source_axis_combo.addItems(["X", "Y", "Z"])

        self.targets_list = QtWidgets.QListWidget()
        self.targets_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.targets_list.setFocusPolicy(QtCore.Qt.NoFocus)

        self.refresh_button = QtWidgets.QPushButton(u"Refresh Targets")

        self.target_groups: Dict[str, Dict[str, QtWidgets.QCheckBox]] = {}
        self._create_target_checkboxes()

        self.manual_group = QtWidgets.QGroupBox(u"Manual Selection")
        manual_layout = QtWidgets.QGridLayout(self.manual_group)
        self.manual_source_display = QtWidgets.QLineEdit()
        self.manual_source_display.setReadOnly(True)
        self.manual_source_display.setPlaceholderText(u"No source selected")
        self.get_source_button = QtWidgets.QPushButton(u"Get Source")
        manual_layout.addWidget(QtWidgets.QLabel(u"Source:"), 0, 0)
        manual_layout.addWidget(self.manual_source_display, 0, 1)
        manual_layout.addWidget(self.get_source_button, 0, 2)

        self.manual_targets_display = QtWidgets.QLineEdit()
        self.manual_targets_display.setReadOnly(True)
        self.manual_targets_display.setPlaceholderText(u"No targets selected")
        self.get_targets_button = QtWidgets.QPushButton(u"Get Targets")
        manual_layout.addWidget(QtWidgets.QLabel(u"Targets:"), 1, 0)
        manual_layout.addWidget(self.manual_targets_display, 1, 1)
        manual_layout.addWidget(self.get_targets_button, 1, 2)
        self.manual_group.setVisible(False)

        self.driver_value_spin = QtWidgets.QDoubleSpinBox()
        self.driver_value_spin.setDecimals(4)
        self.driver_value_spin.setRange(-1_000_000.0, 1_000_000.0)

        self.target_value_group = QtWidgets.QGroupBox(u"Default Target Values")
        self.target_value_layout = QtWidgets.QGridLayout(self.target_value_group)
        self.target_value_inputs: Dict[str, QtWidgets.QDoubleSpinBox] = {}
        self.target_value_labels: Dict[str, QtWidgets.QLabel] = {}
        for row, attr in enumerate(self._target_attr_list):
            label = QtWidgets.QLabel(attr)
            spin = QtWidgets.QDoubleSpinBox()
            spin.setDecimals(4)
            spin.setRange(-1_000_000.0, 1_000_000.0)
            self.target_value_layout.addWidget(label, row, 0)
            self.target_value_layout.addWidget(spin, row, 1)
            self.target_value_inputs[attr] = spin
            self.target_value_labels[attr] = label

        self.individual_values_group = QtWidgets.QGroupBox(u"Individual Target Values")
        self.individual_values_group.setCheckable(True)
        self.individual_values_group.setChecked(False)
        individual_group_layout = QtWidgets.QVBoxLayout(self.individual_values_group)
        self.individual_scroll_area = QtWidgets.QScrollArea()
        self.individual_scroll_area.setWidgetResizable(True)
        individual_group_layout.addWidget(self.individual_scroll_area)
        self.individual_values_widget = QtWidgets.QWidget()
        self.individual_scroll_area.setWidget(self.individual_values_widget)
        self.individual_values_layout = QtWidgets.QVBoxLayout(self.individual_values_widget)
        self.individual_value_inputs: Dict[str, Dict[str, QtWidgets.QDoubleSpinBox]] = {}
        self.individual_value_labels: Dict[str, Dict[str, QtWidgets.QLabel]] = {}

        self.set_key_button = QtWidgets.QPushButton(u"Set Driven Key")
        self.edit_curve_button = QtWidgets.QPushButton(u"Edit Curves")
        self.close_button = QtWidgets.QPushButton(u"Close")

    def _create_target_checkboxes(self):
        attrs = {
            "translate": ("X", "Y", "Z"),
            "rotate": ("X", "Y", "Z"),
            "scale": ("X", "Y", "Z"),
        }
        color_map = {
            "X": "#ff7a7a",
            "Y": "#7aff7a",
            "Z": "#7aa7ff",
        }
        group_box = QtWidgets.QGroupBox()
        layout = QtWidgets.QHBoxLayout(group_box)
        layout.setSpacing(6)
        layout.setContentsMargins(6, 6, 6, 6)
        for prefix, axes in attrs.items():
            self.target_groups[prefix] = {}
            for axis in axes:
                cb = QtWidgets.QCheckBox("")
                cb.setFixedSize(22, 22)
                cb.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
                color = color_map.get(axis, "#cccccc")
                cb.setStyleSheet(
                    "QCheckBox{spacing:0px;}"
                    "QCheckBox::indicator{width:16px;height:16px;border-radius:3px;"
                    "background-color:%s;border:1px solid #333;}"
                    "QCheckBox::indicator:checked{border:2px solid #111;}"
                    % color
                )
                if prefix == "rotate" and axis == "X":
                    cb.setChecked(True)
                layout.addWidget(cb)
                self.target_groups[prefix][axis] = cb
                cb.stateChanged.connect(self._update_attribute_visibility)
        setattr(self, f"trsc_group", group_box)

    def _create_layout(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        mode_layout = QtWidgets.QHBoxLayout()
        mode_layout.addWidget(QtWidgets.QLabel(u"Mode:"))
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addStretch(1)
        mode_layout.addWidget(QtWidgets.QLabel(u"Source Rotate Axis:"))
        mode_layout.addWidget(self.source_axis_combo)
        main_layout.addLayout(mode_layout)

        main_layout.addWidget(QtWidgets.QLabel(u"Targets:"))
        main_layout.addWidget(self.targets_list)
        main_layout.addWidget(self.refresh_button)

        main_layout.addWidget(self.manual_group)

        main_layout.addWidget(self.trsc_group)

        value_layout = QtWidgets.QFormLayout()
        value_layout.addRow(QtWidgets.QLabel(u"Source Value:"), self.driver_value_spin)
        value_container = QtWidgets.QWidget()
        value_container.setLayout(value_layout)
        main_layout.addWidget(value_container)
        main_layout.addWidget(self.target_value_group)
        main_layout.addWidget(self.individual_values_group)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addWidget(self.set_key_button)
        button_layout.addWidget(self.edit_curve_button)
        button_layout.addStretch(1)
        button_layout.addWidget(self.close_button)
        main_layout.addLayout(button_layout)

    def _create_connections(self):
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.source_axis_combo.currentIndexChanged.connect(self._refresh_value_fields)
        self.refresh_button.clicked.connect(self._update_targets)
        self.set_key_button.clicked.connect(self._set_driven_key)
        self.edit_curve_button.clicked.connect(self._edit_curves)
        self.close_button.clicked.connect(self.close)
        self.get_source_button.clicked.connect(self._on_get_source_clicked)
        self.get_targets_button.clicked.connect(self._on_get_targets_clicked)

    # region Target search helpers
    def _selected_source_joint(self) -> str:
        sel = cmds.ls(sl=True, type="joint") or []
        if not sel:
            cmds.warning(u"ソースとなるジョイントを1つ選択してください。")
            return ""
        if len(sel) > 1:
            cmds.warning(u"最初の選択ジョイントのみをソースとして使用します。")
        return sel[0]

    def _active_source_joint(self) -> str:
        mode = self.mode_combo.currentData()
        if mode == self.MODE_MANUAL:
            if not self._manual_source:
                cmds.warning(u"マニュアルモードではソースを取得してください。")
                return ""
            return self._manual_source
        return self._selected_source_joint()

    def _list_siblings(self, node: str) -> List[str]:
        parent = cmds.listRelatives(node, parent=True, fullPath=True) or []
        if parent:
            siblings = cmds.listRelatives(parent[0], children=True, type="joint", fullPath=True) or []
        else:
            siblings = cmds.ls(assemblies=True, type="joint") or []
        return list(dict.fromkeys(siblings))

    def _collect_targets(self, source: str) -> List[str]:
        mode = self.mode_combo.currentData()
        candidates: List[str] = []
        if mode == self.MODE_TWIST:
            siblings = self._list_siblings(source)
            for j in siblings:
                if j == source:
                    continue
                if "twist" in _short_name(j).lower():
                    candidates.append(j)
        elif mode == self.MODE_HALF:
            siblings = self._list_siblings(source)
            half_joints = [j for j in siblings if "_Half" in _short_name(j)]
            for half in half_joints:
                descendants = cmds.listRelatives(half, ad=True, type="joint", fullPath=True) or []
                for j in descendants:
                    if "_Half_INF" in _short_name(j):
                        candidates.append(j)
        elif mode == self.MODE_SUPPORT:
            children = cmds.listRelatives(source, children=True, type="joint", fullPath=True) or []
            for child in children:
                if _short_name(child).endswith("_Sup"):
                    candidates.append(child)
        return list(dict.fromkeys(candidates))

    def _update_targets(self):
        mode = self.mode_combo.currentData()
        self.manual_group.setVisible(mode == self.MODE_MANUAL)
        if mode == self.MODE_MANUAL:
            self._apply_manual_selection()
            return

        source = self._selected_source_joint()
        if not source:
            self.targets_list.clear()
            self._target_items = []
            self._current_source = ""
            self._populate_value_inputs("", [])
            return

        targets = self._collect_targets(source)
        self.targets_list.clear()
        for j in targets:
            item = QtWidgets.QListWidgetItem(_short_name(j))
            item.setData(QtCore.Qt.UserRole, j)
            self.targets_list.addItem(item)
            item.setSelected(True)
        self._target_items = targets
        self._current_source = source
        self._populate_value_inputs(source, targets)

    # endregion

    def _apply_manual_selection(self):
        self.manual_group.setVisible(self.mode_combo.currentData() == self.MODE_MANUAL)
        source = self._manual_source
        targets = list(dict.fromkeys(self._manual_targets))
        self.targets_list.clear()
        for j in targets:
            item = QtWidgets.QListWidgetItem(_short_name(j))
            item.setData(QtCore.Qt.UserRole, j)
            self.targets_list.addItem(item)
            item.setSelected(True)
        self._target_items = targets
        self._current_source = source
        self._populate_value_inputs(source, targets)
        self._update_manual_display()

    def _selected_target_attributes(self) -> List[str]:
        attrs: List[str] = []
        for prefix, axes in self.target_groups.items():
            for axis, checkbox in axes.items():
                if checkbox.isChecked():
                    attrs.append(f"{prefix}{axis}")
        return attrs

    def _selected_targets(self) -> List[str]:
        items = self.targets_list.selectedItems()
        if not items:
            return []
        return [data for data in (item.data(QtCore.Qt.UserRole) for item in items) if data]

    def _driver_attribute(self, source: str) -> str:
        axis = self.source_axis_combo.currentText()
        return f"{source}.rotate{axis}"

    def _clear_layout(self, layout: QtWidgets.QLayout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            else:
                child_layout = item.layout()
                if child_layout:
                    self._clear_layout(child_layout)
                elif item.spacerItem():
                    # Spacer item, nothing to delete
                    continue

    def _populate_value_inputs(self, source: str, targets: List[str]):
        driver_attr = self._driver_attribute(source) if source else ""
        driver_value = 0.0
        if driver_attr and cmds.objExists(driver_attr):
            try:
                driver_value = cmds.getAttr(driver_attr)
            except Exception:
                driver_value = 0.0
            else:
                if isinstance(driver_value, (list, tuple)):
                    driver_value = driver_value[0]
        self.driver_value_spin.setValue(driver_value or 0.0)
        self.driver_value_spin.setEnabled(bool(driver_attr and cmds.objExists(driver_attr)))

        for attr, spin in self.target_value_inputs.items():
            value = 0.0
            for target in targets:
                plug = f"{target}.{attr}"
                if cmds.objExists(plug):
                    try:
                        value = cmds.getAttr(plug)
                    except Exception:
                        value = 0.0
                    else:
                        if isinstance(value, (list, tuple)):
                            value = value[0]
                        break
            spin.setValue(value or 0.0)
            spin.setEnabled(bool(targets))

        self._clear_layout(self.individual_values_layout)
        self.individual_value_inputs = {}
        self.individual_value_labels = {}
        for target in targets:
            group_box = QtWidgets.QGroupBox(_short_name(target))
            grid = QtWidgets.QGridLayout(group_box)
            attr_widgets: Dict[str, QtWidgets.QDoubleSpinBox] = {}
            attr_labels: Dict[str, QtWidgets.QLabel] = {}
            for row, attr in enumerate(self._target_attr_list):
                plug = f"{target}.{attr}"
                value = 0.0
                if cmds.objExists(plug):
                    try:
                        value = cmds.getAttr(plug)
                    except Exception:
                        value = 0.0
                    else:
                        if isinstance(value, (list, tuple)):
                            value = value[0]
                label = QtWidgets.QLabel(attr)
                spin = QtWidgets.QDoubleSpinBox()
                spin.setDecimals(4)
                spin.setRange(-1_000_000.0, 1_000_000.0)
                spin.setValue(value or 0.0)
                grid.addWidget(label, row, 0)
                grid.addWidget(spin, row, 1)
                attr_widgets[attr] = spin
                attr_labels[attr] = label
            self.individual_values_layout.addWidget(group_box)
            self.individual_value_inputs[target] = attr_widgets
            self.individual_value_labels[target] = attr_labels
        self.individual_values_layout.addStretch(1)
        has_targets = bool(targets)
        self.target_value_group.setEnabled(has_targets)
        self.individual_values_group.setEnabled(has_targets)
        self._apply_attribute_visibility()

    def _apply_attribute_visibility(self):
        selected_attrs = set(self._selected_target_attributes())
        for attr, label in self.target_value_labels.items():
            visible = attr in selected_attrs
            label.setVisible(visible)
            spin = self.target_value_inputs.get(attr)
            if spin is not None:
                spin.setVisible(visible)
        for target, attr_inputs in self.individual_value_inputs.items():
            labels = self.individual_value_labels.get(target, {})
            for attr, spin in attr_inputs.items():
                visible = attr in selected_attrs
                spin.setVisible(visible)
                label = labels.get(attr)
                if label is not None:
                    label.setVisible(visible)

    def _update_attribute_visibility(self):
        self._apply_attribute_visibility()

    def _target_value_for(self, target: str, attr: str) -> Optional[float]:
        if self.individual_values_group.isChecked():
            target_inputs = self.individual_value_inputs.get(target, {})
            widget = target_inputs.get(attr)
            if widget is not None:
                return widget.value()
        widget = self.target_value_inputs.get(attr)
        if widget is not None:
            return widget.value()
        return None

    def _refresh_value_fields(self):
        if not self._current_source:
            self._populate_value_inputs("", [])
            return
        self._populate_value_inputs(self._current_source, self._target_items)

    def _set_driven_key(self):
        source = self._active_source_joint()
        if not source:
            return

        self._current_source = source

        targets = self._selected_targets()
        if not targets:
            cmds.warning(u"ターゲットが選択されていません。リストから1つ以上選択してください。")
            return

        attrs = self._selected_target_attributes()
        if not attrs:
            cmds.warning(u"ターゲット属性を1つ以上選択してください。")
            return

        driver_attr = self._driver_attribute(source)
        if not cmds.objExists(driver_attr):
            cmds.warning(u"ソースジョイントに選択された軸が存在しません。")
            return

        driver_value = self.driver_value_spin.value()
        original_driver_value: Optional[float] = None
        try:
            original_driver_value = cmds.getAttr(driver_attr)
        except Exception:
            original_driver_value = None
        target_original_values: Dict[str, Optional[float]] = {}

        previous_selection = cmds.ls(sl=True)

        cmds.undoInfo(openChunk=True)
        try:
            try:
                cmds.select(source, r=True)
            except Exception:
                pass

            try:
                cmds.setAttr(driver_attr, lock=False)
            except Exception:
                pass
            try:
                cmds.setAttr(driver_attr, driver_value)
            except Exception:
                pass

            for target in targets:
                for attr in attrs:
                    plug = f"{target}.{attr}"
                    if not cmds.objExists(plug):
                        continue
                    try:
                        cmds.setAttr(plug, lock=False, keyable=True, channelBox=True)
                    except Exception:
                        pass
                    try:
                        if plug not in target_original_values:
                            target_original_values[plug] = cmds.getAttr(plug)
                    except Exception:
                        if plug not in target_original_values:
                            target_original_values[plug] = None
                    value = self._target_value_for(target, attr)
                    if value is not None:
                        try:
                            cmds.setAttr(plug, value)
                        except Exception:
                            pass
                    cmds.setDrivenKeyframe(plug, cd=driver_attr)
        finally:
            cmds.undoInfo(closeChunk=True)

            if original_driver_value is not None:
                restored_driver = (
                    original_driver_value[0]
                    if isinstance(original_driver_value, (list, tuple))
                    else original_driver_value
                )
                try:
                    cmds.setAttr(driver_attr, restored_driver)
                except Exception:
                    pass
            for plug, value in target_original_values.items():
                if value is None:
                    continue
                restored = value[0] if isinstance(value, (list, tuple)) else value
                try:
                    cmds.setAttr(plug, restored)
                except Exception:
                    pass
            if previous_selection:
                try:
                    cmds.select(previous_selection, r=True)
                except Exception:
                    pass
            else:
                try:
                    cmds.select(clear=True)
                except Exception:
                    pass

        cmds.inViewMessage(amg=u"<hl>Driven Key</hl> 設定完了", pos="topCenter", fade=True)

    def _edit_curves(self):
        source = self._active_source_joint()
        if not source:
            return
        targets = self._selected_targets()
        if not targets:
            cmds.warning(u"ターゲットが選択されていません。リストから1つ以上選択してください。")
            return
        attrs = self._selected_target_attributes()
        if not attrs:
            cmds.warning(u"ターゲット属性を1つ以上選択してください。")
            return

        anim_curves = []
        for target in targets:
            for attr in attrs:
                plug = f"{target}.{attr}"
                conns = cmds.listConnections(plug, type="animCurve", s=True, d=False) or []
                anim_curves.extend(conns)

        if not anim_curves:
            cmds.warning(u"関連するアニメーションカーブが見つかりません。")
            return

        cmds.select(anim_curves, r=True)
        mel.eval("GraphEditor;")

    def _on_mode_changed(self):
        mode = self.mode_combo.currentData()
        self.manual_group.setVisible(mode == self.MODE_MANUAL)
        if mode != self.MODE_MANUAL:
            self.targets_list.setEnabled(True)
        self._update_targets()

    def _on_get_source_clicked(self):
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        if modifiers & QtCore.Qt.AltModifier:
            self._fetch_source_from_targets()
        else:
            self._set_manual_source_from_selection()

    def _on_get_targets_clicked(self):
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        if modifiers & QtCore.Qt.AltModifier:
            self._fetch_targets_from_source()
        else:
            self._set_manual_targets_from_selection()

    def _set_manual_source_from_selection(self):
        sel = cmds.ls(sl=True, type="joint") or []
        if not sel:
            cmds.warning(u"ジョイントを選択してください。")
            return
        source = cmds.ls(sel[0], l=True) or [sel[0]]
        self._manual_source = source[0]
        self._current_source = self._manual_source
        self._update_manual_display()
        self._apply_manual_selection()

    def _set_manual_targets_from_selection(self):
        sel = cmds.ls(sl=True, type="joint") or []
        if not sel:
            cmds.warning(u"ターゲットとなるジョイントを選択してください。")
            return
        long_names = [cmds.ls(j, l=True)[0] if cmds.ls(j, l=True) else j for j in sel]
        self._manual_targets = list(dict.fromkeys(long_names))
        self._apply_manual_selection()

    def _fetch_targets_from_source(self):
        if not self._manual_source:
            cmds.warning(u"ソースが設定されていません。先にソースを取得してください。")
            return
        driver_attr = self._driver_attribute(self._manual_source)
        if not cmds.objExists(driver_attr):
            cmds.warning(u"ソースの回転属性が存在しません。")
            return
        curves = cmds.listConnections(driver_attr, type="animCurve", s=False, d=True) or []
        targets: List[str] = []
        for curve in curves:
            outputs = cmds.listConnections(f"{curve}.output", plugs=True, s=False, d=True) or []
            for plug in outputs:
                if "." not in plug:
                    continue
                node, _ = plug.split(".", 1)
                if cmds.nodeType(node) != "joint":
                    continue
                long_name = cmds.ls(node, l=True) or [node]
                target = long_name[0]
                if target not in targets:
                    targets.append(target)
        if not targets:
            cmds.warning(u"接続されたターゲットが見つかりません。")
            return
        self._manual_targets = targets
        self._apply_manual_selection()

    def _fetch_source_from_targets(self):
        sel = cmds.ls(sl=True, type="joint") or []
        if not sel:
            cmds.warning(u"ターゲットとなるジョイントを選択してください。")
            return
        for j in sel:
            long_name = cmds.ls(j, l=True) or [j]
            driver = self._find_driver_for_target(long_name[0])
            if driver:
                self._manual_source = driver
                self._current_source = driver
                self._update_manual_display()
                self._apply_manual_selection()
                return
        cmds.warning(u"接続されたソースが見つかりませんでした。")

    def _find_driver_for_target(self, target: str) -> str:
        for attr in self._target_attr_list:
            plug = f"{target}.{attr}"
            if not cmds.objExists(plug):
                continue
            curves = cmds.listConnections(plug, type="animCurve", s=True, d=False) or []
            for curve in curves:
                inputs = cmds.listConnections(curve, plugs=True, s=True, d=False) or []
                for input_plug in inputs:
                    if "." not in input_plug:
                        continue
                    node, _ = input_plug.split(".", 1)
                    if cmds.nodeType(node) != "joint":
                        continue
                    long_name = cmds.ls(node, l=True) or [node]
                    return long_name[0]
        return ""

    def _update_manual_display(self):
        self.manual_source_display.setText(_short_name(self._manual_source) if self._manual_source else "")
        if self._manual_targets:
            names = ", ".join(_short_name(t) for t in self._manual_targets)
        else:
            names = ""
        self.manual_targets_display.setText(names)


def show_dialog():
    global _dialog
    try:
        _dialog.close()
        _dialog.deleteLater()
    except Exception:
        pass
    _dialog = DrivenKeyToolDialog()
    _dialog.show()
    _dialog.raise_()
    _dialog.activateWindow()
    return _dialog


_dialog: Optional[DrivenKeyToolDialog] = None
