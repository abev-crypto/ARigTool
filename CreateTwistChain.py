# -*- coding: utf-8 -*-
import maya.cmds as cmds
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

try:
    from PySide2 import QtCore, QtWidgets
    from shiboken2 import wrapInstance
    import maya.OpenMayaUI as omui
except Exception:  # pragma: no cover - Maya環墁EではUI関連モジュールが利用できなぁE合がある
    QtCore = QtWidgets = omui = wrapInstance = None


def _maya_main_window():
    if omui is None:
        raise RuntimeError("Unable to obtain Maya main window.")
    ptr = omui.MQtUtil.mainWindow()
    if ptr is None:
        raise RuntimeError("Unable to obtain Maya main window.")
    return wrapInstance(int(ptr), QtWidgets.QWidget)


def _is_half_joint(joint):
    short_name = joint.split("|")[-1]
    lowered = short_name.lower()
    return (
        "_half_inf" in lowered
        or "_half" in lowered
    )


def _is_support_joint(joint):
    short_name = joint.split("|")[-1]
    lowered = short_name.lower()
    return "_sup" in lowered


TWIST_LAYER = "twist_jnt"
ANIM_CURVE_TYPES: Sequence[str] = (
    "animCurveUL",
    "animCurveUA",
    "animCurveUT",
    "animCurveUU",
)
TWIST_NODE_TYPES: Set[str] = {
    "plusMinusAverage",
    "multDoubleLinear",
    "addDoubleLinear",
    "setRange",
    "condition",
}
_AXES: Tuple[str, ...] = ("X", "Y", "Z")


def _normalize_twist_axis(twist_axis: str) -> str:
    axis = (twist_axis or "X").upper()
    if axis not in _AXES:
        raise ValueError("Invalid twist axis: {0}".format(twist_axis))
    return axis


def _list_base_children(joint):
    children = cmds.listRelatives(joint, c=True, type="joint") or []
    bases = []
    for child in children:
        if _is_half_joint(child):
            continue
        if _is_support_joint(child):
            continue
        short_name = child.split("|")[-1]
        lowered = short_name.lower()
        if "twistroot" in lowered:
            continue
        if "twist" in lowered:
            continue
        if cmds.attributeQuery("twistWeight", node=child, exists=True):
            continue
        bases.append(child)
    return bases


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


def _list_twist_children(joint):
    result = []
    children = cmds.listRelatives(joint, c=True, type="joint") or []
    for child in children:
        if cmds.attributeQuery("twistWeight", node=child, exists=True):
            result.append(child)
    if result:
        return result

    reverse_root = _find_reverse_twist_root(joint)
    if not reverse_root:
        return result

    children = cmds.listRelatives(reverse_root, c=True, type="joint") or []
    for child in children:
        if cmds.attributeQuery("twistWeight", node=child, exists=True):
            result.append(child)
    return result


def _detect_twist_axis_from_joints(twist_joints: Sequence[str]) -> str:
    for joint in twist_joints:
        for axis in _AXES:
            rotate_attr = joint + ".rotate" + axis
            connections = cmds.listConnections(rotate_attr, s=True, d=False, p=True) or []
            for plug in connections:
                node = plug.split(".")[0]
                if cmds.nodeType(node) in TWIST_NODE_TYPES:
                    return axis
    return "X"


