# -*- coding: utf-8 -*-
import maya.cmds as cmds

LAYER_NAME = "halfrot_jnt"

def _uniquify(base):
    if not cmds.objExists(base):
        return base
    i = 1
    while True:
        name = f"{base}{i:02d}"
        if not cmds.objExists(name):
            return name
        i += 1

def _ensure_display_layer(name):
    if not cmds.objExists(name) or cmds.nodeType(name) != "displayLayer":
        return cmds.createDisplayLayer(name=name, empty=True)
    return name

def create_half_rotation_joint():
    sel = cmds.ls(sl=True, type='joint') or []
    if not sel:
        cmds.warning(u"ジョイントを1つ以上選択してください。")
        return

    layer = _ensure_display_layer(LAYER_NAME)

    cmds.undoInfo(openChunk=True)
    created = []
    try:
        for j in sel:
            base = j.split("|")[-1]

            # 半回転ジョイントを複製ベースで作成（子なし、姿勢のみ）
            half_name = _uniquify(base + "_Half")
            half = cmds.duplicate(j, po=True, n=half_name)[0]  # 同階層に複製される想定
            cmds.matchTransform(half, j, pos=True, rot=True, scl=False)  # 念のため位置回転を一致
            # 回転順も合わせる
            ro = cmds.getAttr(j + ".rotateOrder")
            cmds.setAttr(half + ".rotateOrder", ro)

            # 半径スケール（元ジョイント基準）
            try:
                src_rad = cmds.getAttr(j + ".radius")
            except Exception:
                src_rad = 1.0
            cmds.setAttr(half + ".radius", max(0.01, src_rad * 2.0))

            # 0.5倍回転：multiplyDivide
            md_name = _uniquify("md_%s_half" % base)
            md = cmds.createNode("multiplyDivide", n=md_name)
            cmds.setAttr(md + ".operation", 1)  # multiply
            cmds.setAttr(md + ".input2X", 0.5)
            cmds.setAttr(md + ".input2Y", 0.5)
            cmds.setAttr(md + ".input2Z", 0.5)

            # 既存接続チェック（あるなら上書き）
            for ax in ("X", "Y", "Z"):
                dst_plug = f"{half}.rotate{ax}"
                cons = cmds.listConnections(dst_plug, s=True, d=False, p=True) or []
                for c in cons:
                    try:
                        cmds.disconnectAttr(c, dst_plug)
                    except Exception:
                        pass

            cmds.connectAttr(j + ".rotateX", md + ".input1X", f=True)
            cmds.connectAttr(j + ".rotateY", md + ".input1Y", f=True)
            cmds.connectAttr(j + ".rotateZ", md + ".input1Z", f=True)
            cmds.connectAttr(md + ".outputX", half + ".rotateX", f=True)
            cmds.connectAttr(md + ".outputY", half + ".rotateY", f=True)
            cmds.connectAttr(md + ".outputZ", half + ".rotateZ", f=True)

            # インフルエンス用ジョイント（halfの子）
            inf_name = _uniquify(base + "_Half_INF")
            # joint作成時に選択がjointだと自動で親子付くことがあるため、一度選択解除してから作成
            cmds.select(clear=True)
            inf = cmds.joint(n=inf_name)
            # 明示的に親子付け＆ゼロリング
            cmds.parent(inf, half)
            cmds.setAttr(inf + ".translate", 0, 0, 0, type="double3")
            cmds.setAttr(inf + ".rotate", 0, 0, 0, type="double3")
            cmds.setAttr(inf + ".jointOrient", 0, 0, 0, type="double3")
            # 半径 1.5倍（元ジョイント基準）
            cmds.setAttr(inf + ".radius", max(0.01, src_rad * 1.5))

            # ディスプレイレイヤーに追加
            cmds.editDisplayLayerMembers(layer, [half, inf], noRecurse=True)

            created.append((half, inf))

        if created:
            msg = u"\n".join([u"Half: %s / Influence: %s" % (h, i) for h, i in created])
            cmds.inViewMessage(amg=u"<hl>半回転ジョイント作成</hl><br>%s" % msg, pos="topCenter", fade=True, alpha=0.9)
    finally:
        cmds.undoInfo(closeChunk=True)

# 使い方：
# 1) 半回転の基準にしたいジョイントを選択
create_half_rotation_joint()
