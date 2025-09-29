# -*- coding: utf-8 -*-
import maya.cmds as cmds

def _uniquify(name):
    """同名があれば連番でユニーク化"""
    if not cmds.objExists(name):
        return name
    i = 1
    base = name
    while cmds.objExists(f"{base}{i:02d}"):
        i += 1
    return f"{base}{i:02d}"

def simple_rig_from_ctrl_and_joints(grp_suffix="_GRP", ctrl_suffix="_CTRL"):
    sel = cmds.ls(sl=True, l=True) or []
    if len(sel) < 2:
        cmds.error(u"最初にコントローラー(カーブのトランスフォーム)を1つ、続けてジョイントを1つ以上選択してください。")

    # 先頭をコントローラー、以降をジョイント群として解釈
    src_ctrl = sel[0]
    # もしシェイプ選択だったら親トランスフォームにする
    if cmds.nodeType(src_ctrl) in ("nurbsCurve", "bezierCurve", "mesh"):
        parents = cmds.listRelatives(src_ctrl, p=True, f=True) or []
        if not parents:
            cmds.error(u"カーブ(またはメッシュ)のトランスフォームを選択してください。")
        src_ctrl = parents[0]

    # ジョイントのみ抽出（順序維持）
    joints = [j for j in sel[1:] if cmds.nodeType(j) == "joint"]
    if not joints:
        cmds.error(u"コントローラーの後にジョイントを1つ以上選択してください。")

    created = []
    cmds.undoInfo(ock=True)
    try:
        for jnt in joints:
            jnt_short = jnt.split("|")[-1]
            grp_name = _uniquify(jnt_short + grp_suffix)
            ctrl_name = _uniquify(jnt_short + ctrl_suffix)

            # 空グループ作成 & ジョイントにマッチ（位置回転）
            grp = cmds.group(em=True, n=grp_name)
            cmds.matchTransform(grp, jnt, pos=True, rot=True, scl=False)

            # コントローラー複製 → 名前変更 → グループの子に
            dup = cmds.duplicate(src_ctrl, rr=True)[0]
            dup = cmds.rename(dup, ctrl_name)
            cmds.parent(dup, grp)

            # TRをゼロ / Sを1に（ローカル値）
            for a in ("tx","ty","tz","rx","ry","rz"):
                if cmds.objExists(f"{dup}.{a}") and not cmds.getAttr(f"{dup}.{a}", l=True):
                    cmds.setAttr(f"{dup}.{a}", 0)
            for a in ("sx","sy","sz"):
                if cmds.objExists(f"{dup}.{a}") and not cmds.getAttr(f"{dup}.{a}", l=True):
                    cmds.setAttr(f"{dup}.{a}", 1)

            # ジョイントへペアレントコンストレイン（保持オフ：MO=False）
            cmds.parentConstraint(dup, jnt, mo=False)

            created.append((grp, dup))
        cmds.select([c for pair in created for c in pair], r=True)
        print(u"作成完了：{}セット".format(len(created)))
    finally:
        cmds.undoInfo(cck=True)

# 使い方：
# 1) カーブのトランスフォームを1つ選択
# 2) 続けて、リグ化したいジョイントを複数選択（順番は任意）
# 3) 下記を実行 → simple_rig_from_ctrl_and_joints()
simple_rig_from_ctrl_and_joints()