def _create_standard_twist_chain(
    start,
    ref,
    base_tag,
    start_short,
    length,
    base_radius,
    count,
    scale_at_90,
    twist_axis,
):
    twist_axis = _normalize_twist_axis(twist_axis)
    rotate_attr = ".rotate" + twist_axis
    other_axes = tuple(ax for ax in _AXES if ax != twist_axis)

    pma_sub = cmds.createNode("plusMinusAverage", n=f"{base_tag}_twistDelta_PMA")
    cmds.setAttr(pma_sub + ".operation", 2)  # subtract
    cmds.connectAttr(ref + rotate_attr, pma_sub + ".input1D[0]", f=True)
    cmds.connectAttr(start + rotate_attr, pma_sub + ".input1D[1]", f=True)

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
    for idx in range(count):
        step_index = idx + 1
        ratio = float(step_index) / float(count + 1)

        suffix = f"{step_index:02d}"
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

        for ax in _AXES:
            try:
                cmds.setAttr(j + ".rotate" + ax, l=False, k=True, cb=True)
            except Exception:
                pass

        if cmds.objExists(j + ".segmentScaleCompensate"):
            try:
                cmds.setAttr(j + ".segmentScaleCompensate", 0)
            except Exception:
                pass

        node_suffix = f"{step_index:02d}"

        md = cmds.createNode("multDoubleLinear", n=f"{base_tag}_twist{node_suffix}_MD")
        cmds.connectAttr(pma_sub + ".output1D", md + ".input1", f=True)

        pma_add = cmds.createNode("plusMinusAverage", n=f"{base_tag}_twist{node_suffix}_PMA")
        cmds.setAttr(pma_add + ".operation", 1)
        cmds.connectAttr(start + rotate_attr, pma_add + ".input1D[0]", f=True)
        cmds.connectAttr(md + ".output", pma_add + ".input1D[1]", f=True)

        cmds.connectAttr(pma_add + ".output1D", j + rotate_attr, f=True)
        for ax in other_axes:
            cmds.setAttr(j + ".rotate" + ax, l=True, k=False, cb=False)

        ratio_attr = "twistWeight"
        if not cmds.attributeQuery(ratio_attr, node=j, exists=True):
            cmds.addAttr(j, ln=ratio_attr, at="double", min=0.0, dv=ratio)
            cmds.setAttr(j + "." + ratio_attr, e=True, k=True)
        cmds.setAttr(j + "." + ratio_attr, ratio)
        cmds.connectAttr(j + "." + ratio_attr, md + ".input2", f=True)

        scale_factor = float(step_index)
        scale_ratio = (scale_at_90 - 1) * scale_factor / float(count) + 1 if count else 1.0
        scale_attr = "twistScaleMax"
        if not cmds.attributeQuery(scale_attr, node=j, exists=True):
            cmds.addAttr(j, ln=scale_attr, at="double", min=0.0, dv=scale_ratio)
            cmds.setAttr(j + "." + scale_attr, e=True, k=True)
        else:
            cmds.setAttr(j + "." + scale_attr, scale_ratio)

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

    return created


