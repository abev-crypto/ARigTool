# -*- coding: utf-8 -*-
import maya.cmds as cmds
from typing import Callable, Dict, List, Optional, Sequence
try:  # pragma: no cover - Maya環墁EではUI関連モジュールが利用できなぁE合がある
    from PySide2 import QtCore, QtWidgets
    from shiboken2 import wrapInstance
    import maya.OpenMayaUI as omui
except Exception:  # pragma: no cover - Maya環墁EではUI関連モジュールが利用できなぁE合がある
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
        raise RuntimeError("Unable to obtain Maya main window.")
    ptr = omui.MQtUtil.mainWindow()
    if ptr is None:
        raise RuntimeError("Unable to obtain Maya main window.")
    return wrapInstance(int(ptr), QtWidgets.QWidget)
def _get_skip_rotate_x_preference():
    if cmds.optionVar(exists=OPTIONVAR_SKIP_ROTATE_X):
        return bool(cmds.optionVar(q=OPTIONVAR_SKIP_ROTATE_X))
    return False
def _set_skip_rotate_x_preference(enabled):
    cmds.optionVar(iv=(OPTIONVAR_SKIP_ROTATE_X, int(bool(enabled))))
ANIM_CURVE_TYPES: Sequence[str] = (
    "animCurveUL",
    "animCurveUA",
    "animCurveUT",
    "animCurveUU",
)
def _list_connected_anim_curves(target, **kwargs):
    connections = cmds.listConnections(target, **kwargs) or []
    result = []
    for connection in connections:
        node = connection.split(".")[0] if isinstance(connection, str) else connection
        if cmds.nodeType(node) in ANIM_CURVE_TYPES:
            result.append(connection)
    return result
def _list_driven_attributes(node):
    anim_curves = _list_connected_anim_curves(node, s=True, d=False) or []
    attrs: List[str] = []
    for curve in anim_curves:
        outputs = cmds.listConnections(curve + ".output", s=False, d=True, p=True) or []
        for plug in outputs:
            attrs.append(plug.split(".", 1)[1])
    return sorted(set(attrs))
def _create_half_rotation_joint_internal(
    base_joint: str,
    *,
    skip_rotate_x: bool,
    layer: Optional[str] = None,
) -> Optional[Dict[str, object]]:
    if not cmds.objExists(base_joint):
        cmds.warning("Joint {0} was not found.".format(base_joint))
        return None
    base = _strip_duplicate_suffix(base_joint.split("|")[-1])
    if _has_half_joint(base_joint):
        cmds.warning("Half joint already exists for {0}; skipping.".format(base_joint))
        return None
    half_name = _uniquify(base + "_Half")
    try:
        half = cmds.duplicate(base_joint, po=True, n=half_name)[0]
    except Exception as exc:
        cmds.warning("Failed to duplicate {0}: {1}".format(base_joint, exc))
        return None
    try:
        cmds.matchTransform(half, base_joint, pos=True, rot=True, scl=False)
    except Exception:
        pass
    try:
        ro = cmds.getAttr(base_joint + ".rotateOrder")
        cmds.setAttr(half + ".rotateOrder", ro)
    except Exception:
        pass
    try:
        src_rad = cmds.getAttr(base_joint + ".radius")
    except Exception:
        src_rad = 1.0
    try:
        cmds.setAttr(half + ".radius", max(0.01, src_rad * 2.0))
    except Exception:
        pass
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
        cmds.connectAttr(base_joint + ".rotateX", md + ".input1X", f=True)
        cmds.connectAttr(md + ".outputX", half + ".rotateX", f=True)
    cmds.connectAttr(base_joint + ".rotateY", md + ".input1Y", f=True)
    cmds.connectAttr(base_joint + ".rotateZ", md + ".input1Z", f=True)
    cmds.connectAttr(md + ".outputY", half + ".rotateY", f=True)
    cmds.connectAttr(md + ".outputZ", half + ".rotateZ", f=True)
    inf_name = _uniquify(base + "_Half_INF")
    cmds.select(clear=True)
    inf = cmds.joint(n=inf_name)
    cmds.parent(inf, half)
    cmds.setAttr(inf + ".translate", 0, 0, 0, type="double3")
    cmds.setAttr(inf + ".rotate", 0, 0, 0, type="double3")
    cmds.setAttr(inf + ".jointOrient", 0, 0, 0, type="double3")
    try:
        cmds.setAttr(inf + ".radius", max(0.01, src_rad * 1.5))
    except Exception:
        pass
    if layer:
        try:
            cmds.editDisplayLayerMembers(layer, [half, inf], noRecurse=True)
        except Exception:
            pass
    return {"half": half, "influences": [inf], "mult_node": md}
