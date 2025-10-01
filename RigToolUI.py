# -*- coding: utf-8 -*-
import importlib
import os
import sys
from functools import partial

from PySide2 import QtCore, QtWidgets
from shiboken2 import wrapInstance

import maya.OpenMayaUI as omui
import maya.cmds as cmds
import maya.mel as mel

MODULE_DIR = os.path.dirname(__file__)
if MODULE_DIR not in sys.path:
    sys.path.append(MODULE_DIR)


def maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    if ptr is None:
        raise RuntimeError("Mayaのメインウィンドウが取得できませんでした。")
    return wrapInstance(int(ptr), QtWidgets.QWidget)


def _load_module(module_name):
    module = sys.modules.get(module_name)
    if module is not None:
        module = importlib.reload(module)
    else:
        module = importlib.import_module(module_name)
    return module


def _call_module_function(module_name, func_name, *args, **kwargs):
    module = _load_module(module_name)
    func = getattr(module, func_name)
    return func(*args, **kwargs)


def _open_lmrigger():
    module = _load_module("LMRigger")
    module.LMriggerDialog.show_dialog()


def _open_rig111_wire_controllers():
    mel_path = os.path.join(MODULE_DIR, "rig111wireController.mel").replace("\\", "/")
    mel.eval(f'source "{mel_path}";')
    mel.eval("rig111WireControllers();")


def _open_driven_key_helper():
    module = _load_module("DrivenKeyTool")
    module.show_dialog()


def _open_driven_key_matrix():
    module = _load_module("DrivenKeyMatrixTool")
    module.show_dialog()