def _create_reverse_twist_chain(
    start,
    base_tag,
    start_short,
    length,
    base_radius,
    count,
    scale_at_90,
    twist_axis,
    start_parent=None,
):
    twist_axis = _normalize_twist_axis(twist_axis)
    rotate_attr = ".rotate" + twist_axis
    other_axes = tuple(ax for ax in _AXES if ax != twist_axis)

    abs_neg = cmds.createNode("multDoubleLinear", n=f"{base_tag}_twistAbsNeg_MDL")
    cmds.setAttr(abs_neg + ".input2", -1)
    cmds.connectAttr(start + rotate_attr, abs_neg + ".input1", f=True)

    cond_abs = cmds.createNode("condition", n=f"{base_tag}_twistAbs_COND")
    cmds.setAttr(cond_abs + ".operation", 4)  # Less Than
    cmds.setAttr(cond_abs + ".secondTerm", 0)
    cmds.connectAttr(start + rotate_attr, cond_abs + ".firstTerm", f=True)
    cmds.connectAttr(abs_neg + ".output", cond_abs + ".colorIfTrueR", f=True)
    cmds.connectAttr(start + rotate_attr, cond_abs + ".colorIfFalseR", f=True)

    twist_range = cmds.createNode("setRange", n=f"{base_tag}_twistAmount_SR")
    cmds.setAttr(twist_range + ".minX", 0)
    cmds.setAttr(twist_range + ".maxX", 1)
    cmds.setAttr(twist_range + ".oldMinX", 0)
    cmds.setAttr(twist_range + ".oldMaxX", 90)
    cmds.connectAttr(cond_abs + ".outColorR", twist_range + ".valueX", f=True)

    created = []

    root_name = f"{start_short}_twistRoot"
    root = cmds.duplicate(start, po=True, n=root_name)[0]

    if cmds.attributeQuery("radius", node=root, exists=True):
        try:
            cmds.setAttr(root + ".radius", base_radius * 2.0)
        except Exception:
            pass

    try:
        cmds.parent(root, w=True)
    except Exception:
        pass

    if start_parent:
        try:
            cmds.parent(root, start_parent)
        except Exception:
            pass

    if cmds.objExists(root + ".segmentScaleCompensate"):
        try:
            cmds.setAttr(root + ".segmentScaleCompensate", 0)
        except Exception:
            pass

    try:
        cmds.setAttr(root + rotate_attr, l=False, k=True, cb=True)
        cmds.setAttr(root + rotate_attr, 0)
        cmds.setAttr(root + rotate_attr, l=True, k=False, cb=False)
    except Exception:
        pass

    for ax in other_axes:
        try:
            cmds.setAttr(root + ".rotate" + ax, l=False, k=True, cb=True)
            cmds.connectAttr(start + ".rotate" + ax, root + ".rotate" + ax, f=True)
        except Exception:
            pass

    created.append(root)

    for idx in range(1, count + 1):
        ratio = float(idx) / float(count + 1)
        suffix = f"{idx:02d}"
        jnt_name = f"{start_short}_twist{suffix}"
        j = cmds.duplicate(start, po=True, n=jnt_name)[0]

        if cmds.attributeQuery("radius", node=j, exists=True):
            try:
                cmds.setAttr(j + ".radius", base_radius * 2.0)
            except Exception:
                pass

        try:
            cmds.parent(j, root)
        except Exception:
            pass

        cmds.setAttr(j + ".translateY", 0)
        cmds.setAttr(j + ".translateZ", 0)
        cmds.setAttr(j + ".translateX", length * ratio)

        try:
            cmds.setAttr(j + rotate_attr, l=False, k=True, cb=True)
        except Exception:
            pass

        for ax in other_axes:
            try:
                cmds.setAttr(j + ".rotate" + ax, l=True, k=False, cb=False)
            except Exception:
                pass

        if cmds.objExists(j + ".segmentScaleCompensate"):
            try:
                cmds.setAttr(j + ".segmentScaleCompensate", 0)
            except Exception:
                pass

        ratio_attr = "twistWeight"
        if not cmds.attributeQuery(ratio_attr, node=j, exists=True):
            cmds.addAttr(j, ln=ratio_attr, at="double", min=0.0, dv=ratio)
            cmds.setAttr(j + "." + ratio_attr, e=True, k=True)
        cmds.setAttr(j + "." + ratio_attr, ratio)

        md = cmds.createNode("multDoubleLinear", n=f"{base_tag}_twist{suffix}_MD")
        cmds.connectAttr(start + rotate_attr, md + ".input1", f=True)
        cmds.connectAttr(j + "." + ratio_attr, md + ".input2", f=True)
        cmds.connectAttr(md + ".output", j + rotate_attr, f=True)

        scale_factor = float(idx)
        scale_ratio = (scale_at_90 - 1) * scale_factor / float(count) + 1 if count else 1.0
        scale_attr = "twistScaleMax"
        if not cmds.attributeQuery(scale_attr, node=j, exists=True):
            cmds.addAttr(j, ln=scale_attr, at="double", min=0.0, dv=scale_ratio)
            cmds.setAttr(j + "." + scale_attr, e=True, k=True)
        else:
            cmds.setAttr(j + "." + scale_attr, scale_ratio)

        delta_add = cmds.createNode("addDoubleLinear", n=f"{base_tag}_twist{suffix}_scaleDelta_ADL")
        cmds.connectAttr(j + "." + scale_attr, delta_add + ".input1", f=True)
        cmds.setAttr(delta_add + ".input2", -1)

        scale_md = cmds.createNode("multDoubleLinear", n=f"{base_tag}_twist{suffix}_scale_MD")
        cmds.connectAttr(twist_range + ".outValueX", scale_md + ".input1", f=True)
        cmds.connectAttr(delta_add + ".output", scale_md + ".input2", f=True)

        scale_add = cmds.createNode("addDoubleLinear", n=f"{base_tag}_twist{suffix}_scale_ADL")
        cmds.connectAttr(scale_md + ".output", scale_add + ".input1", f=True)
        cmds.setAttr(scale_add + ".input2", 1)

        cmds.connectAttr(scale_add + ".output", j + ".scaleY", f=True)
        cmds.connectAttr(scale_add + ".output", j + ".scaleZ", f=True)

        created.append(j)

    return created