def create_half_rotation_joint(skip_rotate_x=None):
    if skip_rotate_x is None:
        skip_rotate_x = _get_skip_rotate_x_preference()
    sel = cmds.ls(sl=True, type="joint") or []
    if not sel:
        cmds.warning("Select at least one joint.")
        return
    layer = _ensure_display_layer(LAYER_NAME)
    cmds.undoInfo(openChunk=True)
    created = []
    try:
        for joint in sel:
            result = _create_half_rotation_joint_internal(joint, skip_rotate_x=skip_rotate_x, layer=layer)
            if not result:
                continue
            half = result.get("half")
            influences = result.get("influences") or []
            created.append((half, influences))
    finally:
        cmds.undoInfo(closeChunk=True)
    if created:
        lines = []
        for half, influences in created:
            if half is None:
                continue
            if influences:
                lines.append("Half: {0} / Influence: {1}".format(half, influences[0]))
            else:
                lines.append("Half: {0}".format(half))
        if lines:
            msg = "\n".join(lines)
            cmds.inViewMessage(amg="<hl>Half Rotation Created</hl><br>{0}".format(msg), pos="topCenter", fade=True, alpha=0.9)
def _list_half_at_same_level(start: str) -> List[str]:
    start_short = start.split("|")[-1]
    base_short = _strip_duplicate_suffix(start_short)
    half_joints: List[str] = []
    candidates = set(cmds.listRelatives(start, c=True, type="joint") or [])
    parent = cmds.listRelatives(start, p=True) or []
    if parent:
        siblings = cmds.listRelatives(parent[0], c=True, type="joint") or []
        candidates.update(siblings)
    for candidate in candidates:
        if candidate == start:
            continue
        short = candidate.split("|")[-1]
        short_base = _strip_duplicate_suffix(short)
        if short_base.startswith(f"{base_short}_Half"):
            half_joints.append(candidate)
    return half_joints
def collect_half_joint_data(start: str) -> Optional[List[Dict[str, object]]]:
    if not cmds.objExists(start):
        return None
    half_joints = _list_half_at_same_level(start)
    if not half_joints:
        return None
    data: List[Dict[str, object]] = []
    for half in half_joints:
        infs = cmds.listRelatives(half, c=True, type="joint") or []
        inf_infos: List[Dict[str, object]] = []
        for inf in infs:
            pos = cmds.xform(inf, q=True, ws=True, t=True)
            try:
                radius = cmds.getAttr(inf + ".radius")
            except Exception:
                radius = 1.0
            driven_attrs = _list_driven_attributes(inf)
            inf_infos.append(
                {
                    "name": inf,
                    "position": pos,
                    "radius": radius,
                    "driven": driven_attrs,
                }
            )
        try:
            rotate_order = cmds.getAttr(half + ".rotateOrder")
        except Exception:
            rotate_order = 0
        try:
            half_radius = cmds.getAttr(half + ".radius")
        except Exception:
            half_radius = 1.0
        data.append(
            {
                "name": half,
                "rotateOrder": rotate_order,
                "radius": half_radius,
                "infs": inf_infos,
            }
        )
    return data
def cleanup_half_joints(start: str) -> None:
    half_joints = _list_half_at_same_level(start)
    if half_joints:
        cmds.delete(half_joints)
