# -*- coding: utf-8 -*-
import maya.cmds as cmds

try:
    from PySide2 import QtCore, QtWidgets
    from shiboken2 import wrapInstance
    import maya.OpenMayaUI as omui
except Exception:  # pragma: no cover - Maya環境外ではUI関連モジュールが利用できない場合がある
    QtCore = QtWidgets = omui = wrapInstance = None


def _maya_main_window():
    if omui is None:
        raise RuntimeError("Maya UI modules are not available.")
    ptr = omui.MQtUtil.mainWindow()
    if ptr is None:
        raise RuntimeError("Mayaのメインウィンドウが取得できませんでした。")
    return wrapInstance(int(ptr), QtWidgets.QWidget)


def _is_half_joint(joint):
    short_name = joint.split("|")[-1]
    lowered = short_name.lower()
    return (
        lowered.endswith("_half")
        or lowered.endswith("_half_inf")
        or "halfjoint" in lowered
    )


def _list_base_children(joint):
    children = cmds.listRelatives(joint, c=True, type="joint") or []
    bases = []
    for child in children:
        if _is_half_joint(child):
            continue
        if cmds.attributeQuery("twistWeight", node=child, exists=True):
            continue
        bases.append(child)
    return bases


def create_twist_chain(count=4, name_tag="Twist", scale_at_90=1.2, reverse_twist=False):
    sel = cmds.ls(sl=True, type="joint") or []
    if not sel:
        cmds.error(u"開始ジョイントを1つ選択してください。")

    start = sel[0]

    existing_twists = _list_twist_joints(start)
    if existing_twists:
        cmds.warning(u"{0} 直下には既にツイストジョイントが存在するため、処理をスキップします。".format(start))
        return []

    base_candidates = _list_base_children(start)
    if not base_candidates:
        cmds.warning(u"{0} 直下にツイストの基礎となるジョイントが見つからないため、処理をスキップします。".format(start))
        return []
    if len(base_candidates) > 1:
        cmds.warning(u"{0} 直下に複数の基礎ジョイントが存在するため、ツイストチェーンの作成をスキップします。".format(start))
        return []

    ref = base_candidates[0]

    start_short = start.split("|")[-1]
    base_tag = name_tag or start_short

    p_start = cmds.xform(start, q=True, ws=True, t=True)
    p_ref = cmds.xform(ref, q=True, ws=True, t=True)
    length = ((p_ref[0] - p_start[0]) ** 2 + (p_ref[1] - p_start[1]) ** 2 + (p_ref[2] - p_start[2]) ** 2) ** 0.5
    if length < 1e-5:
        cmds.error(u"開始ジョイントと参照ジョイントの位置が同一です。")

    pma_sub = cmds.createNode("plusMinusAverage", n=f"{base_tag}_twistDelta_PMA")
    cmds.setAttr(pma_sub + ".operation", 2)  # subtract
    cmds.connectAttr(ref + ".rotateX", pma_sub + ".input1D[0]", f=True)
    cmds.connectAttr(start + ".rotateX", pma_sub + ".input1D[1]", f=True)

    base_radius = 1.0
    if cmds.attributeQuery("radius", node=start, exists=True):
        try:
            base_radius = cmds.getAttr(start + ".radius")
        except Exception:
            base_radius = 1.0

    abs_neg = cmds.createNode("multDoubleLinear", n=f"{base_tag}_twistAbsNeg_MDL")
    cmds.setAttr(abs_neg + ".input2", -1)
    cmds.connectAttr(pma_sub + ".output1D", abs_neg + ".input1", f=True)

    cond_abs = cmds.createNode("condition", n=f"{base_tag}_twistAbs_COND")
    cmds.setAttr(cond_abs + ".operation", 4)  # Less Than
    cmds.setAttr(cond_abs + ".secondTerm", 0)
    cmds.connectAttr(pma_sub + ".output1D", cond_abs + ".firstTerm", f=True)
    cmds.connectAttr(abs_neg + ".output", cond_abs + ".colorIfTrueR", f=True)
    cmds.connectAttr(pma_sub + ".output1D", cond_abs + ".colorIfFalseR", f=True)

    twist_range = cmds.createNode("setRange", n=f"{base_tag}_twistAmount_SR")
    cmds.setAttr(twist_range + ".minX", 0)
    cmds.setAttr(twist_range + ".maxX", 1)
    cmds.setAttr(twist_range + ".oldMinX", 0)
    cmds.setAttr(twist_range + ".oldMaxX", 90)
    cmds.connectAttr(cond_abs + ".outColorR", twist_range + ".valueX", f=True)

    created = []
    total = count + 1 if reverse_twist else count
    for idx in range(total):
        step_index = idx if reverse_twist else idx + 1
        ratio = float(step_index) / float(count + 1)

        suffix = "Root" if reverse_twist and step_index == 0 else f"{step_index:02d}"
        jnt_name = f"{start_short}_twist{suffix}"
        j = cmds.duplicate(start, po=True, n=jnt_name)[0]

        if cmds.attributeQuery("radius", node=j, exists=True):
            try:
                cmds.setAttr(j + ".radius", base_radius * 2.0)
            except Exception:
                pass

        try:
            cmds.parent(j, start)
        except Exception:
            pass

        cmds.setAttr(j + ".translateY", 0)
        cmds.setAttr(j + ".translateZ", 0)
        cmds.setAttr(j + ".translateX", length * ratio)

        for ax in ("X", "Y", "Z"):
            try:
                cmds.setAttr(j + ".rotate" + ax, l=False, k=True, cb=True)
            except Exception:
                pass

        if cmds.objExists(j + ".segmentScaleCompensate"):
            try:
                cmds.setAttr(j + ".segmentScaleCompensate", 0)
            except Exception:
                pass

        node_suffix = "Root" if reverse_twist and step_index == 0 else f"{step_index:02d}"

        md = cmds.createNode("multDoubleLinear", n=f"{base_tag}_twist{node_suffix}_MD")
        cmds.connectAttr(pma_sub + ".output1D", md + ".input1", f=True)

        pma_add = cmds.createNode("plusMinusAverage", n=f"{base_tag}_twist{node_suffix}_PMA")
        cmds.setAttr(pma_add + ".operation", 1)
        cmds.connectAttr(start + ".rotateX", pma_add + ".input1D[0]", f=True)
        cmds.connectAttr(md + ".output", pma_add + ".input1D[1]", f=True)

        final_output = pma_add + ".output1D"
        if reverse_twist:
            reverse_attr = "reverseTwistWeight"
            reverse_value = max(0.0, 1.0 - ratio)
            if not cmds.attributeQuery(reverse_attr, node=j, exists=True):
                cmds.addAttr(j, ln=reverse_attr, at="double", min=0.0, dv=reverse_value)
                cmds.setAttr(j + "." + reverse_attr, e=True, k=True)
            cmds.setAttr(j + "." + reverse_attr, reverse_value)

            rev_md = cmds.createNode("multDoubleLinear", n=f"{base_tag}_twist{node_suffix}_reverse_MDL")
            cmds.connectAttr(start + ".rotateX", rev_md + ".input1", f=True)
            cmds.connectAttr(j + "." + reverse_attr, rev_md + ".input2", f=True)

            rev_neg = cmds.createNode("multDoubleLinear", n=f"{base_tag}_twist{node_suffix}_reverseNeg_MDL")
            cmds.setAttr(rev_neg + ".input2", -1)
            cmds.connectAttr(rev_md + ".output", rev_neg + ".input1", f=True)

            final_add = cmds.createNode("addDoubleLinear", n=f"{base_tag}_twist{node_suffix}_reverse_ADL")
            cmds.connectAttr(pma_add + ".output1D", final_add + ".input1", f=True)
            cmds.connectAttr(rev_neg + ".output", final_add + ".input2", f=True)
            final_output = final_add + ".output"

        cmds.connectAttr(final_output, j + ".rotateX", f=True)
        for ax in ("Y", "Z"):
            cmds.setAttr(j + ".rotate" + ax, l=True, k=False, cb=False)

        ratio_attr = "twistWeight"
        if not cmds.attributeQuery(ratio_attr, node=j, exists=True):
            cmds.addAttr(j, ln=ratio_attr, at="double", min=0.0, dv=ratio)
            cmds.setAttr(j + "." + ratio_attr, e=True, k=True)
        cmds.setAttr(j + "." + ratio_attr, ratio)
        cmds.connectAttr(j + "." + ratio_attr, md + ".input2", f=True)

        scale_factor = float(step_index) if step_index > 0 else 0.0
        scale_raito = (scale_at_90 - 1) * scale_factor / float(count) + 1
        scale_attr = "twistScaleMax"
        if not cmds.attributeQuery(scale_attr, node=j, exists=True):
            cmds.addAttr(j, ln=scale_attr, at="double", min=0.0, dv=scale_raito)
            cmds.setAttr(j + "." + scale_attr, e=True, k=True)
        else:
            cmds.setAttr(j + "." + scale_attr, scale_raito)

        delta_add = cmds.createNode("addDoubleLinear", n=f"{base_tag}_twist{node_suffix}_scaleDelta_ADL")
        cmds.connectAttr(j + "." + scale_attr, delta_add + ".input1", f=True)
        cmds.setAttr(delta_add + ".input2", -1)

        scale_md = cmds.createNode("multDoubleLinear", n=f"{base_tag}_twist{node_suffix}_scale_MD")
        cmds.connectAttr(twist_range + ".outValueX", scale_md + ".input1", f=True)
        cmds.connectAttr(delta_add + ".output", scale_md + ".input2", f=True)

        scale_add = cmds.createNode("addDoubleLinear", n=f"{base_tag}_twist{node_suffix}_scale_ADL")
        cmds.connectAttr(scale_md + ".output", scale_add + ".input1", f=True)
        cmds.setAttr(scale_add + ".input2", 1)

        cmds.connectAttr(scale_add + ".output", j + ".scaleY", f=True)
        cmds.connectAttr(scale_add + ".output", j + ".scaleZ", f=True)

        created.append(j)

    layer_name = "twist_jnt"
    if cmds.objExists(layer_name):
        if cmds.nodeType(layer_name) != "displayLayer":
            cmds.error(u"'{0}' は displayLayer ではありません。".format(layer_name))
        layer = layer_name
    else:
        layer = cmds.createDisplayLayer(name=layer_name, empty=True, nr=True)

    try:
        cmds.editDisplayLayerMembers(layer, created, nr=True)
    except Exception:
        pass

    if reverse_twist:
        start_short_name = start.split("|")[-1]
        if not start_short_name.endswith("_D"):
            new_short_name = start_short_name + "_D"
            if cmds.objExists(new_short_name):
                cmds.warning(
                    u"{0} に '_D' を付加した名前 {1} は既に存在するため、リネームをスキップします。".format(
                        start_short_name, new_short_name
                    )
                )
            else:
                try:
                    start = cmds.rename(start, new_short_name)
                except RuntimeError as exc:
                    cmds.warning(
                        u"{0} のリネームに失敗しました: {1}".format(start_short_name, exc)
                    )

    cmds.select(created, r=True)
    print(u"[Twist] 作成:", created)
    return created


