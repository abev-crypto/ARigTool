# ARig Tool

ARig Tool は Autodesk Maya 上でのキャラクターリギング作業を効率化するためのツールランチャーです。PySide2 ベースの UI から複数の補助スクリプトを呼び出し、ジョイントセットアップやドリブンキー編集、コントローラー配置などの作業をまとめて行えます。【F:RigToolUI.py†L258-L310】

## 必要環境

- Autodesk Maya 2020 以降（PySide2 / shiboken2 が利用可能な環境）【F:RigToolUI.py†L8-L57】
- 本リポジトリの Python / MEL スクリプト一式

## 導入と起動方法

1. 本フォルダーを Maya の `scripts` パスに配置します。
2. Maya の Script Editor で次を実行するとランチャーが起動します。
   ```python
   import RigToolUI
   RigToolUI.RigToolLauncher.show_dialog()
   ```
   【F:RigToolUI.py†L258-L310】

## 注意

-ジョイントの向きはXUpでYがX+方向に向いていることが前提になっている機能があります

## 機能一覧

### ジョイントセットアップ

- **Create Twist Chain** — 選択したジョイントから参照ジョイントを自動検出し、ツイスト用補助ジョイントを指定数生成します。各ジョイントには `twistWeight` と `twistScaleMax` 属性が設定され、90° 時のスケール変化も自動接続されます。【F:RigToolUI.py†L149-L202】【F:CreateTwistChain.py†L43-L197】
- **Twist Chain Editor** — 選択ジョイント直下のツイストチェーンを一覧表示し、重みや最大スケール値を UI から編集できます。【F:RigToolUI.py†L149-L202】【F:CreateTwistChain.py†L320-L365】
- **Create Half Rotation Joint** — 選択ジョイントを複製して半回転ジョイントと影響ジョイントを作成し、回転値を 0.5 倍で伝達します。作成結果は `halfrot_jnt` レイヤーに追加されます。【F:RigToolUI.py†L149-L202】【F:CreateHalfRotJoint.py†L24-L88】
- **Create Support Joint** — 選択ジョイントの子としてサポートジョイントを生成し、半径を拡大した上で `support_jnt` レイヤーに自動登録します。【F:RigToolUI.py†L149-L202】【F:CreateSupportJoint.py†L34-L70】
- **Mirror Twist & Half Joint** — `_L` / `_R` の命名規則に従ってツイストチェーンや半回転ジョイント、サポートジョイントを反対側に複製し、必要に応じてドリブンキーも反転コピーします。【F:RigToolUI.py†L149-L202】【F:MirrorTwistHalfJoint.py†L1-L267】
- **Driven Key Helper** — Twist / Half / Support ジョイントの駆動設定を想定した UI を提供し、ドライバー軸と対象属性を選んでドリブンキーを一括設定できます。【F:RigToolUI.py†L149-L202】【F:DrivenKeyTool.py†L32-L200】
- **Driven Key Matrix** — 選択ジョイントに設定されたドリブンキーを行列形式で表示し、入力値・出力値をダブルクリックで編集できる管理ツールです。【F:RigToolUI.py†L149-L202】【F:DrivenKeyMatrixTool.py†L1-L200】
- **Simple Rig From Ctrl + Joints** — コントローラーとジョイントを選択すると、各ジョイントにゼログループ付きの複製コントローラーを配置し、親子関係とコンストレイントを自動構築します。【F:RigToolUI.py†L149-L202】【F:csimplerig.py†L16-L48】
- **Create Eyelid Rig** — ベースコントローラーとまぶたジョイントを元に Aim / Parent Constraint を含むまぶたリグをセットアップし、複製コントローラーを選択状態にします。【F:RigToolUI.py†L149-L202】【F:ArigUtil.py†L83-L139】
- **Create Stretchy Spline IK** — 開始ジョイントと終了ジョイントを指定してスプライン IK ハンドルとカーブを作成し、カーブ長に応じたストレッチとクラスタを自動付与します。【F:RigToolUI.py†L149-L202】【F:ArigUtil.py†L209-L253】

### コントローラー補助

- **Build Poly Loop** — 3 つ以上のトランスフォームを選択し、その位置を頂点とする 1 フェースのポリゴンを生成します。【F:RigToolUI.py†L203-L239】【F:buildpoly.py†L14-L26】
- **Build Poly + Nearest Constrain** — メッシュと複数コントローラーを選ぶと、最寄り頂点に `pointOnPolyConstraint` で拘束するゼログループを自動挿入します。【F:RigToolUI.py†L203-L239】【F:ArigUtil.py†L143-L208】
- **Nearest PointOnPoly Constraint** — 指定メッシュ上の最も近い頂点に各トランスフォームを拘束する `pointOnPolyConstraint` を設定します。【F:RigToolUI.py†L203-L239】【F:NearestPOPConstraint.py†L5-L42】
- **Connect Translate Attributes** — 最初に選択したノードの `translate` 属性を後続選択へ一括接続します。【F:RigToolUI.py†L203-L239】【F:ArigUtil.py†L13-L29】
- **Delete Constraints In Hierarchy** — 選択階層以下に存在する全てのコンストレイントノードを検出して削除します。【F:RigToolUI.py†L203-L239】【F:ArigUtil.py†L30-L59】
- **Create Matched Locators** — 選択オブジェクトの位置と回転に一致するロケータを生成し、作成したロケータを選択し直します。【F:RigToolUI.py†L203-L239】【F:ArigUtil.py†L256-L272】

### 外部ツール

- **LMRigger** — LMrigger 2.7.23 の UI を Maya 内で開きます。【F:RigToolUI.py†L240-L252】
- **rig111 Wire Controllers** — 付属の MEL スクリプトをロードし、選択に応じたワイヤーコントローラー UI を起動します。【F:RigToolUI.py†L240-L252】

## ライセンス

本リポジトリにライセンス表記が存在しないため、利用形態に応じて作者へ確認してください。
