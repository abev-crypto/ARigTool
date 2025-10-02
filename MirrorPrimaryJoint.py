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

def _to_long(node):
    result = cmds.ls(node, l=True)
    if result:
        return result[0]
    return None

def _normalize_angle(value):
    value = math.fmod(value, 360.0)
    if value > 180.0:
        value -= 360.0
    elif value < -180.0:
        value += 360.0
    return value


def _ensure_suffix(joint):
    joint_long = _to_long(joint)
    if not joint_long:
        return None
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
    return _to_long(renamed) or renamed



def _ensure_hierarchy_suffix(joint):
    joint_long = _to_long(joint)
    if not joint_long:
        return None
    stack = [joint_long]
    new_root = None
    visited = set()
    while stack:
        node = stack.pop()
        node_long = _ensure_suffix(node)
        if not node_long:
            continue
        if new_root is None:
            new_root = node_long
        if node_long in visited:
            continue
        visited.add(node_long)
        children = cmds.listRelatives(node_long, c=True, type="joint", f=True) or []
        stack.extend(children)
    return new_root





def _apply_mirror_transform(node, freeze_scale=True):
    node_long = _to_long(node)
    if not node_long:
        return None, None
    node_short = node_long.split("|")[-1]
    null_name = _uniquify(node_short + "_MirrorNull")
    null = cmds.group(em=True, name=null_name)
    cmds.xform(null, ws=True, t=(0.0, 0.0, 0.0), ro=(0.0, 0.0, 0.0))
    try:
        parented = cmds.parent(node_long, null) or []
        if parented:
            node_long = _to_long(parented[0]) or node_long
        cmds.setAttr(null + ".scaleX", -1.0)
        if freeze_scale:
            cmds.makeIdentity(null, apply=True, t=False, r=False, s=True, n=False, pn=True)
        parented = cmds.parent(node_long, w=True) or []
        if parented:
            node_long = _to_long(parented[0]) or node_long
    except Exception:
        if cmds.objExists(null):
            cmds.delete(null)
        return None, None
    return node_long, null



def _match_transform(target, source, pos=False, rot=False):
    if not (pos or rot):
        return
    if hasattr(cmds, "matchTransform"):
        cmds.matchTransform(target, source, pos=pos, rot=rot)
        return
    constraints = []
    if pos and rot:
        constraints.append(cmds.parentConstraint(source, target, mo=False))
    elif rot:
        constraints.append(cmds.orientConstraint(source, target, mo=False))
    elif pos:
        constraints.append(cmds.pointConstraint(source, target, mo=False))
    if constraints:
        cmds.delete(constraints)



def _align_with_dummy(source_joint, mirrored_joint):
    source_long = _to_long(source_joint)
    mirrored_long = _to_long(mirrored_joint)
    if not source_long or not mirrored_long:
        return
    mirror_short = mirrored_long.split("|")[-1]
    dummy_short = _uniquify(mirror_short + "_Dummy")

    cleanup_nodes = set()
    helper_null = None
    dummy_long = None
    try:
        duplicated = cmds.duplicate(source_long, po=True, n=dummy_short)
    except Exception:
        return
    if not duplicated:
        return

    cleanup_nodes.update(duplicated)
    dummy = duplicated[0]
    dummy_long = _to_long(dummy)
    if not dummy_long:
        return

    dummy_long, helper_null = _apply_mirror_transform(dummy_long, freeze_scale=False)
    if helper_null:
        cleanup_nodes.add(helper_null)
    if not dummy_long:
        return

    cleanup_nodes.add(dummy_long)
    try:
        _match_transform(mirrored_long, dummy_long, pos=True, rot=True)
        cmds.rotate(0.0, 180.0, 0.0, mirrored_long, os=True, r=True, pcp=True)
        cmds.makeIdentity(mirrored_long, apply=True, t=False, r=True, s=False, n=False, pn=True)
    except Exception:
        pass
    finally:
        existing = []
        for node in cleanup_nodes:
            if not cmds.objExists(node):
                continue
            node_long = _to_long(node) or node
            existing.append(node_long)
        if existing:
            cmds.delete(list(set(existing)))


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



