# -*- coding: utf-8 -*-
import maya.cmds as cmds


def _uniquify(name):
    if not cmds.objExists(name):
        return name
    i = 1
    while cmds.objExists(f"{name}{i:02d}"):
        i += 1
    return f"{name}{i:02d}"


def build_poly(poly_name="CTRL_Loop_POLY"):
    sel = [s for s in (cmds.ls(sl=True, l=True) or []) if cmds.nodeType(s) == "transform"]
    if len(sel) < 3:
        cmds.error(u"コントローラーを3つ以上選択してください。")

    cmds.undoInfo(openChunk=True)
    try:
        pts = [cmds.xform(s, q=True, ws=True, rp=True) for s in sel]
        pts = [(p[0], p[1], p[2]) for p in pts]

        poly = cmds.polyCreateFacet(p=pts, n=_uniquify(poly_name))[0]
        cmds.select(poly)
        return poly
    finally:
        cmds.undoInfo(closeChunk=True)


if __name__ == "__main__":
    build_poly()