def _create_twist_chain_internal(
    start: str,
    *,
    count: int = 4,
    name_tag: Optional[str] = None,
    scale_at_90: float = 1.2,
    reverse_twist: bool = False,
    manage_display_layer: bool = True,
    allow_start_rename: bool = True,
    twist_axis: str = "X",
) -> List[str]:
    twist_axis = _normalize_twist_axis(twist_axis)

    if not cmds.objExists(start):
        cmds.warning("Start joint {0} does not exist; skipping.".format(start))
        return []

    existing_twists = _list_twist_joints(start)
    if existing_twists:
        reverse_root = _find_reverse_twist_root(start)
        if reverse_root:
            message = "{0} already has a reverse twist chain; skipping.".format(start)
        else:
            message = "Twist joints already exist under {0}; skipping.".format(start)
        cmds.warning(message)
        return []

    base_candidates = _list_base_children(start)
    if not base_candidates:
        cmds.warning("No base joint found under {0}; skipping twist creation.".format(start))
        return []
    if len(base_candidates) > 1:
        cmds.warning("Multiple base joints found under {0}; skipping twist creation.".format(start))
        return []

    ref = base_candidates[0]

    start_short = start.split("|")[-1]
    base_tag = name_tag or start_short

    p_start = cmds.xform(start, q=True, ws=True, t=True)
    p_ref = cmds.xform(ref, q=True, ws=True, t=True)
    length = ((p_ref[0] - p_start[0]) ** 2 + (p_ref[1] - p_start[1]) ** 2 + (p_ref[2] - p_start[2]) ** 2) ** 0.5
    if length < 1e-5:
        cmds.error("Start and reference joints share the same position.")

    base_radius = 1.0
    if cmds.attributeQuery("radius", node=start, exists=True):
        try:
            base_radius = cmds.getAttr(start + ".radius")
        except Exception:
            base_radius = 1.0

    start_parent = cmds.listRelatives(start, p=True, pa=True) or []
    start_parent = start_parent[0] if start_parent else None

    if reverse_twist:
        created = _create_reverse_twist_chain(
            start=start,
            base_tag=base_tag,
            start_short=start_short,
            length=length,
            base_radius=base_radius,
            count=count,
            scale_at_90=scale_at_90,
            twist_axis=twist_axis,
            start_parent=start_parent,
        )
    else:
        created = _create_standard_twist_chain(
            start=start,
            ref=ref,
            base_tag=base_tag,
            start_short=start_short,
            length=length,
            base_radius=base_radius,
            count=count,
            scale_at_90=scale_at_90,
            twist_axis=twist_axis,
        )

    if manage_display_layer and created:
        layer_name = TWIST_LAYER
        if cmds.objExists(layer_name):
            if cmds.nodeType(layer_name) != "displayLayer":
                cmds.error("'{0}' is not a displayLayer.".format(layer_name))
            layer = layer_name
        else:
            layer = cmds.createDisplayLayer(name=layer_name, empty=True, nr=True)
        try:
            cmds.editDisplayLayerMembers(layer, created, nr=True)
        except Exception:
            pass

    if reverse_twist and allow_start_rename and created:
        start_short_name = start.split("|")[-1]
        if not start_short_name.endswith("_D"):
            new_short_name = start_short_name + "_D"
            if cmds.objExists(new_short_name):
                cmds.warning(
                    "{0} + '_D' conflicts with existing name {1}; skipping.".format(
                        start_short_name, new_short_name
                    )
                )
            else:
                try:
                    cmds.rename(start, new_short_name)
                except RuntimeError as exc:
                    cmds.warning("Failed to rename {0}: {1}".format(start_short_name, exc))

    return created or []