def _create_mirrored_joint(joint, mirror_map):
    joint_long = _to_long(joint)
    if not joint_long:
        return None
    short = joint_long.split("|")[-1]
    mirror_short = _mirror_name(short)
    if not mirror_short:
        return None

    existing = cmds.ls(mirror_short, l=True)
    if existing:
        cmds.warning(u"{0} は既に存在するため作成をスキップします。".format(mirror_short))
        mirror_map[joint_long] = existing[0]
        return None

    duplicated_list = cmds.duplicate(joint_long)
    if not duplicated_list:
        cmds.warning(u"{0} の複製に失敗しました。".format(joint_long))
        return None

    duplicated = duplicated_list[0]
    try:
        duplicated = cmds.rename(duplicated, mirror_short)
    except RuntimeError:
        cmds.warning(u"{0} のリネームに失敗しました。".format(mirror_short))
        cmds.delete(duplicated)
        return None

    duplicated_long = _to_long(duplicated)
    if not duplicated_long:
        cmds.warning(u"複製したジョイント {0} を取得できませんでした。".format(mirror_short))
        cmds.delete(duplicated)
        return None

    duplicated_long, helper_null = _apply_mirror_transform(duplicated_long, freeze_scale=True)
    if not duplicated_long:
        cmds.warning(u"{0} ?????????????".format(mirror_short))
        if helper_null and cmds.objExists(helper_null):
            cmds.delete(helper_null)
        return None
    if helper_null and cmds.objExists(helper_null):
        cmds.delete(helper_null)

    target_parent = _determine_target_parent(joint_long, mirror_map)
    if target_parent:
        parented = cmds.parent(duplicated_long, target_parent) or []
        if parented:
            duplicated_long = _to_long(parented[0]) or duplicated_long

    mirror_map[joint_long] = duplicated_long
    created_nodes = [duplicated_long]
    alignment_pairs = [(joint_long, duplicated_long)]

    queue = [(joint_long, duplicated_long)]
    while queue:
        source, mirrored = queue.pop(0)
        src_children = cmds.listRelatives(source, c=True, type='joint', f=True) or []
        mirrored_children = cmds.listRelatives(mirrored, c=True, type='joint', f=True) or []
        if len(src_children) != len(mirrored_children):
            cmds.warning('Child count mismatch while mirroring {0}'.format(source.split('|')[-1]))
        for src_child, mirrored_child in zip(src_children, mirrored_children):
            src_child_long = _to_long(src_child)
            mirrored_child_long = _to_long(mirrored_child)
            if not src_child_long or not mirrored_child_long:
                continue
            src_short = src_child_long.split('|')[-1]
            target_short = _mirror_name(src_short)
            if target_short:
                if cmds.objExists(target_short):
                    target_short = _uniquify(target_short)
                try:
                    renamed_child = cmds.rename(mirrored_child_long, target_short)
                    mirrored_child_long = _to_long(renamed_child)
                except RuntimeError:
                    cmds.warning('Failed to rename duplicated child {0}'.format(target_short))
                    mirrored_child_long = _to_long(mirrored_child_long)
            else:
                mirrored_child_long = _to_long(mirrored_child_long)
            if not mirrored_child_long:
                continue
            mirror_map[src_child_long] = mirrored_child_long
            created_nodes.append(mirrored_child_long)
            alignment_pairs.append((src_child_long, mirrored_child_long))
            queue.append((src_child_long, mirrored_child_long))

    for source_node, mirrored_node in alignment_pairs:
        _align_with_dummy(source_node, mirrored_node)

    return created_nodes

def _mirror_joint_recursive(joint, mirror_map, created):
    joint_long = _to_long(joint)
    if not joint_long:
        return
    joint_long = _ensure_hierarchy_suffix(joint_long)
    if not joint_long:
        return
    if joint_long in mirror_map:
        return

    mirrored_nodes = _create_mirrored_joint(joint_long, mirror_map)
    if mirrored_nodes:
        created.extend(mirrored_nodes)

def mirror_primary_joints():
    selection = cmds.ls(sl=True, type="joint", l=True) or []
    selected = []
    if selection:
        # sort by hierarchy depth so parents are processed before children
        selection = sorted(selection, key=lambda node: node.count("|"))
        selected_set = set()
        for joint in selection:
            parents = set(cmds.listRelatives(joint, p=True, f=True) or [])
            if parents & selected_set:
                continue
            selected.append(joint)
            selected_set.add(joint)
    else:
        selected = []
    if not selected:
        cmds.warning(u"ミラーするジョイントを選択してください。")
        return
    cmds.undoInfo(openChunk=True)
    roots = selected

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
    cmds.undoInfo(closeChunk=True)