def build_half_chain_from_data(
    target_start: str,
    data: Sequence[Dict[str, object]],
    *,
    name_mapper: Optional[Callable[[str], Optional[str]]] = None,
    position_mapper: Optional[Callable[[Sequence[float]], Sequence[float]]] = None,
    copy_driven_callback: Optional[Callable[[str, str, Sequence[str]], None]] = None,
    skip_rotate_x: Optional[bool] = None,
    select_result: bool = False,
    show_message: bool = False,
) -> List[str]:
    if not cmds.objExists(target_start):
        cmds.warning("Target joint {0} does not exist.".format(target_start))
        return []
    if not data:
        return []
    if skip_rotate_x is None:
        skip_rotate_x = _get_skip_rotate_x_preference()
    cleanup_half_joints(target_start)
    layer = _ensure_display_layer(LAYER_NAME)
    created_halves: List[str] = []
    for info in data:
        result = _create_half_rotation_joint_internal(
            target_start,
            skip_rotate_x=bool(skip_rotate_x),
            layer=layer,
        )
        if not result:
            continue
        half = result.get("half")
        if not half:
            continue
        target_name = info.get("name")
        if name_mapper:
            mapped = name_mapper(target_name)
            if mapped:
                target_name = mapped
        if not target_name:
            target_name = info.get("name")
        target_name = _uniquify(target_name)
        half = cmds.rename(half, target_name)
        try:
            cmds.setAttr(half + ".rotateOrder", int(info.get("rotateOrder", 0)))
        except Exception:
            pass
        try:
            radius_value = max(0.01, float(info.get("radius", 1.0)))
            cmds.setAttr(half + ".radius", radius_value)
        except Exception:
            pass
        existing_children = cmds.listRelatives(half, c=True, type="joint") or []
        if existing_children:
            cmds.delete(existing_children)
        created_infs: List[str] = []
        half_short = half.split("|")[-1]
        for inf_info in info.get("infs", []):
            source_inf_name = inf_info.get("name")
            target_inf_name = None
            if name_mapper:
                target_inf_name = name_mapper(source_inf_name)
            if not target_inf_name:
                target_inf_name = half_short + "_INF"
            target_inf_name = _uniquify(target_inf_name)
            cmds.select(clear=True)
            inf = cmds.joint(n=target_inf_name)
            cmds.parent(inf, half)
            cmds.setAttr(inf + ".translate", 0, 0, 0, type="double3")
            cmds.setAttr(inf + ".rotate", 0, 0, 0, type="double3")
            cmds.setAttr(inf + ".jointOrient", 0, 0, 0, type="double3")
            try:
                inf_radius = max(0.01, float(inf_info.get("radius", 1.0)))
                cmds.setAttr(inf + ".radius", inf_radius)
            except Exception:
                pass
            pos = inf_info.get("position")
            mapped_pos = None
            if pos is not None:
                mapped_pos = position_mapper(pos) if position_mapper else pos
            if mapped_pos and len(mapped_pos) == 3:
                try:
                    cmds.xform(inf, ws=True, t=mapped_pos)
                except Exception:
                    pass
            if copy_driven_callback:
                attrs = inf_info.get("driven") or []
                if attrs:
                    copy_driven_callback(source_inf_name, inf, attrs)
            created_infs.append(inf)
        try:
            cmds.editDisplayLayerMembers(layer, [half] + created_infs, nr=True)
        except Exception:
            pass
        created_halves.append(half)
    if select_result and created_halves:
        cmds.select(created_halves, add=True)
    if show_message and created_halves:
        cmds.inViewMessage(
            amg="<hl>Half Rotation Created</hl><br>{0}".format("\n".join(created_halves)),
            pos="topCenter",
            fade=True,
        )
    return created_halves
if QtWidgets is not None:  # pragma: no cover - Maya環墁Eのみ利用
    class HalfRotationDialog(QtWidgets.QDialog):
        def __init__(self, parent=None):
            if parent is None:
                parent = _maya_main_window()
            super(HalfRotationDialog, self).__init__(parent)
            self.setWindowTitle("Create Half Rotation Joint")
            self.setObjectName("halfRotationDialog")
            self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
            self._create_widgets()
            self._create_layout()
        def _create_widgets(self):
            self.skip_x_checkbox = QtWidgets.QCheckBox("Skip connecting rotate X")
            self.skip_x_checkbox.setChecked(_get_skip_rotate_x_preference())
            self.create_button = QtWidgets.QPushButton("Create")
            self.close_button = QtWidgets.QPushButton("Close")
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
    def show_half_rotation_dialog():  # pragma: no cover - Maya環墁EE
        raise RuntimeError("PySide2 modules are not available.")
if __name__ == "__main__":
    create_half_rotation_joint()
