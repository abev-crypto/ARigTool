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
_AXES_WITH_SIGN: Tuple[str, ...] = ("X", "Y", "Z", "-X", "-Y", "-Z")


def _as_bool(value: object) -> bool:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off", ""):
            return False
    return bool(value)


def _axis_to_vector(axis: str) -> Tuple[float, float, float]:
    normalized = _normalize_twist_axis(axis)
    if normalized == "X":
        return (1.0, 0.0, 0.0)
    if normalized == "Y":
        return (0.0, 1.0, 0.0)
    if normalized == "Z":
        return (0.0, 0.0, 1.0)
    raise ValueError("Invalid axis: {0}".format(axis))


def _connect_quaternion(src_prefix: str, dst_prefix: str) -> None:
    for suffix in ("X", "Y", "Z", "W"):
        cmds.connectAttr(src_prefix + suffix, dst_prefix + suffix, f=True)


def _set_quaternion(attr_prefix: str, values: Tuple[float, float, float, float]) -> None:
    for suffix, value in zip(("X", "Y", "Z", "W"), values):
        cmds.setAttr(attr_prefix + suffix, value)


def _normalize_twist_axis_with_sign(twist_axis: Optional[str]) -> Tuple[str, int]:
    raw_axis = (twist_axis or "X").strip()
    if not raw_axis:
        raw_axis = "X"

    sign = 1
    if raw_axis[0] in "+-":
        sign = -1 if raw_axis[0] == "-" else 1
        raw_axis = raw_axis[1:]

    axis = raw_axis.upper()
    if axis not in _AXES:
        raise ValueError("Invalid twist axis: {0}".format(twist_axis))

    return axis, sign


def _normalize_twist_axis(twist_axis: str) -> str:
    axis, _ = _normalize_twist_axis_with_sign(twist_axis)
    return axis


def _format_twist_axis(axis: str, sign: int) -> str:
    return f"-{axis}" if sign < 0 else axis


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
                    sign = _detect_twist_axis_sign(plug)
                    return _format_twist_axis(axis, sign)
    return "X"


def _detect_twist_driver_axis(start_joint: str) -> str:
    for axis in _AXES:
        rotate_attr = start_joint + ".rotate" + axis
        outputs = cmds.listConnections(rotate_attr, s=False, d=True, p=True) or []
        for plug in outputs:
            node = plug.split(".")[0]
            if cmds.nodeType(node) in TWIST_NODE_TYPES:
                return axis
    return "X"