def create_twist_chain(
    count=4,
    name_tag="Twist",
    scale_at_90=1.2,
    reverse_twist=False,
    twist_axis="X",
):
    sel = cmds.ls(sl=True, type="joint") or []
    if not sel:
        cmds.error("Select at least one joint.")

    start = sel[0]

    cmds.undoInfo(openChunk=True, chunkName="CreateTwistChain")
    try:
        created = _create_twist_chain_internal(
            start,
            count=count,
            name_tag=name_tag,
            scale_at_90=scale_at_90,
            reverse_twist=reverse_twist,
            allow_start_rename=True,
            twist_axis=twist_axis,
        )
    finally:
        cmds.undoInfo(closeChunk=True)

    if created:
        cmds.select(created, r=True)
        print("[Twist] created:", created)
    return created

def create_twist_chain_for_joint(
    start: str,
    *,
    count: int = 4,
    name_tag: Optional[str] = None,
    scale_at_90: float = 1.2,
    reverse_twist: bool = False,
    select_result: bool = False,
    allow_start_rename: bool = False,
    use_undo_chunk: bool = True,
    twist_axis: str = "X",
) -> List[str]:
    if use_undo_chunk:
        cmds.undoInfo(openChunk=True, chunkName="CreateTwistChain")
    try:
        created = _create_twist_chain_internal(
            start,
            count=count,
            name_tag=name_tag,
            scale_at_90=scale_at_90,
            reverse_twist=reverse_twist,
            allow_start_rename=allow_start_rename,
            twist_axis=twist_axis,
        )
    finally:
        if use_undo_chunk:
            cmds.undoInfo(closeChunk=True)
    if select_result and created:
        cmds.select(created, r=True)
    return created

def collect_twist_chain_data(start: str) -> Optional[Dict[str, object]]:
    if not cmds.objExists(start):
        return None

    reverse_root = _find_reverse_twist_root(start)
    twist_parent = reverse_root if reverse_root else start

    children = cmds.listRelatives(twist_parent, c=True, type="joint") or []
    twist_joints = [child for child in children if cmds.attributeQuery("twistWeight", node=child, exists=True)]
    if not twist_joints:
        return None

    try:
        twist_joints.sort(key=lambda x: cmds.getAttr(x + ".twistWeight"))
    except Exception:
        twist_joints.sort()

    weights: List[float] = []
    scales: List[float] = []
    driven: Dict[str, Sequence[str]] = {}
    for joint in twist_joints:
        try:
            weights.append(cmds.getAttr(joint + ".twistWeight"))
        except Exception:
            weights.append(0.0)
        if cmds.attributeQuery("twistScaleMax", node=joint, exists=True):
            try:
                scales.append(cmds.getAttr(joint + ".twistScaleMax"))
            except Exception:
                scales.append(1.0)
        else:
            scales.append(1.0)
        driven[joint] = _list_driven_attributes(joint)

    joint_count = len(twist_joints)
    twist_axis = _detect_twist_axis_from_joints(twist_joints)

    return {
        "start": start,
        "weights": weights,
        "scales": scales,
        "count": joint_count,
        "joint_count": joint_count,
        "joints": list(twist_joints),
        "driven": driven,
        "reverse_twist": bool(reverse_root),
        "reverse_root": reverse_root,
        "reverse_root_driven": _list_driven_attributes(reverse_root) if reverse_root else [],
        "twist_axis": twist_axis,
    }


