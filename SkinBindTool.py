# -*- coding: utf-8 -*-
"""Utilities for skin binding operations used from the ARig tool UI."""

import maya.cmds as cmds


def _short_name(node):
    return node.split("|")[-1]


def _is_bind_geometry(node):
    """Return True if the node can be used as a bind target geometry."""

    if not cmds.objExists(node):
        return False

    node_type = cmds.nodeType(node)
    if node_type in {"mesh", "nurbsSurface", "lattice"}:
        return True

    if node_type != "transform":
        return False

    shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
    for shape in shapes:
        if cmds.nodeType(shape) in {"mesh", "nurbsSurface", "lattice"}:
            return True
    return False


def _collect_bind_joints(root):
    """Collect joints under the root excluding Half joints except Half_INF."""

    joints = []

    full_root = cmds.ls(root, long=True) or []
    if not full_root:
        return joints

    root_path = full_root[0]

    descendants = cmds.listRelatives(root_path, allDescendents=True, type="joint", fullPath=True) or []
    descendants = list(reversed(descendants))

    for joint in [root_path] + descendants:
        short = _short_name(joint)
        if "Half" in short and "Half_INF" not in short:
            continue
        if "_D" in short:
            continue
        joints.append(joint)

    # Remove duplicates while keeping order.
    unique = []
    seen = set()
    for joint in joints:
        if joint in seen:
            continue
        seen.add(joint)
        unique.append(joint)
    return unique


def bind_skin_excluding_half():
    """Bind the selected geometry to the joint hierarchy without Half joints."""

    selection = cmds.ls(sl=True, long=True) or []
    if not selection:
        cmds.warning(u"ジョイントのルートとバインド対象ジオメトリを選択してください。")
        return

    joint_roots = [node for node in selection if cmds.nodeType(node) == "joint"]
    if not joint_roots:
        cmds.warning(u"ジョイントのルートを少なくとも1つ選択してください。")
        return

    geometries = [node for node in selection if _is_bind_geometry(node)]
    if not geometries:
        cmds.warning(u"バインド対象のジオメトリを選択してください。")
        return

    bind_joints = []
    for root in joint_roots:
        bind_joints.extend(_collect_bind_joints(root))

    # Remove duplicates while keeping order.
    unique_joints = []
    seen = set()
    for joint in bind_joints:
        if joint in seen:
            continue
        seen.add(joint)
        unique_joints.append(joint)

    if not unique_joints:
        cmds.warning(u"バインドに使用できるジョイントが見つかりませんでした。")
        return

    original_selection = cmds.ls(sl=True, long=True) or []
    cmds.undoInfo(openChunk=True)
    try:
        for geometry in geometries:
            try:
                cmds.skinCluster(unique_joints, geometry, toSelectedBones=True)
            except RuntimeError as exc:
                cmds.warning(u"{0} のスキンバインドに失敗しました: {1}".format(_short_name(geometry), exc))
    finally:
        cmds.undoInfo(closeChunk=True)
        if original_selection:
            cmds.select(original_selection, replace=True)
        else:
            cmds.select(clear=True)

