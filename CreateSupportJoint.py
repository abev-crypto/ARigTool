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
    if short.endswith("_D"):
        short = short[:-2]
    new_name = _unique_name(f"{short}_Sup")

    cmds.undoInfo(openChunk=True)
    try:
        cmds.select(clear=True)
        new_joint = cmds.duplicate(source_joint, po=True, n=new_name)[0]
        cmds.parent(new_joint, source_joint)
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