def cleanup_twist_chain(start: str) -> None:
    twist_joints = _list_twist_children(start)
    reverse_root = _find_reverse_twist_root(start)
    if not twist_joints and not reverse_root:
        return

    nodes_to_delete: Set[str] = set()
    to_visit: List[str] = list(twist_joints)
    while to_visit:
        node = to_visit.pop()
        for attr in (".rotateX", ".rotateY", ".rotateZ", ".scaleY", ".scaleZ"):
            plugs = cmds.listConnections(node + attr, s=True, d=False, p=True) or []
            for plug in plugs:
                src_node = plug.split(".")[0]
                if src_node == start:
                    continue
                if cmds.nodeType(src_node) in TWIST_NODE_TYPES and src_node not in nodes_to_delete:
                    nodes_to_delete.add(src_node)
                    upstream = cmds.listConnections(src_node, s=True, d=False) or []
                    for up in upstream:
                        if cmds.nodeType(up) in TWIST_NODE_TYPES and up not in nodes_to_delete:
                            to_visit.append(up)
    if nodes_to_delete:
        cmds.delete(list(nodes_to_delete))

    delete_targets = list(twist_joints)
    if reverse_root and cmds.objExists(reverse_root):
        delete_targets.append(reverse_root)

    if delete_targets:
        cmds.delete(delete_targets)


def build_twist_chain_from_data(
    target_start: str,
    data: Dict[str, object],
    *,
    copy_driven_callback: Optional[Callable[[str, str, Sequence[str]], None]] = None,
    select_result: bool = False,
    allow_start_rename: bool = False,
    show_message: bool = False,
) -> List[str]:
    if not cmds.objExists(target_start):
        cmds.warning("Target joint {0} does not exist.".format(target_start))
        return []

    joint_count = int(data.get("joint_count", 0))
    if joint_count <= 0:
        return []

    base_candidates = _list_base_children(target_start)
    if not base_candidates:
        cmds.warning("No base joint found under {0}; skipping twist mirror.".format(target_start))
        return []
    if len(base_candidates) > 1:
        cmds.warning("Multiple base joints found under {0}; skipping twist mirror.".format(target_start))
        return []

    cleanup_twist_chain(target_start)

    scales: Sequence[float] = data.get("scales") or []
    scale_at_90 = scales[-1] if scales else 1.0
    twist_count = int(data.get("count", joint_count))
    reverse_twist = bool(data.get("reverse_twist", False))
    twist_axis = data.get("twist_axis", "X")

    created_chain = create_twist_chain_for_joint(
        target_start,
        count=twist_count,
        name_tag=None,
        scale_at_90=scale_at_90,
        reverse_twist=reverse_twist,
        select_result=False,
        allow_start_rename=allow_start_rename,
        twist_axis=twist_axis,
    )
    if not created_chain:
        return []

    twist_targets = list(created_chain)
    root_joint = None
    if reverse_twist:
        if twist_targets:
            root_joint = twist_targets.pop(0)
        else:
            twist_targets = []

    twist_targets = twist_targets[:joint_count]

    weights: Sequence[float] = data.get("weights") or []
    source_joints: Sequence[str] = data.get("joints") or []
    driven_map: Dict[str, Sequence[str]] = data.get("driven") or {}

    for idx, joint in enumerate(twist_targets):
        weight = weights[idx] if idx < len(weights) else 0.0
        scale_max = scales[idx] if idx < len(scales) else 1.0
        if cmds.attributeQuery("twistWeight", node=joint, exists=True):
            try:
                cmds.setAttr(joint + ".twistWeight", float(weight))
            except Exception:
                pass
        if cmds.attributeQuery("twistScaleMax", node=joint, exists=True):
            try:
                cmds.setAttr(joint + ".twistScaleMax", float(scale_max))
            except Exception:
                pass

        if idx < len(source_joints) and copy_driven_callback:
            src_joint = source_joints[idx]
            attrs = driven_map.get(src_joint) or []
            if attrs:
                copy_driven_callback(src_joint, joint, attrs)

    if root_joint and copy_driven_callback:
        source_root = data.get("reverse_root")
        root_attrs = data.get("reverse_root_driven") or []
        if source_root and root_attrs:
            copy_driven_callback(source_root, root_joint, root_attrs)

    final_chain: List[str] = []
    if root_joint:
        final_chain.append(root_joint)
    final_chain.extend(twist_targets)
    if not final_chain:
        final_chain = list(created_chain)

    if select_result and final_chain:
        cmds.select(final_chain, add=True)

    if show_message and final_chain:
        cmds.inViewMessage(
            amg="<hl>Twist Mirror Created</hl><br>{0}".format("\n".join(final_chain)),
            pos="topCenter",
            fade=True,
        )

    return final_chain


