# -*- coding: utf-8 -*-
import maya.cmds as cmds


def create_twist_chain(count=4, name_tag="Twist"):
    sel = cmds.ls(sl=True, type="joint")
    if len(sel) < 2:
        cmds.error(u"開始ジョイント → 参照ジョイント の順に選択してください。")
    start, ref = sel[0], sel[1]

    p_start = cmds.xform(start, q=True, ws=True, t=True)
    p_ref = cmds.xform(ref, q=True, ws=True, t=True)
    length = ((p_ref[0] - p_start[0]) ** 2 + (p_ref[1] - p_start[1]) ** 2 + (p_ref[2] - p_start[2]) ** 2) ** 0.5
    if length < 1e-5:
        cmds.error(u"開始ジョイントと参照ジョイントの位置が同一です。")

    pma_sub = cmds.createNode("plusMinusAverage", n=f"{name_tag}_twistDelta_PMA")
    cmds.setAttr(pma_sub + ".operation", 2)  # subtract
    cmds.connectAttr(ref + ".rotateX", pma_sub + ".input1D[0]", f=True)
    cmds.connectAttr(start + ".rotateX", pma_sub + ".input1D[1]", f=True)

    created = []
    for i in range(1, count + 1):
        ratio = float(i) / float(count + 1)

        jnt_name = f"{name_tag}_twist{i:02d}_JNT"
        j = cmds.duplicate(start, po=True, n=jnt_name)[0]

        try:
            cmds.parent(j, start)
        except Exception:
            pass

        cmds.setAttr(j + ".translateY", 0)
        cmds.setAttr(j + ".translateZ", 0)
        cmds.setAttr(j + ".translateX", length * ratio)

        for ax in ("X", "Y", "Z"):
            try:
                cmds.setAttr(j + ".rotate" + ax, l=False, k=True, cb=True)
            except Exception:
                pass

        if cmds.objExists(j + ".segmentScaleCompensate"):
            try:
                cmds.setAttr(j + ".segmentScaleCompensate", 0)
            except Exception:
                pass

        md = cmds.createNode("multDoubleLinear", n=f"{name_tag}_twist{i:02d}_MD")
        cmds.setAttr(md + ".input2", ratio)
        cmds.connectAttr(pma_sub + ".output1D", md + ".input1", f=True)

        pma_add = cmds.createNode("plusMinusAverage", n=f"{name_tag}_twist{i:02d}_PMA")
        cmds.setAttr(pma_add + ".operation", 1)
        cmds.connectAttr(start + ".rotateX", pma_add + ".input1D[0]", f=True)
        cmds.connectAttr(md + ".output", pma_add + ".input1D[1]", f=True)

        cmds.connectAttr(pma_add + ".output1D", j + ".rotateX", f=True)
        for ax in ("Y", "Z"):
            cmds.setAttr(j + ".rotate" + ax, l=True, k=False, cb=False)

        created.append(j)

    cmds.select(created, r=True)
    print(u"[Twist] 作成:", created)
    return created


if __name__ == "__main__":
    create_twist_chain()
