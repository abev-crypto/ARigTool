# -*- coding: utf-8 -*-
"""Mirror primary joints based on naming conventions."""

import math

import maya.cmds as cmds


def _mirror_name(name):
    if "_L" in name:
        return name.replace("_L", "_R", 1)
    if "_R" in name:
        return name.replace("_R", "_L", 1)
    return None


def _uniquify(name):
    if not cmds.objExists(name):
        return name
    base = name
    index = 1
    while True:
        candidate = f"{base}{index:02d}"
        if not cmds.objExists(candidate):
            return candidate
        index += 1


def _normalize_angle(value):
    value = math.fmod(value, 360.0)
    if value > 180.0:
        value -= 360.0
    elif value < -180.0:
        value += 360.0
    return value


def _ensure_suffix(joint):
    joint_long = cmds.ls(joint, l=True)
    if not joint_long:
        return joint
    joint_long = joint_long[0]
    short = joint_long.split("|")[-1]
    if "_L" in short or "_R" in short:
        return joint_long

    pos = cmds.xform(joint_long, q=True, ws=True, t=True)
    x = pos[0] if pos else 0.0
    if abs(x) < 1e-5:
        return joint_long

    suffix = "_L" if x > 0.0 else "_R"
    new_short = short + suffix
    if cmds.objExists(new_short):
        new_short = _uniquify(new_short)
    renamed = cmds.rename(joint_long, new_short)
    return cmds.ls(renamed, l=True)[0]


def _determine_target_parent(source_joint, mirror_map):
    parents = cmds.listRelatives(source_joint, p=True, f=True) or []
    if not parents:
        return None

    parent = parents[0]
    parent_short = parent.split("|")[-1]
    if "_L" in parent_short or "_R" in parent_short:
        mapped = mirror_map.get(parent)
        if mapped:
            return mapped
        mirrored_short = _mirror_name(parent_short)
        if mirrored_short:
            candidates = cmds.ls(mirrored_short, l=True)
            if candidates:
                return candidates[0]
    return parent


def _adjust_joint_orientation(joint):
    attr = joint + ".jointOrientX"
    if cmds.objExists(attr) and not cmds.getAttr(attr, l=True):
        value = cmds.getAttr(attr)
        if value is None:
            return
        new_value = _normalize_angle(value + 180.0)
        cmds.setAttr(attr, new_value)
    else:
        try:
            cmds.rotate(180.0, 0.0, 0.0, joint, os=True, r=True)
        except Exception:
            pass


def _create_mirrored_joint(joint, mirror_map):
    joint_long = cmds.ls(joint, l=True)
    if not joint_long:
        return None
    joint_long = joint_long[0]
    short = joint_long.split("|")[-1]
    mirror_short = _mirror_name(short)
    if not mirror_short:
        return None

    existing = cmds.ls(mirror_short, l=True)
    if existing:
        cmds.warning(u"{0} は既に存在するため作成をスキップします。".format(mirror_short))
        mirror_map[joint_long] = existing[0]
        return None

    duplicated = cmds.duplicate(joint_long, po=True)[0]
    duplicated = cmds.rename(duplicated, mirror_short)
    duplicated_long = cmds.ls(duplicated, l=True)[0]

    null_name = _uniquify(mirror_short + "_MirrorNull")
    null = cmds.group(em=True, name=null_name)
    cmds.xform(null, ws=True, t=(0.0, 0.0, 0.0), ro=(0.0, 0.0, 0.0))

    cmds.parent(duplicated_long, null)
    duplicated_long = cmds.ls(duplicated_long, l=True)[0]
    cmds.setAttr(null + ".scaleX", -1.0)
    cmds.makeIdentity(null, apply=True, t=False, r=False, s=True, n=False, pn=True)
    cmds.parent(duplicated_long, w=True)
    duplicated_long = cmds.ls(duplicated_long, l=True)[0]
    cmds.delete(null)

    target_parent = _determine_target_parent(joint_long, mirror_map)
    if target_parent:
        cmds.parent(duplicated_long, target_parent)
        duplicated_long = cmds.ls(duplicated_long, l=True)[0]

    _adjust_joint_orientation(duplicated_long)
    mirror_map[joint_long] = duplicated_long
    return duplicated_long


def _mirror_joint_recursive(joint, mirror_map, created):
    joint_long = cmds.ls(joint, l=True)
    if not joint_long:
        return
    joint_long = joint_long[0]
    joint_long = _ensure_suffix(joint_long)

    mirrored = _create_mirrored_joint(joint_long, mirror_map)
    if mirrored:
        created.append(mirrored)

    children = cmds.listRelatives(joint_long, c=True, type="joint", f=True) or []
    for child in children:
        _mirror_joint_recursive(child, mirror_map, created)


def mirror_primary_joints():
    selected = cmds.ls(sl=True, type="joint", l=True) or []
    if not selected:
        cmds.warning(u"ミラーするジョイントを選択してください。")
        return

    selected_set = set(selected)
    roots = []
    for joint in selected:
        parents = cmds.listRelatives(joint, p=True, f=True) or []
        if not parents or parents[0] not in selected_set:
            roots.append(joint)

    mirror_map = {}
    created = []
    for root in roots:
        _mirror_joint_recursive(root, mirror_map, created)

    if created:
        cmds.select(created, r=True)
        try:
            cmds.inform(u"{0} 個のジョイントをミラー作成しました。".format(len(created)))
        except AttributeError:
            # cmds.inform は 2022+ で導入。存在しない場合は print のみ。
            print(u"{0} 個のジョイントをミラー作成しました。".format(len(created)))
    else:
        cmds.warning(u"新たにミラーされたジョイントはありませんでした。")