def _list_twist_joints(base_joint):
    children = cmds.listRelatives(base_joint, c=True, type="joint") or []
    twist_joints = []
    for child in children:
        if cmds.attributeQuery("twistWeight", node=child, exists=True) and cmds.attributeQuery(
            "twistScaleMax", node=child, exists=True
        ):
            twist_joints.append(child)
    if twist_joints:
        return twist_joints

    reverse_root = _find_reverse_twist_root(base_joint)
    if not reverse_root:
        return twist_joints

    reverse_children = cmds.listRelatives(reverse_root, c=True, type="joint") or []
    for child in reverse_children:
        if cmds.attributeQuery("twistWeight", node=child, exists=True) and cmds.attributeQuery(
            "twistScaleMax", node=child, exists=True
        ):
            twist_joints.append(child)
    return twist_joints


def _find_joint_by_short_name(base_joint, short_name):
    """Find a joint that shares the same parent/namespace as *base_joint* and has *short_name*.

    Maya may return either full DAG paths or short names, so we try siblings first and then fall
    back to a global search.
    """

    parent = cmds.listRelatives(base_joint, p=True, pa=True) or []
    search_roots = []
    if parent:
        siblings = cmds.listRelatives(parent[0], c=True, type="joint", pa=True) or []
        search_roots.extend(siblings)
    matches = cmds.ls(short_name, type="joint", long=True) or []
    search_roots.extend(matches)

    for candidate in search_roots:
        if candidate.split("|")[-1] == short_name:
            return candidate
    return None


def _find_reverse_twist_root(base_joint):
    base_short = base_joint.split("|")[-1]
    if base_short.endswith("_D"):
        base_short = base_short[:-2]
    candidate_short = base_short + "_twistRoot"
    # Prefer siblings that contain "twistRoot" in their name and share the same parent
    parent = cmds.listRelatives(base_joint, p=True, pa=True) or []
    if parent:
        siblings = cmds.listRelatives(parent[0], c=True, type="joint", pa=True) or []
    else:
        siblings = cmds.ls("|*", type="joint", long=True) or []

    base_long = cmds.ls(base_joint, long=True) or [base_joint]
    base_long = base_long[0]

    for sibling in siblings:
        if not sibling or sibling == base_long:
            continue
        short_name = sibling.split("|")[-1]
        if short_name == candidate_short:
            return sibling

    for sibling in siblings:
        if not sibling or sibling == base_long:
            continue
        if "twistroot" in sibling.split("|")[-1].lower():
            return sibling

    return _find_joint_by_short_name(base_joint, candidate_short)


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
                self._populate_table([], message="Select a joint to edit.")
                return

            base = sel[0]
            twist_joints = _list_twist_joints(base)
            info_message = "Base joint {0}".format(base)

            if not twist_joints:
                reverse_root = _find_reverse_twist_root(base)
                if reverse_root:
                    twist_joints = _list_twist_joints(reverse_root)
                    if twist_joints:
                        info_message = "Base joint {0}\nReverse twist root {1}".format(base, reverse_root)

            if not twist_joints:
                self._populate_table([], message="No twist joints found under the selected joint.")
                return

            self._populate_table(twist_joints, message=info_message)

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
