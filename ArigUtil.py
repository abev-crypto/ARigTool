import maya.cmds as cmds

def connect_translate_from_target():
    selection = cmds.ls(selection=True)
    if len(selection) < 2:
        cmds.warning("2つ以上のオブジェクトを選択してください（最初がターゲット）")
        return

    target = selection[0]
    destinations = selection[1:]

    for dest in destinations:
        for axis in ['X', 'Y', 'Z']:
            try:
                cmds.connectAttr(f'{target}.translate{axis}', f'{dest}.translate{axis}', force=True)
            except RuntimeError as e:
                cmds.warning(f"接続に失敗: {target}.translate{axis} → {dest}.translate{axis} | {e}")

# 実行
connect_translate_from_target()

import maya.cmds as cmds

def delete_constraints_in_selection_hierarchy():
    selected = cmds.ls(selection=True, long=True)
    if not selected:
        cmds.warning("何かノードを選択してください。")
        return

    # 階層内のすべてのノードを取得（選択ノード自身も含む）
    all_nodes = []
    for node in selected:
        all_nodes.append(node)
        descendants = cmds.listRelatives(node, allDescendents=True, fullPath=True) or []
        all_nodes.extend(descendants)

    # コンストレインを集める
    constraints_to_delete = set()

    for node in all_nodes:
        # 子ノードにコンストレインがある場合
        children = cmds.listRelatives(node, children=True, fullPath=True) or []
        for child in children:
            if cmds.nodeType(child).endswith("Constraint"):
                constraints_to_delete.add(child)

        # 入出力接続にあるコンストレインノード
        connections = cmds.listConnections(node, type="constraint", plugs=False, connections=False) or []
        for conn in connections:
            conn_path = cmds.ls(conn, long=True)
            if conn_path and cmds.nodeType(conn_path[0]).endswith("Constraint"):
                constraints_to_delete.add(conn_path[0])

    # コンストレインを削除
    for constraint in constraints_to_delete:
        if cmds.objExists(constraint):
            cmds.delete(constraint)
            print(f"Deleted constraint: {constraint}")

delete_constraints_in_selection_hierarchy()

# -*- coding: utf-8 -*-
import maya.cmds as cmds

def create_eyelid_rig(aim_vector=(1,0,0), up_vector=(0,1,0), maintain_offset=True):
    sel = cmds.ls(sl=True, long=True) or []
    if len(sel) < 2:
        cmds.error(u"選択順: [最初にコントローラー曲線] → [以降は対象ジョイント].")

    base_ctrl = sel[0]
    joints = [s for s in sel[1:] if cmds.nodeType(s) == "joint"]
    if not joints:
        cmds.error(u"2番目以降にジョイントを選択してください。")

    created = []
    for jnt in joints:
        # 親ジョイント取得
        parent_jnt = None
        parents = cmds.listRelatives(jnt, parent=True, fullPath=True) or []
        if parents and cmds.nodeType(parents[0]) == "joint":
            parent_jnt = parents[0]
        else:
            cmds.warning(u"{0}: 親ジョイントが見つからないためスキップ".format(jnt))
            continue

        short = jnt.split("|")[-1]
        # ノード名
        center_name   = short.replace(":", "_") + "_Center"
        offset_name   = short.replace(":", "_") + "_CTRL_OFf"  # 大小混在を避けるなら "_ctrlOfs" などに
        ctrl_name     = short.replace(":", "_") + "_CTRL"

        # 既存衝突回避
        center_name = cmds.rename(cmds.createNode("transform", name=cmds.undoInfo(q=True, state=True) and center_name or center_name), center_name) if not cmds.objExists(center_name) else cmds.createNode("transform", name=cmds.sceneName().split("/")[-1] + "_" + center_name)
        offset_name = offset_name if not cmds.objExists(offset_name) else cmds.createNode("transform")
        if isinstance(offset_name, unicode) if hasattr(__builtins__, 'unicode') else isinstance(offset_name, str):
            pass

        # Center作成：親ジョイント位置に
        center = center_name if cmds.objExists(center_name) else cmds.createNode("transform", name=center_name)
        cmds.matchTransform(center, parent_jnt, pos=True, rot=False, scl=False)

        # オフセットNull作成：ジョイントに一致
        offset = offset_name if cmds.objExists(offset_name) else cmds.createNode("transform", name=offset_name)
        cmds.matchTransform(offset, jnt, pos=True, rot=True, scl=False)

        # コントローラー複製 → オフセットの子へ
        dup = cmds.duplicate(base_ctrl, name=ctrl_name, rr=True)[0]
        # 余計な履歴やシェイプネーム衝突を一応ケア
        # （必要ならここでfreezeはしない。ゼロ化運用のため）
        # 親子付け
        try:
            cmds.parent(dup, offset)
        except:
            # 既に親がある/循環などの保険
            cmds.delete(dup)
            dup = cmds.duplicate(base_ctrl, name=ctrl_name, rr=True)[0]
            cmds.parent(dup, offset)

        # ローカルでTRゼロ化
        for a in ("tx","ty","tz","rx","ry","rz"):
            if cmds.objExists(dup + "." + a):
                cmds.setAttr(dup + "." + a, 0)

        # AimConstraint: Center をターゲット、dup(複製コントローラー)を拘束対象
        # worldUpTypeはシーンUp（vector）で簡潔に
        cmds.aimConstraint(dup, center, 
                           aimVector=aim_vector,
                           upVector=up_vector,
                           worldUpType="scene",
                           maintainOffset=False)

        # ParentConstraint: Center -> ジョイント
        cmds.parentConstraint(center, jnt, mo=maintain_offset)

        created.append((jnt, center, offset, dup))

    if created:
        cmds.select([c[3] for c in created], r=True)
        print(u"完了: {0} 本のジョイントにセットアップ。複製コントローラーを選択中。".format(len(created)))
    else:
        cmds.warning(u"処理対象がありませんでした。")

