# -*- coding: utf-8 -*-
import maya.cmds as cmds

try:  # pragma: no cover - Maya環境外ではUI関連モジュールが利用できない場合がある
    from PySide2 import QtCore, QtWidgets
    from shiboken2 import wrapInstance
    import maya.OpenMayaUI as omui
except Exception:  # pragma: no cover - Maya環境外ではUI関連モジュールが利用できない場合がある
    QtCore = QtWidgets = omui = wrapInstance = None

LAYER_NAME = "halfrot_jnt"
OPTIONVAR_SKIP_ROTATE_X = "ARigTool_SkipHalfRotateX"
_half_rotation_dialog = None


def _strip_duplicate_suffix(name):
    if name.endswith("_D"):
        return name[:-2]
    return name


def _uniquify(base):
    if not cmds.objExists(base):
        return base
    i = 1
    while True:
        name = f"{base}{i:02d}"
        if not cmds.objExists(name):
            return name
        i += 1


def _has_half_joint(base_joint):
    """Return True if a half joint already exists for *base_joint*."""

    base_short = _strip_duplicate_suffix(base_joint.split("|")[-1])
    parent = cmds.listRelatives(base_joint, p=True, pa=True) or []
    candidates = []
    if parent:
        candidates = cmds.listRelatives(parent[0], c=True, type="joint", pa=True) or []
    else:
        pattern = f"{base_short}_Half*"
        candidates = cmds.ls(pattern, type="joint", l=True) or []

    for candidate in candidates:
        if candidate == base_joint:
            continue
        short = _strip_duplicate_suffix(candidate.split("|")[-1])
        if short.startswith(base_short + "_Half"):
            return True
    return False


def _ensure_display_layer(name):
    if not cmds.objExists(name) or cmds.nodeType(name) != "displayLayer":
        return cmds.createDisplayLayer(name=name, empty=True)
    return name


def _maya_main_window():
    if omui is None:
        raise RuntimeError("Maya UI modules are not available.")
    ptr = omui.MQtUtil.mainWindow()
    if ptr is None:
        raise RuntimeError("Mayaのメインウィンドウが取得できませんでした。")
    return wrapInstance(int(ptr), QtWidgets.QWidget)


def _get_skip_rotate_x_preference():
    if cmds.optionVar(exists=OPTIONVAR_SKIP_ROTATE_X):
        return bool(cmds.optionVar(q=OPTIONVAR_SKIP_ROTATE_X))
    return False


def _set_skip_rotate_x_preference(enabled):
    cmds.optionVar(iv=(OPTIONVAR_SKIP_ROTATE_X, int(bool(enabled))))


