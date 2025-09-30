# -*- coding: utf-8 -*-
"""Utility for creating support joints."""

from typing import Optional

import maya.cmds as cmds


def _short_name(node: str) -> str:
    return node.split("|")[-1]


def _unique_name(base_name: str) -> str:
    if not cmds.objExists(base_name):
        return base_name
    index = 1
    while True:
        candidate = f"{base_name}{index:02d}"
        if not cmds.objExists(candidate):
            return candidate
        index += 1


def _get_joint_radius(joint: str) -> Optional[float]:
    attr = f"{joint}.radius"
    if not cmds.objExists(attr):
        return None
    try:
        return cmds.getAttr(attr)
    except Exception:
        return None


def create_support_joint():
    """Create a support joint under the first selected joint."""
    selection = cmds.ls(sl=True, type="joint", l=True) or []
    if not selection:
        cmds.warning(u"サポートジョイントを作成するジョイントを1つ選択してください。")
        return

    source_joint = selection[0]
    short = _short_name(source_joint)
    new_name = _unique_name(f"{short}_Sup")

    world_pos = cmds.xform(source_joint, q=True, ws=True, t=True)
    world_rot = cmds.xform(source_joint, q=True, ws=True, ro=True)
    try:
        joint_orient = cmds.getAttr(f"{source_joint}.jointOrient")[0]
    except Exception:
        joint_orient = (0.0, 0.0, 0.0)
    try:
        rotate_order = cmds.getAttr(f"{source_joint}.rotateOrder")
    except Exception:
        rotate_order = 0

    cmds.undoInfo(openChunk=True)
    try:
        cmds.select(clear=True)
        new_joint = cmds.createNode("joint", name=new_name)
        cmds.xform(new_joint, ws=True, t=world_pos, ro=world_rot)
        try:
            cmds.setAttr(f"{new_joint}.jointOrient", *joint_orient)
        except Exception:
            pass
        try:
            cmds.setAttr(f"{new_joint}.rotateOrder", rotate_order)
        except Exception:
            pass

        try:
            cmds.parent(new_joint, source_joint)
        except Exception:
            cmds.warning(u"親子付けに失敗しました。手動で親子付けを行ってください。")

        for axis in ("X", "Y", "Z"):
            try:
                cmds.setAttr(f"{new_joint}.translate{axis}", 0.0)
            except Exception:
                pass
            try:
                cmds.setAttr(f"{new_joint}.rotate{axis}", 0.0)
            except Exception:
                pass

        source_radius = _get_joint_radius(source_joint)
        if source_radius is not None:
            try:
                cmds.setAttr(f"{new_joint}.radius", source_radius * 2.0)
            except Exception:
                pass

        layer_name = "support_jnt"
        if not cmds.objExists(layer_name):
            try:
                cmds.createDisplayLayer(name=layer_name, empty=True)
            except Exception:
                layer_name = None
        if layer_name:
            try:
                cmds.editDisplayLayerMembers(layer_name, new_joint, nr=True)
            except Exception:
                pass

        cmds.select(new_joint, r=True)
        cmds.inViewMessage(amg=u"<hl>{0}</hl> を作成しました".format(new_name), pos="topCenter", fade=True)
    finally:
        cmds.undoInfo(closeChunk=True)