def _list_twist_joints(base_joint):
    children = cmds.listRelatives(base_joint, c=True, type="joint") or []
    twist_joints = []
    for child in children:
        if cmds.attributeQuery("twistWeight", node=child, exists=True) and cmds.attributeQuery(
            "twistScaleMax", node=child, exists=True
        ):
            twist_joints.append(child)
    return twist_joints


if QtWidgets is not None:

    class TwistChainEditorDialog(QtWidgets.QDialog):
        WINDOW_OBJECT_NAME = "twistChainEditorDialog"

        def __init__(self, parent=None):
            if parent is None:
                parent = _maya_main_window()
            super(TwistChainEditorDialog, self).__init__(parent)
            self.setObjectName(self.WINDOW_OBJECT_NAME)
            self.setWindowTitle(u"Twist Chain Editor")
            self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)

            self._create_widgets()
            self._create_layout()
            self._create_connections()

            self._refresh_data()

        def _create_widgets(self):
            self.info_label = QtWidgets.QLabel("")

            self.table = QtWidgets.QTableWidget(0, 3)
            headers = [u"Joint", u"Twist Weight", u"Scale Max"]
            self.table.setHorizontalHeaderLabels(headers)
            header = self.table.horizontalHeader()
            header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
            header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
            header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
            self.table.verticalHeader().setVisible(False)
            self.table.setAlternatingRowColors(True)
            self.table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
            self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

            self.refresh_button = QtWidgets.QPushButton(u"Refresh")
            self.apply_button = QtWidgets.QPushButton(u"Apply")
            self.close_button = QtWidgets.QPushButton(u"Close")

        def _create_layout(self):
            main_layout = QtWidgets.QVBoxLayout(self)
            main_layout.addWidget(self.info_label)
            main_layout.addWidget(self.table)

            button_layout = QtWidgets.QHBoxLayout()
            button_layout.addStretch(1)
            button_layout.addWidget(self.refresh_button)
            button_layout.addWidget(self.apply_button)
            button_layout.addWidget(self.close_button)
            main_layout.addLayout(button_layout)

        def _create_connections(self):
            self.refresh_button.clicked.connect(self._refresh_data)
            self.apply_button.clicked.connect(self._apply_changes)
            self.close_button.clicked.connect(self.close)

        def _refresh_data(self):
            sel = cmds.ls(sl=True, type="joint") or []
            if not sel:
                self._populate_table([], message=u"編集対象のジョイントを選択してください。")
                return

            base = sel[0]
            twist_joints = _list_twist_joints(base)
            if not twist_joints:
                self._populate_table([], message=u"選択したジョイント直下にツイストジョイントが見つかりません。")
                return

            self._populate_table(twist_joints, message=u"ベースジョイント: {0}".format(base))

        def _populate_table(self, joints, message=""):
            self.table.setRowCount(0)
            self.info_label.setText(message)
            self.table.setEnabled(bool(joints))

            for row, joint in enumerate(joints):
                self.table.insertRow(row)

                item = QtWidgets.QTableWidgetItem(joint)
                item.setFlags(QtCore.Qt.ItemIsEnabled)
                self.table.setItem(row, 0, item)

                weight_spin = QtWidgets.QDoubleSpinBox()
                weight_spin.setDecimals(3)
                weight_spin.setRange(0.0, 10.0)
                weight_spin.setSingleStep(0.01)
                try:
                    weight_value = cmds.getAttr(joint + ".twistWeight")
                except Exception:
                    weight_value = 0.0
                weight_spin.setValue(weight_value)
                self.table.setCellWidget(row, 1, weight_spin)

                scale_spin = QtWidgets.QDoubleSpinBox()
                scale_spin.setDecimals(3)
                scale_spin.setRange(0.0, 20.0)
                scale_spin.setSingleStep(0.01)
                try:
                    scale_value = cmds.getAttr(joint + ".twistScaleMax")
                except Exception:
                    scale_value = 1.0
                scale_spin.setValue(scale_value)
                self.table.setCellWidget(row, 2, scale_spin)

        def _apply_changes(self):
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if item is None:
                    continue
                joint = item.text()
                if not cmds.objExists(joint):
                    continue

                weight_widget = self.table.cellWidget(row, 1)
                scale_widget = self.table.cellWidget(row, 2)
                if weight_widget is None or scale_widget is None:
                    continue

                weight_value = weight_widget.value()
                scale_value = scale_widget.value()

                try:
                    cmds.setAttr(joint + ".twistWeight", weight_value)
                except Exception:
                    pass
                try:
                    cmds.setAttr(joint + ".twistScaleMax", scale_value)
                except Exception:
                    pass

        def closeEvent(self, event):
            super(TwistChainEditorDialog, self).closeEvent(event)
            global _twist_chain_editor_dialog
            _twist_chain_editor_dialog = None


else:

    class TwistChainEditorDialog(object):
        pass


_twist_chain_editor_dialog = None


def show_twist_chain_editor():
    if QtWidgets is None:
        raise RuntimeError("PySide2 modules are not available.")
    global _twist_chain_editor_dialog
    if _twist_chain_editor_dialog is None:
        _twist_chain_editor_dialog = TwistChainEditorDialog()
    _twist_chain_editor_dialog.show()
    _twist_chain_editor_dialog.raise_()
    _twist_chain_editor_dialog.activateWindow()
    return _twist_chain_editor_dialog


if __name__ == "__main__":
    create_twist_chain()
