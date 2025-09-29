# -*- coding: utf-8 -*-
import maya.cmds as cmds


def nearest_point_on_poly_constraint(mesh=None, controls=None, maintain_offset=False):
    if controls is None:
        controls = []

    selection = cmds.ls(sl=True, l=True) or []
    if mesh is None:
        if len(selection) < 2:
            cmds.error(u"[メッシュ] → [拘束したいトランスフォーム] の順で選択してください。")
        mesh = selection[0]
        controls = selection[1:]
    elif not controls:
        controls = selection

    if not controls:
        cmds.error(u"拘束対象のトランスフォームを1つ以上指定してください。")

    mesh = cmds.ls(mesh, l=True)[0]
    mesh_shapes = cmds.listRelatives(mesh, s=True, ni=True, type="mesh", f=True) or []
    if not mesh_shapes:
        cmds.error(u"メッシュ形状が見つかりません: {0}".format(mesh))
    mesh_shape = mesh_shapes[0]

    ctrl_positions = [tuple(cmds.xform(ctrl, q=True, ws=True, rp=True)) for ctrl in controls]
    vtx_count = cmds.polyEvaluate(mesh_shape, v=True)
    vtx_positions = [tuple(cmds.pointPosition(f"{mesh_shape}.vtx[{i}]", w=True)) for i in range(vtx_count)]

    def _dist2(a, b):
        return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2

    created = []
    for ctrl, pos in zip(controls, ctrl_positions):
        nearest_idx = min(range(vtx_count), key=lambda i: _dist2(pos, vtx_positions[i]))
        vtx_comp = f"{mesh_shape}.vtx[{nearest_idx}]"
        constraint = cmds.pointOnPolyConstraint(vtx_comp, ctrl, mo=maintain_offset)[0]
        created.append((ctrl, constraint, vtx_comp))

    cmds.select([c for c, _, _ in created], r=True)
    return created


if __name__ == "__main__":
    nearest_point_on_poly_constraint()
