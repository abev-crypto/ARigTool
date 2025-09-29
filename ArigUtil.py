# -*- coding: utf-8 -*-
import maya.cmds as cmds


def _uniquify(name):
    if not cmds.objExists(name):
        return name
    i = 1
    while cmds.objExists(f"{name}{i:02d}"):
        i += 1
    return f"{name}{i:02d}"


def connect_translate_from_target():
    selection = cmds.ls(selection=True)
    if len(selection) < 2:
        cmds.warning("2つ以上のオブジェクトを選択してください（最初がターゲット）")
        return

    target = selection[0]
    destinations = selection[1:]

    for dest in destinations:
        for axis in ["X", "Y", "Z"]:
            try:
                cmds.connectAttr(f"{target}.translate{axis}", f"{dest}.translate{axis}", force=True)
            except RuntimeError as exc:
                cmds.warning(f"接続に失敗: {target}.translate{axis} → {dest}.translate{axis} | {exc}")


def delete_constraints_in_selection_hierarchy():
    selected = cmds.ls(selection=True, long=True)
    if not selected:
        cmds.warning("何かノードを選択してください。")
        return

    all_nodes = []
    for node in selected:
        all_nodes.append(node)
        descendants = cmds.listRelatives(node, allDescendents=True, fullPath=True) or []
        all_nodes.extend(descendants)

    constraints_to_delete = set()
    for node in all_nodes:
        children = cmds.listRelatives(node, children=True, fullPath=True) or []
        for child in children:
            if cmds.nodeType(child).endswith("Constraint"):
                constraints_to_delete.add(child)

        connections = cmds.listConnections(node, type="constraint", plugs=False, connections=False) or []
        for conn in connections:
            conn_path = cmds.ls(conn, long=True)
            if conn_path and cmds.nodeType(conn_path[0]).endswith("Constraint"):
                constraints_to_delete.add(conn_path[0])

    for constraint in constraints_to_delete:
        if cmds.objExists(constraint):
            cmds.delete(constraint)
            print(f"Deleted constraint: {constraint}")


def _ensure_unique_transform(name):
    unique = _uniquify(name)
    return cmds.createNode("transform", name=unique)


def _insert_zero_group(ctrl, suffix="_GRP"):
    ctrl = cmds.ls(ctrl, l=True)[0]
    parent = cmds.listRelatives(ctrl, p=True, f=True) or []
    grp_name = _uniquify(ctrl.split("|")[-1] + suffix)
    grp = cmds.group(em=True, n=grp_name)
    cmds.matchTransform(grp, ctrl, pos=True, rot=True, scl=False)
    if parent:
        cmds.parent(grp, parent[0])
    cmds.parent(ctrl, grp)
    return cmds.ls(grp, l=True)[0]


