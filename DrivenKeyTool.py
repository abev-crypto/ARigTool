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

    def __init__(self, parent=None):
        super(DrivenKeyToolDialog, self).__init__(parent or maya_main_window())

        self.setWindowTitle(u"Driven Key Helper")
        self.setObjectName("drivenKeyToolDialog")
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)

        self._target_items: List[str] = []

        self._create_widgets()
        self._create_layout()
        self._create_connections()
        self._update_targets()

    def _create_widgets(self):
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItem("Twist", self.MODE_TWIST)
        self.mode_combo.addItem("Half", self.MODE_HALF)

        self.source_axis_combo = QtWidgets.QComboBox()
        self.source_axis_combo.addItems(["X", "Y", "Z"])

        self.targets_list = QtWidgets.QListWidget()
        self.targets_list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.targets_list.setFocusPolicy(QtCore.Qt.NoFocus)

        self.refresh_button = QtWidgets.QPushButton(u"Refresh Targets")

        self.target_groups: Dict[str, Dict[str, QtWidgets.QCheckBox]] = {}
        self._create_target_checkboxes()

        self.set_key_button = QtWidgets.QPushButton(u"Set Driven Key")
        self.edit_curve_button = QtWidgets.QPushButton(u"Edit Curves")
        self.close_button = QtWidgets.QPushButton(u"Close")

    def _create_target_checkboxes(self):
        attrs = {
            "translate": ("X", "Y", "Z"),
            "rotate": ("X", "Y", "Z"),
            "scale": ("X", "Y", "Z"),
        }
        for prefix, axes in attrs.items():
            group_box = QtWidgets.QGroupBox(prefix.title())
            layout = QtWidgets.QHBoxLayout(group_box)
            self.target_groups[prefix] = {}
            for axis in axes:
                cb = QtWidgets.QCheckBox(axis)
                if prefix == "rotate" and axis == "X":
                    cb.setChecked(True)
                layout.addWidget(cb)
                self.target_groups[prefix][axis] = cb
            layout.addStretch(1)
            setattr(self, f"{prefix}_group", group_box)

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

        main_layout.addWidget(self.translate_group)
        main_layout.addWidget(self.rotate_group)
        main_layout.addWidget(self.scale_group)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addWidget(self.set_key_button)
        button_layout.addWidget(self.edit_curve_button)
        button_layout.addStretch(1)
        button_layout.addWidget(self.close_button)
        main_layout.addLayout(button_layout)

    def _create_connections(self):
        self.mode_combo.currentIndexChanged.connect(self._update_targets)
        self.refresh_button.clicked.connect(self._update_targets)
        self.set_key_button.clicked.connect(self._set_driven_key)
        self.edit_curve_button.clicked.connect(self._edit_curves)
        self.close_button.clicked.connect(self.close)

    # region Target search helpers
    def _get_source_joint(self) -> str:
        sel = cmds.ls(sl=True, type="joint") or []
        if not sel:
            cmds.warning(u"ソースとなるジョイントを1つ選択してください。")
            return ""
        if len(sel) > 1:
            cmds.warning(u"最初の選択ジョイントのみをソースとして使用します。")
        return sel[0]

    def _list_siblings(self, node: str) -> List[str]:
        parent = cmds.listRelatives(node, parent=True, fullPath=True) or []
        if parent:
            siblings = cmds.listRelatives(parent[0], children=True, type="joint", fullPath=True) or []
        else:
            siblings = cmds.ls(assemblies=True, type="joint") or []
        return list(dict.fromkeys(siblings))

    def _list_children(self, node: str) -> List[str]:
        return cmds.listRelatives(node, children=True, type="joint", fullPath=True) or []

    def _collect_targets(self, source: str) -> List[str]:
        mode = self.mode_combo.currentData()
        candidates: List[str] = []
        if mode == self.MODE_TWIST:
            siblings = self._list_siblings(source)
            children = self._list_children(source)
            combined = list(dict.fromkeys(siblings + children))
            for j in combined:
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
        return list(dict.fromkeys(candidates))

    def _update_targets(self):
        source = self._get_source_joint()
        if not source:
            self.targets_list.clear()
            self._target_items = []
            return

        targets = self._collect_targets(source)
        self.targets_list.clear()
        for j in targets:
            self.targets_list.addItem(_short_name(j))
        self._target_items = targets

    # endregion

    def _selected_target_attributes(self) -> List[str]:
        attrs: List[str] = []
        for prefix, axes in self.target_groups.items():
            for axis, checkbox in axes.items():
                if checkbox.isChecked():
                    attrs.append(f"{prefix}{axis}")
        return attrs

    def _driver_attribute(self, source: str) -> str:
        axis = self.source_axis_combo.currentText()
        return f"{source}.rotate{axis}"

    def _set_driven_key(self):
        source = self._get_source_joint()
        if not source:
            return

        targets = self._target_items
        if not targets:
            cmds.warning(u"ターゲットが見つかりません。Refresh Targets を試してください。")
            return

        attrs = self._selected_target_attributes()
        if not attrs:
            cmds.warning(u"ターゲット属性を1つ以上選択してください。")
            return

        driver_attr = self._driver_attribute(source)
        if not cmds.objExists(driver_attr):
            cmds.warning(u"ソースジョイントに選択された軸が存在しません。")
            return

        cmds.undoInfo(openChunk=True)
        try:
            for target in targets:
                for attr in attrs:
                    plug = f"{target}.{attr}"
                    if not cmds.objExists(plug):
                        continue
                    try:
                        cmds.setAttr(plug, lock=False, keyable=True, channelBox=True)
                    except Exception:
                        pass
                    cmds.setDrivenKeyframe(plug, cd=driver_attr)
        finally:
            cmds.undoInfo(closeChunk=True)

        cmds.inViewMessage(amg=u"<hl>Driven Key</hl> 設定完了", pos="topCenter", fade=True)

    def _edit_curves(self):
        source = self._get_source_joint()
        if not source:
            return
        targets = self._target_items
        if not targets:
            cmds.warning(u"ターゲットが見つかりません。Refresh Targets を試してください。")
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