class TwistChainDialog(QtWidgets.QDialog):
    def __init__(self, parent=maya_main_window()):
        super(TwistChainDialog, self).__init__(parent)
        self.setObjectName("twistChainDialog")
        self.setWindowTitle(u"Create Twist Chain")
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        self.setWindowModality(QtCore.Qt.NonModal)

        self._create_widgets()
        self._create_layout()

    def _create_widgets(self):
        self.label = QtWidgets.QLabel(u"生成する補助ジョイントの数:")
        self.spin_box = QtWidgets.QSpinBox()
        self.spin_box.setRange(1, 100)
        self.spin_box.setValue(4)

        self.scale_label = QtWidgets.QLabel(u"90°ツイスト時のYZスケール:")
        self.scale_spin = QtWidgets.QDoubleSpinBox()
        self.scale_spin.setDecimals(3)
        self.scale_spin.setRange(0.0, 20.0)
        self.scale_spin.setSingleStep(0.05)
        self.scale_spin.setValue(1.2)

        self.create_button = QtWidgets.QPushButton(u"Create")
        self.close_button = QtWidgets.QPushButton(u"Close")
        self.create_button.setDefault(True)
        self.create_button.setAutoDefault(True)

        self.create_button.clicked.connect(self._on_create_clicked)
        self.close_button.clicked.connect(self.close)

    def _create_layout(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        form_layout = QtWidgets.QFormLayout()
        form_layout.addRow(self.label, self.spin_box)
        form_layout.addRow(self.scale_label, self.scale_spin)
        main_layout.addLayout(form_layout)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(self.create_button)
        button_layout.addWidget(self.close_button)
        main_layout.addLayout(button_layout)

    def _on_create_clicked(self):
        count = self.spin_box.value()
        scale = self.scale_spin.value()

        def _callback():
            _call_module_function(
                "CreateTwistChain", "create_twist_chain", count=count, scale_at_90=scale
            )

        _run_with_warning(_callback)

    def closeEvent(self, event):
        super(TwistChainDialog, self).closeEvent(event)
        global _twist_chain_dialog
        _twist_chain_dialog = None


_twist_chain_dialog = None


def _create_twist_chain_with_count_dialog():
    global _twist_chain_dialog
    if _twist_chain_dialog is None:
        _twist_chain_dialog = TwistChainDialog()
    _twist_chain_dialog.show()
    _twist_chain_dialog.raise_()
    _twist_chain_dialog.activateWindow()
    return _twist_chain_dialog


def _open_twist_chain_editor_dialog():
    _call_module_function("CreateTwistChain", "show_twist_chain_editor")


def _run_with_warning(callback):
    try:
        callback()
    except Exception as exc:  # pragma: no cover - Maya環境での実行時に必要
        cmds.warning(u"ツール実行中にエラーが発生しました: {0}".format(exc))
        raise


TOOL_CATEGORIES = [
    (
        u"ジョイントセットアップ",
        [
            {
                "label": u"Create Twist Chain",
                "tooltip": u"開始ジョイントを選択すると子から参照ジョイントを自動検出してツイスト用補助ジョイントを作成します。",
                "callback": _create_twist_chain_with_count_dialog,
            },
            {
                "label": u"Twist Chain Editor",
                "tooltip": u"選択したジョイント直下のツイストジョイントに設定されたツイストウェイトとスケール最大値を一覧で編集します。",
                "callback": partial(_run_with_warning, _open_twist_chain_editor_dialog),
            },
            {
                "label": u"Create Half Rotation Joint",
                "tooltip": u"選択したジョイントに半回転ジョイントとINFジョイントを生成し、回転を0.5倍に接続します。",
                "callback": partial(_call_module_function, "CreateHalfRotJoint", "create_half_rotation_joint"),
            },
            {
                "label": u"Create Support Joint",
                "tooltip": u"選択したジョイントを親としてサポートジョイントを作成し、support_jntレイヤーに追加します。",
                "callback": partial(_call_module_function, "CreateSupportJoint", "create_support_joint"),
            },
            {
                "label": u"Mirror Twist & Half Joint",
                "tooltip": u"選択したジョイントのTwistチェーンとHalfジョイントを名前規則に基づいて反対側に複製します。",
                "callback": partial(_call_module_function, "MirrorTwistHalfJoint", "mirror_twist_and_half"),
            },
            {
                "label": u"Driven Key Helper",
                "tooltip": u"選択したジョイントをソースにTwist/Half用ジョイントへドリブンキーを設定します。",
                "callback": partial(_run_with_warning, _open_driven_key_helper),
            },
            {
                "label": u"Driven Key Matrix",
                "tooltip": u"選択したジョイントに設定されたドリブンキーを行列で確認・編集します。",
                "callback": partial(_run_with_warning, _open_driven_key_matrix),
            },
            {
                "label": u"Simple Rig From Ctrl + Joints",
                "tooltip": u"コントローラーを1つ、続いてジョイントを選択し、複製コントローラーとゼログループを自動配置します。",
                "callback": partial(_call_module_function, "csimplerig", "simple_rig_from_ctrl_and_joints"),
            },
            {
                "label": u"Create Eyelid Rig",
                "tooltip": u"複製元コントローラーとまぶたジョイントを選択し、Aim/Parentコンストレイント付きのセットアップを構築します。",
                "callback": partial(_call_module_function, "ArigUtil", "create_eyelid_rig"),
            },
            {
                "label": u"Create Stretchy Spline IK",
                "tooltip": u"開始ジョイントと終了ジョイントを選択してストレッチ付きスプラインIKとクラスタを作成します。",
                "callback": partial(_call_module_function, "ArigUtil", "create_stretchy_spline_ik_from_selection"),
            },
        ],
    ),
    (
        u"コントローラー補助",
        [
            {
                "label": u"Build Poly Loop",
                "tooltip": u"3つ以上のコントローラーを選択し、その位置を頂点とする1フェースのポリゴンを生成します。",
                "callback": partial(_call_module_function, "buildpoly", "build_poly"),
            },
            {
                "label": u"Build Poly + Nearest Constrain",
                "tooltip": u"メッシュとコントローラーを選択し、最寄り頂点へ pointOnPolyConstraint で拘束するゼログループを挿入します。",
                "callback": partial(_call_module_function, "ArigUtil", "build_poly_and_constrain_to_nearest_vertices"),
            },
            {
                "label": u"Nearest PointOnPoly Constraint",
                "tooltip": u"メッシュとトランスフォームを選んで、各トランスフォームを最も近い頂点へ pointOnPolyConstraint します。",
                "callback": partial(_call_module_function, "NearestPOPConstraint", "nearest_point_on_poly_constraint"),
            },
            {
                "label": u"Connect Translate Attributes",
                "tooltip": u"最初に駆動元、続いて接続先を選択して translate XYZ を一括接続します。",
                "callback": partial(_call_module_function, "ArigUtil", "connect_translate_from_target"),
            },
            {
                "label": u"Delete Constraints In Hierarchy",
                "tooltip": u"選択階層内に存在するコンストレイントノードをまとめて削除します。",
                "callback": partial(_call_module_function, "ArigUtil", "delete_constraints_in_selection_hierarchy"),
            },
            {
                "label": u"Create Matched Locators",
                "tooltip": u"選択オブジェクトの位置・回転に合わせたロケータを作成し選択し直します。",
                "callback": partial(_call_module_function, "ArigUtil", "create_locators_with_match_transform"),
            },
        ],
    ),
    (
        u"外部ツール",
        [
            {
                "label": u"LMRigger",
                "tooltip": u"LMrigger 2.7.23 のUIを開きます。",
                "callback": _open_lmrigger,
            },
            {
                "label": u"rig111 Wire Controllers",
                "tooltip": u"rig111 wireControllers のMELウィンドウを開き、選択に合わせてカーブを配置します。",
                "callback": _open_rig111_wire_controllers,
            },
        ],
    ),
]


class RigToolLauncher(QtWidgets.QDialog):
    _instance = None

    @classmethod
    def show_dialog(cls):
        if cls._instance is None:
            cls._instance = RigToolLauncher()
        cls._instance.show()
        cls._instance.raise_()
        cls._instance.activateWindow()
        return cls._instance

    def __init__(self, parent=maya_main_window()):
        super(RigToolLauncher, self).__init__(parent)
        self.setObjectName("arigToolLauncher")
        self.setWindowTitle("ARig Tool Launcher")
        self.setMinimumWidth(360)
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)

        self._create_widgets()
        self._create_layout()

    def _create_widgets(self):
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        container = QtWidgets.QWidget()
        self.scroll_area.setWidget(container)
        self.tools_layout = QtWidgets.QVBoxLayout(container)
        self.tools_layout.setContentsMargins(6, 6, 6, 6)
        self.tools_layout.setSpacing(12)

        for category_name, tools in TOOL_CATEGORIES:
            group = QtWidgets.QGroupBox(category_name)
            vbox = QtWidgets.QVBoxLayout(group)
            vbox.setSpacing(6)
            for tool in tools:
                button = QtWidgets.QPushButton(tool["label"])
                button.setToolTip(tool["tooltip"])
                button.clicked.connect(partial(_run_with_warning, tool["callback"]))
                vbox.addWidget(button)
            self.tools_layout.addWidget(group)

        self.tools_layout.addStretch(1)

    def _create_layout(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.addWidget(self.scroll_area)


if __name__ == "__main__":
    RigToolLauncher.show_dialog()
