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

    src_ctrl = sel[0]
    if cmds.nodeType(src_ctrl) in ("nurbsCurve", "bezierCurve", "mesh"):
        parents = cmds.listRelatives(src_ctrl, p=True, f=True) or []
        if not parents:
            cmds.error(u"カーブ(またはメッシュ)のトランスフォームを選択してください。")
        src_ctrl = parents[0]

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

            grp = cmds.group(em=True, n=grp_name)
            cmds.matchTransform(grp, jnt, pos=True, rot=True, scl=False)

            dup = cmds.duplicate(src_ctrl, rr=True)[0]
            dup = cmds.rename(dup, ctrl_name)
            cmds.parent(dup, grp)

            for attr in ("tx", "ty", "tz", "rx", "ry", "rz"):
                if cmds.objExists(f"{dup}.{attr}") and not cmds.getAttr(f"{dup}.{attr}", l=True):
                    cmds.setAttr(f"{dup}.{attr}", 0)
            for attr in ("sx", "sy", "sz"):
                if cmds.objExists(f"{dup}.{attr}") and not cmds.getAttr(f"{dup}.{attr}", l=True):
                    cmds.setAttr(f"{dup}.{attr}", 1)

            cmds.parentConstraint(dup, jnt, mo=False)

            created.append((grp, dup))
        cmds.select([c for pair in created for c in pair], r=True)
        print(u"作成完了：{}セット".format(len(created)))
    finally:
        cmds.undoInfo(cck=True)


if __name__ == "__main__":
    simple_rig_from_ctrl_and_joints()