def _dist2(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def create_eyelid_rig(aim_vector=(1, 0, 0), up_vector=(0, 1, 0), maintain_offset=True):
    sel = cmds.ls(sl=True, long=True) or []
    if len(sel) < 2:
        cmds.error(u"選択順: [最初にコントローラー曲線] → [以降は対象ジョイント].")

    base_ctrl = sel[0]
    if cmds.nodeType(base_ctrl) in ("nurbsCurve", "bezierCurve", "mesh"):
        parents = cmds.listRelatives(base_ctrl, p=True, f=True) or []
        if not parents:
            cmds.error(u"カーブ(またはメッシュ)のトランスフォームを選択してください。")
        base_ctrl = parents[0]

    joints = [s for s in sel[1:] if cmds.nodeType(s) == "joint"]
    if not joints:
        cmds.error(u"2番目以降にジョイントを選択してください。")

    created = []
    for jnt in joints:
        parents = cmds.listRelatives(jnt, parent=True, fullPath=True) or []
        parent_jnt = parents[0] if parents and cmds.nodeType(parents[0]) == "joint" else None
        if not parent_jnt:
            cmds.warning(u"{0}: 親ジョイントが見つからないためスキップ".format(jnt))
            continue

        short = jnt.split("|")[-1].replace(":", "_")
        center = _ensure_unique_transform(short + "_Center")
        cmds.matchTransform(center, parent_jnt, pos=True, rot=True, scl=False)
        cmds.parent(center, parent_jnt)

        offset = _ensure_unique_transform(short + "_CTRL_OFS")
        cmds.matchTransform(offset, jnt, pos=True, rot=True, scl=False)
        cmds.parent(offset, center)

        dup = cmds.duplicate(base_ctrl, rr=True)[0]
        dup = cmds.rename(dup, _uniquify(short + "_CTRL"))
        cmds.parent(dup, offset)

        for attr in ("tx", "ty", "tz", "rx", "ry", "rz"):
            if cmds.objExists(f"{dup}.{attr}"):
                cmds.setAttr(f"{dup}.{attr}", 0)
        for attr in ("sx", "sy", "sz"):
            if cmds.objExists(f"{dup}.{attr}") and not cmds.getAttr(f"{dup}.{attr}", l=True):
                cmds.setAttr(f"{dup}.{attr}", 1)

        cmds.aimConstraint(dup, center,
                           aimVector=aim_vector,
                           upVector=up_vector,
                           worldUpType="scene",
                           maintainOffset=False)

        cmds.parentConstraint(center, jnt, mo=maintain_offset)
        created.append((jnt, center, offset, dup))

    if created:
        cmds.select([c[3] for c in created], r=True)
        print(u"完了: {0} 本のジョイントにセットアップ。複製コントローラーを選択中。".format(len(created)))
    else:
        cmds.warning(u"処理対象がありませんでした。")


def build_poly_and_constrain_to_nearest_vertices(mesh=None,
                                                 group_suffix="_GRP",
                                                 keep_mesh_visible=True):
    sel = cmds.ls(sl=True) or []
    if mesh:
        controls = sel
        mesh_transform = mesh
    else:
        if len(sel) < 2:
            cmds.error(u"[メッシュ] → [コントローラー群] の順に選択してください。")
        mesh_transform = sel[0]
        controls = sel[1:]

    if not controls:
        cmds.error(u"拘束したいコントローラーを1つ以上選択してください。")

    mesh_transform = cmds.ls(mesh_transform, l=True)[0]
    mesh_shapes = cmds.listRelatives(mesh_transform, s=True, ni=True, type="mesh", f=True) or []
    if not mesh_shapes:
        cmds.error(u"メッシュ形状が見つかりません: {0}".format(mesh_transform))
    mesh_shape = mesh_shapes[0]

    ctrl_pos = [tuple(cmds.xform(s, q=True, ws=True, rp=True)) for s in controls]
    groups = [_insert_zero_group(ctrl, suffix=group_suffix) for ctrl in controls]
    vtx_count = cmds.polyEvaluate(mesh_shape, v=True)
    vtx_world = [tuple(cmds.pointPosition(f"{mesh_shape}.vtx[{i}]", w=True)) for i in range(vtx_count)]

    if len(ctrl_pos) > vtx_count:
        cmds.error(u"メッシュの頂点数よりコントローラーの方が多いため拘束できません。")

    unused = set(range(vtx_count))
    pairings = []
    for p in ctrl_pos:
        nearest_idx = min(unused, key=lambda i: _dist2(p, vtx_world[i]))
        pairings.append(nearest_idx)
        unused.remove(nearest_idx)

    for grp, vidx in zip(groups, pairings):
        constraint = cmds.pointOnPolyConstraint(f"{mesh_shape}.vtx[{vidx}]", grp, mo=False)[0]
        for axis in ("X", "Y", "Z"):
            conns = cmds.listConnections(f"{grp}.rotate{axis}", s=True, d=False, plugs=True) or []
            for src in conns:
                try:
                    cmds.disconnectAttr(src, f"{grp}.rotate{axis}")
                except Exception:
                    pass
        print(f"Constraint: {constraint} -> {grp} (vtx {vidx})")

    if not keep_mesh_visible:
        try:
            cmds.setAttr(mesh_transform + ".visibility", 0)
        except Exception:
            pass

    return groups


def get_all_spline_joints(joint_list, parent_joint, last_joint):
    child = cmds.listRelatives(parent_joint, children=True, type="joint")
    joint_list.append(child[0])
    if child and last_joint not in child:
        get_all_spline_joints(joint_list, child[0], last_joint)
    else:
        return joint_list


def create_stretchy_spline_ik(start_joint, end_joint, ik_name):
    spline_joints = [start_joint]
    get_all_spline_joints(spline_joints, start_joint, end_joint)

    ik_handle, effector, curve = cmds.ikHandle(
        sj=start_joint,
        ee=end_joint,
        sol="ikSplineSolver",
        createCurve=True,
        numSpans=2,
        n=ik_name)

    curve_info = cmds.arclen(curve, ch=True)
    cmds.getAttr(curve_info + ".arcLength")

    mult_node = cmds.shadingNode("multiplyDivide", asUtility=True, n=ik_name + "_multDiv")
    cmds.setAttr(mult_node + ".operation", 2)
    cmds.setAttr(mult_node + ".input2X", 6)

    cmds.connectAttr(curve_info + ".arcLength", mult_node + ".input1X")

    for jnt in spline_joints:
        cmds.connectAttr(mult_node + ".outputX", jnt + ".translateY")

    return ik_handle, curve


def apply_clusters_to_curve(curve_name):
    curve_cvs = cmds.ls(f"{curve_name}.cv[:]", fl=True)
    for cv in curve_cvs:
        cmds.cluster(cv)


def create_stretchy_spline_ik_from_selection():
    selected_joints = cmds.ls(sl=True, flatten=True, type="joint")
    if len(selected_joints) < 2:
        cmds.error(u"開始ジョイントと終了ジョイントを順に選択してください。")

    start_joint = selected_joints[0]
    end_joint = selected_joints[1]
    ik_name = "{0}_splineIK".format(end_joint.split("|")[-1])

    ik_handle, curve = create_stretchy_spline_ik(start_joint, end_joint, ik_name)
    apply_clusters_to_curve(curve)
    return ik_handle, curve


def create_locators_with_match_transform():
    selected_objects = cmds.ls(selection=True)

    if not selected_objects:
        cmds.warning("オブジェクトを選択してください。")
        return []

    locators = []

    for obj in selected_objects:
        loc = cmds.spaceLocator(name=_uniquify(obj.split("|")[-1] + "_LOC"))[0]
        cmds.matchTransform(loc, obj, position=True, rotation=True)
        locators.append(loc)

    cmds.select(locators, replace=True)
    print(f"{len(locators)} 個のロケータを作成しました。")
    return locators


__all__ = [
    "connect_translate_from_target",
    "delete_constraints_in_selection_hierarchy",
    "create_eyelid_rig",
    "build_poly_and_constrain_to_nearest_vertices",
    "create_stretchy_spline_ik_from_selection",
    "create_locators_with_match_transform",
]


if __name__ == "__main__":
    pass