def _detect_twist_axis_sign(plug: str) -> int:
    node = plug.split(".")[0]
    node_type = cmds.nodeType(node)
    if node_type == "multDoubleLinear":
        try:
            value = cmds.getAttr(node + ".input2")
            if abs(abs(value) - 1.0) < 1e-3:
                return -1 if value < 0 else 1
        except Exception:
            pass

        upstream = cmds.listConnections(node + ".input1", s=True, d=False, p=True) or []
        for up in upstream:
            sign = _detect_twist_axis_sign(up)
            if sign in (-1, 1):
                return sign
    return 1


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
    driver_axis,
    twist_axis_sign=1,
    use_matrix_twist=False,
):
    twist_axis = _normalize_twist_axis(twist_axis)
    driver_axis = _normalize_twist_axis(driver_axis)
    twist_rotate_attr = ".rotate" + twist_axis
    driver_rotate_attr = ".rotate" + driver_axis
    other_axes = tuple(ax for ax in _AXES if ax != twist_axis)

    pma_sub = cmds.createNode("plusMinusAverage", n=f"{base_tag}_twistDelta_PMA")
    cmds.setAttr(pma_sub + ".operation", 2)  # subtract
    cmds.connectAttr(ref + driver_rotate_attr, pma_sub + ".input1D[0]", f=True)
    cmds.connectAttr(start + driver_rotate_attr, pma_sub + ".input1D[1]", f=True)

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

    roll_quat_prefix: Optional[str] = None
    if use_matrix_twist:
        axis_vector = _axis_to_vector(driver_axis)
        compose_axis = cmds.createNode("composeMatrix", n=f"{base_tag}_twistAxis_CM")
        for axis_name, value in zip(_AXES, axis_vector):
            cmds.setAttr(compose_axis + ".inputTranslate" + axis_name, value)

        compose_rot = cmds.createNode("composeMatrix", n=f"{base_tag}_twistRotate_CM")
        twist_target = ref if cmds.objExists(ref) else start
        for ax in _AXES:
            try:
                cmds.connectAttr(
                    twist_target + ".rotate" + ax,
                    compose_rot + ".inputRotate" + ax,
                    f=True,
                )
            except Exception:
                pass

        mult_matrix = cmds.createNode("multMatrix", n=f"{base_tag}_twistAxis_MTMX")
        cmds.connectAttr(compose_axis + ".outputMatrix", mult_matrix + ".matrixIn[0]", f=True)
        cmds.connectAttr(compose_rot + ".outputMatrix", mult_matrix + ".matrixIn[1]", f=True)

        decompose = cmds.createNode("decomposeMatrix", n=f"{base_tag}_twistAxis_DCM")
        cmds.connectAttr(mult_matrix + ".matrixSum", decompose + ".inputMatrix", f=True)

        angle_between = cmds.createNode("angleBetween", n=f"{base_tag}_twistAxis_AB")
        for axis_name, value in zip(_AXES, axis_vector):
            cmds.setAttr(angle_between + ".vector1" + axis_name, value)
            cmds.connectAttr(
                decompose + ".outputTranslate" + axis_name,
                angle_between + ".vector2" + axis_name,
                f=True,
            )

        axis_angle = cmds.createNode("axisAngleToQuat", n=f"{base_tag}_twistBend_AATQ")

        axis_prefix = ".axis"
        if not cmds.attributeQuery("axisX", node=axis_angle, exists=True):
            axis_prefix = ".inputAxis"

        angle_attr = ".angle"
        if not cmds.attributeQuery("angle", node=axis_angle, exists=True):
            angle_attr = ".inputAngle"

        for ax in _AXES:
            cmds.connectAttr(
                angle_between + ".axis" + ax,
                axis_angle + axis_prefix + ax,
                f=True,
            )
        cmds.connectAttr(angle_between + ".angle", axis_angle + angle_attr, f=True)

        quat_invert_bend = cmds.createNode("quatInvert", n=f"{base_tag}_twistBend_INV")
        _connect_quaternion(axis_angle + ".outputQuat", quat_invert_bend + ".inputQuat")

        euler_to_quat = cmds.createNode("eulerToQuat", n=f"{base_tag}_twistTarget_ETQ")
        for ax in _AXES:
            try:
                cmds.connectAttr(start + ".rotate" + ax, euler_to_quat + ".inputRotate" + ax, f=True)
            except Exception:
                pass
        try:
            rotate_order = cmds.getAttr(start + ".rotateOrder")
            cmds.setAttr(euler_to_quat + ".inputRotateOrder", rotate_order)
        except Exception:
            pass

        quat_prod = cmds.createNode("quatProd", n=f"{base_tag}_twistRoll_QP")
        _connect_quaternion(euler_to_quat + ".outputQuat", quat_prod + ".input1Quat")
        _connect_quaternion(quat_invert_bend + ".outputQuat", quat_prod + ".input2Quat")

        roll_quat_prefix = quat_prod + ".outputQuat"
        if twist_axis_sign < 0:
            roll_invert = cmds.createNode("quatInvert", n=f"{base_tag}_twistRollSign_INV")
            _connect_quaternion(roll_quat_prefix, roll_invert + ".inputQuat")
            roll_quat_prefix = roll_invert + ".outputQuat"

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

        ratio_attr = "twistWeight"
        if not cmds.attributeQuery(ratio_attr, node=j, exists=True):
            cmds.addAttr(j, ln=ratio_attr, at="double", min=0.0, dv=ratio)
            cmds.setAttr(j + "." + ratio_attr, e=True, k=True)
        cmds.setAttr(j + "." + ratio_attr, ratio)

        if use_matrix_twist:
            if roll_quat_prefix is None:
                raise RuntimeError("Matrix-based twist setup is not available.")

            for ax in _AXES:
                try:
                    cmds.setAttr(j + ".rotate" + ax, l=False, k=False, cb=False)
                except Exception:
                    pass

            quat_slerp = cmds.createNode("quatSlerp", n=f"{base_tag}_twist{node_suffix}_SLERP")
            _set_quaternion(quat_slerp + ".input1Quat", (0.0, 0.0, 0.0, 1.0))
            _connect_quaternion(roll_quat_prefix, quat_slerp + ".input2Quat")
            cmds.connectAttr(j + "." + ratio_attr, quat_slerp + ".inputT", f=True)

            quat_to_euler = cmds.createNode("quatToEuler", n=f"{base_tag}_twist{node_suffix}_QTE")
            _connect_quaternion(quat_slerp + ".outputQuat", quat_to_euler + ".inputQuat")
            try:
                rotate_order = cmds.getAttr(j + ".rotateOrder")
                cmds.setAttr(quat_to_euler + ".inputRotateOrder", rotate_order)
            except Exception:
                pass

            for ax in _AXES:
                cmds.connectAttr(quat_to_euler + ".outputRotate" + ax, j + ".rotate" + ax, f=True)
                try:
                    cmds.setAttr(j + ".rotate" + ax, l=True, k=False, cb=False)
                except Exception:
                    pass
        else:
            md = cmds.createNode("multDoubleLinear", n=f"{base_tag}_twist{node_suffix}_MD")
            cmds.connectAttr(pma_sub + ".output1D", md + ".input1", f=True)

            pma_add = cmds.createNode("plusMinusAverage", n=f"{base_tag}_twist{node_suffix}_PMA")
            cmds.setAttr(pma_add + ".operation", 1)
            cmds.connectAttr(start + driver_rotate_attr, pma_add + ".input1D[0]", f=True)
            cmds.connectAttr(md + ".output", pma_add + ".input1D[1]", f=True)

            axis_sign_md = cmds.createNode(
                "multDoubleLinear", n=f"{base_tag}_twist{node_suffix}_axis_MD"
            )
            cmds.setAttr(axis_sign_md + ".input2", twist_axis_sign)
            cmds.connectAttr(pma_add + ".output1D", axis_sign_md + ".input1", f=True)
            cmds.connectAttr(axis_sign_md + ".output", j + twist_rotate_attr, f=True)
            for ax in other_axes:
                cmds.setAttr(j + ".rotate" + ax, l=True, k=False, cb=False)

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
    driver_axis,
    start_parent=None,
    twist_axis_sign=1,
):
    twist_axis = _normalize_twist_axis(twist_axis)
    driver_axis = _normalize_twist_axis(driver_axis)
    twist_rotate_attr = ".rotate" + twist_axis
    driver_rotate_attr = ".rotate" + driver_axis
    other_axes = tuple(ax for ax in _AXES if ax != twist_axis)

    abs_neg = cmds.createNode("multDoubleLinear", n=f"{base_tag}_twistAbsNeg_MDL")
    cmds.setAttr(abs_neg + ".input2", -1)
    cmds.connectAttr(start + driver_rotate_attr, abs_neg + ".input1", f=True)

    cond_abs = cmds.createNode("condition", n=f"{base_tag}_twistAbs_COND")
    cmds.setAttr(cond_abs + ".operation", 4)  # Less Than
    cmds.setAttr(cond_abs + ".secondTerm", 0)
    cmds.connectAttr(start + driver_rotate_attr, cond_abs + ".firstTerm", f=True)
    cmds.connectAttr(abs_neg + ".output", cond_abs + ".colorIfTrueR", f=True)
    cmds.connectAttr(start + driver_rotate_attr, cond_abs + ".colorIfFalseR", f=True)

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
        cmds.setAttr(root + twist_rotate_attr, l=False, k=True, cb=True)
        cmds.setAttr(root + twist_rotate_attr, 0)
        cmds.setAttr(root + twist_rotate_attr, l=True, k=False, cb=False)
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
            cmds.setAttr(j + twist_rotate_attr, l=False, k=True, cb=True)
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
        cmds.connectAttr(start + driver_rotate_attr, md + ".input1", f=True)
        cmds.connectAttr(j + "." + ratio_attr, md + ".input2", f=True)
        axis_sign_md = cmds.createNode(
            "multDoubleLinear", n=f"{base_tag}_twist{suffix}_axis_MD"
        )
        cmds.setAttr(axis_sign_md + ".input2", twist_axis_sign)
        cmds.connectAttr(md + ".output", axis_sign_md + ".input1", f=True)
        cmds.connectAttr(axis_sign_md + ".output", j + twist_rotate_attr, f=True)

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
    driver_axis: Optional[str] = None,
    twist_axis_sign: int = 1,
    use_matrix_twist: bool = False,
) -> List[str]:
    reverse_twist = _as_bool(reverse_twist)
    use_matrix_twist = _as_bool(use_matrix_twist)
    twist_axis = _normalize_twist_axis(twist_axis)
    driver_axis = _normalize_twist_axis(driver_axis or twist_axis)

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

    if reverse_twist and use_matrix_twist:
        cmds.warning(
            "Matrix-based twist is not supported with reverse twist; falling back to the legacy setup."
        )
        use_matrix_twist = False

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
            driver_axis=driver_axis,
            twist_axis_sign=twist_axis_sign,
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
            driver_axis=driver_axis,
            twist_axis_sign=twist_axis_sign,
            use_matrix_twist=use_matrix_twist,
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
    driver_axis=None,
    use_matrix_twist=False,
):
    """Create a twist chain for the first selected joint.

    Args:
        count: Number of twist joints to insert between the start and the
            referenced child joint.
        name_tag: Optional tag appended to the generated node names.
        scale_at_90: Multiplier applied to the twist joint scale values when
            the driving rotation reaches 90 degrees.
        reverse_twist: When ``True`` a reverse twist setup is created instead
            of the forward chain.
        twist_axis: Axis that will receive the computed twist on the generated
            joints. The value is case-insensitive and may optionally be
            prefixed with ``-`` to invert the result (for example ``"-X"``).
        driver_axis: Axis from the target joint that will be sampled to drive
            the twist computation. When ``None`` the value of ``twist_axis`` is
            used.
        use_matrix_twist: When ``True`` the twist rotation is extracted using
            a matrix/quaternion based workflow that isolates bend rotation
            before distributing the remaining roll.
    """

    sel = cmds.ls(sl=True, type="joint") or []
    if not sel:
        cmds.error("Select at least one joint.")

    start = sel[0]
    normalized_twist_axis, twist_axis_sign = _normalize_twist_axis_with_sign(twist_axis)
    normalized_driver_axis = (
        _normalize_twist_axis(driver_axis) if driver_axis else normalized_twist_axis
    )
    display_twist_axis = _format_twist_axis(normalized_twist_axis, twist_axis_sign)

    cmds.undoInfo(openChunk=True, chunkName="CreateTwistChain")
    try:
        created = _create_twist_chain_internal(
            start,
            count=count,
            name_tag=name_tag,
            scale_at_90=scale_at_90,
            reverse_twist=reverse_twist,
            allow_start_rename=True,
            twist_axis=normalized_twist_axis,
            driver_axis=normalized_driver_axis,
            twist_axis_sign=twist_axis_sign,
            use_matrix_twist=use_matrix_twist,
        )
    finally:
        cmds.undoInfo(closeChunk=True)

    if created:
        cmds.select(created, r=True)
        print(
            "[Twist] created (twist axis {0}, driver axis {1}): {2}".format(
                display_twist_axis,
                normalized_driver_axis,
                created,
            )
        )
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
    driver_axis: Optional[str] = None,
    use_matrix_twist: bool = False,
) -> List[str]:
    normalized_twist_axis, twist_axis_sign = _normalize_twist_axis_with_sign(twist_axis)
    normalized_driver_axis = (
        _normalize_twist_axis(driver_axis) if driver_axis else normalized_twist_axis
    )

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
            twist_axis=normalized_twist_axis,
            driver_axis=normalized_driver_axis,
            twist_axis_sign=twist_axis_sign,
            use_matrix_twist=use_matrix_twist,
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
    driver_axis = _detect_twist_driver_axis(start)

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
        "driver_axis": driver_axis,
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
    reverse_twist = _as_bool(data.get("reverse_twist", False))
    twist_axis = data.get("twist_axis", "X")
    driver_axis = data.get("driver_axis") or twist_axis

    created_chain = create_twist_chain_for_joint(
        target_start,
        count=twist_count,
        name_tag=None,
        scale_at_90=scale_at_90,
        reverse_twist=reverse_twist,
        select_result=False,
        allow_start_rename=allow_start_rename,
        twist_axis=twist_axis,
        driver_axis=driver_axis,
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

            self._current_base_joint: Optional[str] = None
            self._current_reverse_twist: bool = False
            self._current_twist_axis: str = "X"
            self._current_driver_axis: str = "X"

            self._refresh_data()

        def _create_widgets(self):
            self.info_label = QtWidgets.QLabel("")

            self.axis_label = QtWidgets.QLabel(u"ツイスト軸:")
            self.axis_combo = QtWidgets.QComboBox()
            self.axis_combo.addItems(list(_AXES_WITH_SIGN))
            self.axis_combo.setEnabled(False)
            self.axis_combo.setToolTip(
                u"生成されるツイストジョイントの回転軸を選択します。"
            )

            self.driver_axis_label = QtWidgets.QLabel(u"ターゲット軸:")
            self.driver_axis_combo = QtWidgets.QComboBox()
            self.driver_axis_combo.addItems(list(_AXES))
            self.driver_axis_combo.setEnabled(False)
            self.driver_axis_combo.setToolTip(
                u"ターゲットジョイントから参照する回転軸を選択します。"
            )

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

            axis_layout = QtWidgets.QGridLayout()
            axis_layout.addWidget(self.axis_label, 0, 0)
            axis_layout.addWidget(self.axis_combo, 0, 1)
            axis_layout.addWidget(self.driver_axis_label, 1, 0)
            axis_layout.addWidget(self.driver_axis_combo, 1, 1)
            axis_layout.setColumnStretch(1, 1)
            main_layout.addLayout(axis_layout)

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
            reverse_twist = False

            if not twist_joints:
                reverse_root = _find_reverse_twist_root(base)
                if reverse_root:
                    twist_joints = _list_twist_joints(reverse_root)
                    if twist_joints:
                        info_message = "Base joint {0}\nReverse twist root {1}".format(base, reverse_root)
                        reverse_twist = True

            if not twist_joints:
                self._populate_table([], message="No twist joints found under the selected joint.")
                return

            twist_axis = _detect_twist_axis_from_joints(twist_joints)
            driver_axis = _detect_twist_driver_axis(base)

            self._populate_table(
                twist_joints,
                message=info_message,
                base_joint=base,
                twist_axis=twist_axis,
                driver_axis=driver_axis,
                reverse_twist=reverse_twist,
            )

        def _populate_table(
            self,
            joints,
            message="",
            *,
            base_joint: Optional[str] = None,
            twist_axis: Optional[str] = None,
            driver_axis: Optional[str] = None,
            reverse_twist: bool = False,
        ):
            self.table.setRowCount(0)
            self.info_label.setText(message)
            self.table.setEnabled(bool(joints))

            if joints:
                try:
                    normalized_twist_axis, twist_sign = _normalize_twist_axis_with_sign(
                        twist_axis or "X"
                    )
                except ValueError:
                    normalized_twist_axis, twist_sign = "X", 1
                try:
                    normalized_driver_axis = _normalize_twist_axis(
                        driver_axis or normalized_twist_axis
                    )
                except ValueError:
                    normalized_driver_axis = normalized_twist_axis

                self.axis_combo.setEnabled(True)
                display_twist_axis = _format_twist_axis(
                    normalized_twist_axis, twist_sign
                )
                twist_index = self.axis_combo.findText(
                    display_twist_axis, QtCore.Qt.MatchFixedString
                )
                if twist_index < 0:
                    twist_index = 0
                self.axis_combo.setCurrentIndex(twist_index)

                self.driver_axis_combo.setEnabled(True)
                driver_index = self.driver_axis_combo.findText(
                    normalized_driver_axis, QtCore.Qt.MatchFixedString
                )
                if driver_index < 0:
                    driver_index = 0
                self.driver_axis_combo.setCurrentIndex(driver_index)

                self._current_base_joint = base_joint
                self._current_reverse_twist = _as_bool(reverse_twist)
                self._current_twist_axis = display_twist_axis
                self._current_driver_axis = normalized_driver_axis
            else:
                self.axis_combo.setEnabled(False)
                self.driver_axis_combo.setEnabled(False)
                self.axis_combo.setCurrentIndex(0)
                self.driver_axis_combo.setCurrentIndex(0)
                self._current_base_joint = None
                self._current_reverse_twist = False
                self._current_twist_axis = "X"
                self._current_driver_axis = "X"

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
            row_count = self.table.rowCount()
            if not self._current_base_joint or row_count <= 0:
                return

            try:
                (
                    selected_twist_axis,
                    selected_twist_sign,
                ) = _normalize_twist_axis_with_sign(self.axis_combo.currentText())
            except ValueError:
                selected_twist_axis, selected_twist_sign = "X", 1

            try:
                selected_driver_axis = _normalize_twist_axis(
                    self.driver_axis_combo.currentText()
                )
            except ValueError:
                selected_driver_axis = selected_twist_axis

            selected_twist_axis_display = _format_twist_axis(
                selected_twist_axis, selected_twist_sign
            )
            axes_changed = (
                selected_twist_axis_display != self._current_twist_axis
                or selected_driver_axis != self._current_driver_axis
            )

            weights: List[float] = []
            scales: List[float] = []

            for row in range(row_count):
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

                weights.append(weight_value)
                scales.append(scale_value)

                if not axes_changed:
                    try:
                        cmds.setAttr(joint + ".twistWeight", weight_value)
                    except Exception:
                        pass
                    try:
                        cmds.setAttr(joint + ".twistScaleMax", scale_value)
                    except Exception:
                        pass

            if not axes_changed:
                return

            base_joint = self._current_base_joint
            count = len(weights)
            if count <= 0:
                return

            scale_at_90 = scales[-1] if scales else 1.0

            cmds.undoInfo(openChunk=True, chunkName="TwistChainEditorAxisChange")
            try:
                cleanup_twist_chain(base_joint)
                new_chain = create_twist_chain_for_joint(
                    base_joint,
                    count=count,
                    name_tag=None,
                    scale_at_90=scale_at_90,
                    reverse_twist=self._current_reverse_twist,
                    select_result=False,
                    allow_start_rename=False,
                    use_undo_chunk=False,
                    twist_axis=selected_twist_axis_display,
                    driver_axis=selected_driver_axis,
                )

                if not new_chain:
                    cmds.warning("Failed to rebuild twist chain for {0}.".format(base_joint))
                    return

                new_twist_joints = [
                    j for j in new_chain if cmds.attributeQuery("twistWeight", node=j, exists=True)
                ]

                for idx, joint in enumerate(new_twist_joints):
                    if idx >= len(weights):
                        break
                    try:
                        cmds.setAttr(joint + ".twistWeight", float(weights[idx]))
                    except Exception:
                        pass
                    try:
                        cmds.setAttr(joint + ".twistScaleMax", float(scales[idx]))
                    except Exception:
                        pass
            finally:
                cmds.undoInfo(closeChunk=True)

            self._refresh_data()

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