# そのまま実行したい場合は下行のコメントを外す
create_eyelid_rig()

# -*- coding: utf-8 -*-
import maya.cmds as cmds
import math
import maya.mel as mel

def _uniquify(name):
    if not cmds.objExists(name):
        return name
    i = 1
    while cmds.objExists(f"{name}{i:02d}"):
        i += 1
    return f"{name}{i:02d}"

def _insert_zero_group(ctrl, suffix="_GRP"):
    """コントローラー直上にゼログループを差し込む"""
    ctrl = cmds.ls(ctrl, l=True)[0]
    parent = cmds.listRelatives(ctrl, p=True, f=True)
    grp_name = _uniquify(ctrl.split("|")[-1] + suffix)
    grp = cmds.group(em=True, n=grp_name)
    cmds.matchTransform(grp, ctrl, pos=True, rot=True, scl=False)
    if parent:
        cmds.parent(grp, parent[0])
    cmds.parent(ctrl, grp)
    return cmds.ls(grp)[0]

def _dist2(a, b):
    return (a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2

def build_poly_and_constrain_to_nearest_vertices(poly_name="CTRL_Loop_POLY",
                                                 group_suffix="_GRP",
                                                 keep_mesh_visible=True):
    """
    1) 選択コントローラー位置に頂点を持つ1フェースのポリゴンを生成
    2) 各コントローラーにゼログループを差し込み
    3) 各グループを『最も近い頂点』へ pointOnPolyConstraint（mo=False）で拘束
       ※ 頂点指定は transform.vtx[i] 形式を使用
    """
    sel = [s for s in (cmds.ls(sl=True) or [])]
    mesh = sel[0]
    sel = [s for s in sel[1:]]
    cmds.undoInfo(openChunk=True)
    try:
        # 2) ゼログループ
        ctrl_pos = [tuple(cmds.xform(s, q=True, ws=True, rp=True)) for s in sel]
        groups = [_insert_zero_group(ctrl, suffix=group_suffix) for ctrl in sel]
        vtx_count = cmds.polyEvaluate(mesh, v=True)
        vtx_world = [tuple(cmds.pointPosition(f"{mesh}.vtx[{i}]", w=True)) for i in range(vtx_count)]
        # 3) 最近傍頂点に1対1で割り当て（重複を避けるため貪欲に確定）
        unused = set(range(vtx_count))
        pairings = []
        for p in ctrl_pos:
            # まだ使っていない頂点から最小距離を選ぶ
            nearest_idx = min(unused, key=lambda i: _dist2(p, vtx_world[i]))
            pairings.append(nearest_idx)
            unused.remove(nearest_idx)

        # 拘束設定（transform.vtx[i] を使う / ls で存在確認）
        for grp, vidx in zip(groups, pairings):
            vtx_comp = f"{mesh}.vtx[{vidx}]"
            if not cmds.ls(vtx_comp):
                cmds.error(u"頂点コンポーネントが取得できませんでした: " + vtx_comp)
            print(vtx_comp)
            cmds.select(cl=True)
            cmds.select(vtx_comp)
            cmds.select(grp, add=True)
            mel.eval('doCreatePointOnPolyConstraintArgList 2 {   "0" ,"0" ,"0" ,"1" ,"" ,"1" ,"1" ,"0" ,"0" ,"0" };pointOnPolyConstraint -maintainOffset  -weight 1;')
            for axis in ("X","Y","Z"):
                conns = cmds.listConnections(f"{grp}.rotate{axis}", s=True, d=False, plugs=True) or []
                for src in conns:
                    try:
                        cmds.disconnectAttr(src, f"{grp}.rotate{axis}")
                    except:
                        pass
            

    finally:
        cmds.undoInfo(closeChunk=True)

# 使い方：
# 1) ループ順でコントローラーを複数選択
# 2) 実行
build_poly_and_constrain_to_nearest_vertices(keep_mesh_visible=True)

import maya.cmds as cmds

# StartJointからEndJointに関連付けられているJointをListで取得
# Childが一つの想定なので骨が複数あるとおかしくなるかも。
def get_all_spline_joints(joint_list, parent_joint, last_joint):
    child = cmds.listRelatives(parent_joint, children=True, type="joint")
    joint_list.append(child[0])
    if child and last_joint not in child:
        get_all_spline_joints(joint_list, child[0], last_joint)
    else:
        return joint_list

# StretchySplineIKを自動作成するスクリプト
def create_stretchy_spline_ik(start_joint, end_joint, ik_name):
    
    spline_joints = [start_joint]
    get_all_spline_joints(spline_joints, start_joint, end_joint)
    
    # Spline IKの作成
    ik_handle, effector, curve = cmds.ikHandle(
        sj=start_joint,
        ee=end_joint,
        sol='ikSplineSolver',
        createCurve=True,
        numSpans=2,
        n=ik_name)
    
    curve_info = cmds.arclen(curve, ch=True)

    # ジョイントチェーンの初期長さを取得
    original_curve_length = cmds.getAttr(curve_info + ".arcLength")

    # スケールノードを作成
    mult_node = cmds.shadingNode('multiplyDivide', asUtility=True, n=ik_name + "_multDiv")
    cmds.setAttr(mult_node + ".operation", 2)  # Divide
    cmds.setAttr(mult_node + ".input2X", 6)

    # ノードを接続
    cmds.connectAttr(curve_info + ".arcLength", mult_node + ".input1X")
    
    for jnt in spline_joints:
        cmds.connectAttr(mult_node + ".outputX", jnt + ".translateY")

    return ik_handle, curve

# CurveのControlPointにClusterを自動作成するスクリプト
def apply_clusters_to_curve(curve_name):
    curveCVs = cmds.ls('{0}.cv[:]'.format(curve_name), fl=True)
    for cv in curveCVs:
        cmds.cluster(cv)

# How To Use
selected_joints = cmds.ls(sl=True, flatten=True, type="joint")

start_joint = selected_joints[0]
end_joint = selected_joints[1]
ik_name = "{0}_splineIK".format(end_joint.split("_")[-1]) # ex: Character_LeftArm

ik_handle, curve = create_stretchy_spline_ik(start_joint, end_joint, ik_name)
apply_clusters_to_curve(curve)

import maya.cmds as cmds

def create_locators_with_match_transform():
    selected_objects = cmds.ls(selection=True)
    
    if not selected_objects:
        cmds.warning("オブジェクトを選択してください。")
        return
    
    locators = []
    
    for obj in selected_objects:
        loc = cmds.spaceLocator(name=obj + "_LOC")[0]
        cmds.matchTransform(loc, obj, position=True, rotation=True)
        locators.append(loc)
    
    cmds.select(locators, replace=True)
    print(f"{len(locators)} 個のロケータを作成しました。")

# 実行
create_locators_with_match_transform()