def create_half_rotation_joint(skip_rotate_x=None):
    if skip_rotate_x is None:
        skip_rotate_x = _get_skip_rotate_x_preference()

    sel = cmds.ls(sl=True, type="joint") or []
    if not sel:
        cmds.warning(u"ジョイントを1つ以上選択してください。")
        return

    layer = _ensure_display_layer(LAYER_NAME)

    cmds.undoInfo(openChunk=True)
    created = []
    try:
        for j in sel:
            base = _strip_duplicate_suffix(j.split("|")[-1])

            if _has_half_joint(j):
                cmds.warning(u"{0} には既にHalfジョイントが存在するため、作成をスキップします。".format(j))
                continue

            half_name = _uniquify(base + "_Half")
            half = cmds.duplicate(j, po=True, n=half_name)[0]
            cmds.matchTransform(half, j, pos=True, rot=True, scl=False)
            ro = cmds.getAttr(j + ".rotateOrder")
            cmds.setAttr(half + ".rotateOrder", ro)

            try:
                src_rad = cmds.getAttr(j + ".radius")
            except Exception:
                src_rad = 1.0
            cmds.setAttr(half + ".radius", max(0.01, src_rad * 2.0))

            md_name = _uniquify("md_%s_half" % base)
            md = cmds.createNode("multiplyDivide", n=md_name)
            cmds.setAttr(md + ".operation", 1)
            if not skip_rotate_x:
                cmds.setAttr(md + ".input2X", 0.5)
            cmds.setAttr(md + ".input2Y", 0.5)
            cmds.setAttr(md + ".input2Z", 0.5)

            for ax in ("X", "Y", "Z"):
                dst_plug = f"{half}.rotate{ax}"
                cons = cmds.listConnections(dst_plug, s=True, d=False, p=True) or []
                for c in cons:
                    try:
                        cmds.disconnectAttr(c, dst_plug)
                    except Exception:
                        pass

            if skip_rotate_x:
                try:
                    cmds.setAttr(half + ".rotateX", 0)
                except Exception:
                    pass
            else:
                cmds.connectAttr(j + ".rotateX", md + ".input1X", f=True)
                cmds.connectAttr(md + ".outputX", half + ".rotateX", f=True)
            cmds.connectAttr(j + ".rotateY", md + ".input1Y", f=True)
            cmds.connectAttr(j + ".rotateZ", md + ".input1Z", f=True)
            cmds.connectAttr(md + ".outputY", half + ".rotateY", f=True)
            cmds.connectAttr(md + ".outputZ", half + ".rotateZ", f=True)

            inf_name = _uniquify(base + "_Half_INF")
            cmds.select(clear=True)
            inf = cmds.joint(n=inf_name)
            cmds.parent(inf, half)
            cmds.setAttr(inf + ".translate", 0, 0, 0, type="double3")
            cmds.setAttr(inf + ".rotate", 0, 0, 0, type="double3")
            cmds.setAttr(inf + ".jointOrient", 0, 0, 0, type="double3")
            cmds.setAttr(inf + ".radius", max(0.01, src_rad * 1.5))

            cmds.editDisplayLayerMembers(layer, [half, inf], noRecurse=True)

            created.append((half, inf))

        if created:
            msg = u"\n".join([u"Half: %s / Influence: %s" % (h, i) for h, i in created])
            cmds.inViewMessage(amg=u"<hl>半回転ジョイント作成</hl><br>%s" % msg, pos="topCenter", fade=True, alpha=0.9)
    finally:
        cmds.undoInfo(closeChunk=True)


if QtWidgets is not None:  # pragma: no cover - Maya環境でのみ利用

    class HalfRotationDialog(QtWidgets.QDialog):
        def __init__(self, parent=None):
            if parent is None:
                parent = _maya_main_window()
            super(HalfRotationDialog, self).__init__(parent)
            self.setWindowTitle(u"Create Half Rotation Joint")
            self.setObjectName("halfRotationDialog")
            self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)

            self._create_widgets()
            self._create_layout()

        def _create_widgets(self):
            self.skip_x_checkbox = QtWidgets.QCheckBox(u"X回転を接続しない")
            self.skip_x_checkbox.setChecked(_get_skip_rotate_x_preference())

            self.create_button = QtWidgets.QPushButton(u"Create")
            self.close_button = QtWidgets.QPushButton(u"Close")
            self.create_button.clicked.connect(self._on_create_clicked)
            self.close_button.clicked.connect(self.close)

        def _create_layout(self):
            main_layout = QtWidgets.QVBoxLayout(self)
            main_layout.addWidget(self.skip_x_checkbox)

            button_layout = QtWidgets.QHBoxLayout()
            button_layout.addStretch(1)
            button_layout.addWidget(self.create_button)
            button_layout.addWidget(self.close_button)
            main_layout.addLayout(button_layout)

        def _on_create_clicked(self):
            enabled = self.skip_x_checkbox.isChecked()
            _set_skip_rotate_x_preference(enabled)
            create_half_rotation_joint(skip_rotate_x=enabled)

        def closeEvent(self, event):
            super(HalfRotationDialog, self).closeEvent(event)
            global _half_rotation_dialog
            _half_rotation_dialog = None


    _half_rotation_dialog = None


    def show_half_rotation_dialog():
        global _half_rotation_dialog
        if _half_rotation_dialog is None:
            _half_rotation_dialog = HalfRotationDialog()
        _half_rotation_dialog.show()
        _half_rotation_dialog.raise_()
        _half_rotation_dialog.activateWindow()
        return _half_rotation_dialog

else:

    def show_half_rotation_dialog():  # pragma: no cover - Maya環境外
        raise RuntimeError("PySide2 modules are not available.")


if __name__ == "__main__":
    create_half_rotation_joint()
