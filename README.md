# ARig Tool

ARig Tool は Autodesk Maya 上でのキャラクターリギング作業を効率化するツールランチャーです。PySide2 ベースの UI から複数の補助スクリプトを呼び出し、ジョイントセットアップやドリブンキー編集、コントローラー補助などを一括で実行できます。([RigToolUI.py L171-L344](./RigToolUI.py#L171-L344))

## 必要環境

- Autodesk Maya 2020 以降（PySide2 / shiboken2 が利用可能な環境）([RigToolUI.py L1-L57](./RigToolUI.py#L1-L57))
- 本リポジトリの Python / MEL スクリプト一式

## 導入と起動方法

1. 本フォルダーを Maya の `scripts` パスに配置します。
2. Maya の Script Editor で次を実行するとランチャーが起動します。
   ```python
   import RigToolUI
   RigToolUI.RigToolLauncher.show_dialog()
   ```
   上記コードは PySide2 製のランチャーダイアログを生成し、ボタン経由で各スクリプトを呼び出せるようにします。([RigToolUI.py L295-L346](./RigToolUI.py#L295-L346))

## 注意

- ジョイントの向きは X Up で Y が X+ 方向に向いていることが前提になっている機能があります。

## 機能一覧

### ジョイントセットアップ

- **Create Twist Chain** — 選択したジョイントから参照ジョイントを自動検出し、`twistWeight` と `twistScaleMax` を備えたツイスト用補助ジョイントを指定数生成します。([RigToolUI.py L175-L205](./RigToolUI.py#L175-L205)) ([CreateTwistChain.py L525-L586](./CreateTwistChain.py#L525-L586))
- **Twist Chain Editor** — 選択ジョイント配下のツイストチェーンを一覧表示し、重みや最大スケール値を UI から編集できます。([RigToolUI.py L175-L205](./RigToolUI.py#L175-L205)) ([CreateTwistChain.py L1008-L1016](./CreateTwistChain.py#L1008-L1016))
- **Create Half Rotation Joint** — 選択ジョイントを複製して半回転ジョイントと `_Half_INF` を生成し、回転値を 0.5 倍で伝達します。スキップ設定は UI から切り替えられ、`halfrot_jnt` レイヤーへ自動追加されます。([RigToolUI.py L175-L205](./RigToolUI.py#L175-L205)) ([CreateHalfRotJoint.py L34-L399](./CreateHalfRotJoint.py#L34-L399))
- **Create Support Joint** — 選択ジョイント配下に半径を拡大したサポートジョイントを作成し、`support_jnt` レイヤーへ登録します。([RigToolUI.py L175-L205](./RigToolUI.py#L175-L205)) ([CreateSupportJoint.py L34-L73](./CreateSupportJoint.py#L34-L73))
- **Mirror Primary Joint** — `_L` / `_R` の命名規則を考慮してプライマリジョイント階層を反転複製し、名称調整と軸反転を自動処理します。([RigToolUI.py L175-L205](./RigToolUI.py#L175-L205)) ([MirrorPrimaryJoint.py L292-L340](./MirrorPrimaryJoint.py#L292-L340))
- **Mirror Twist & Half Joint** — ツイストチェーンや Half / Support ジョイントを反対側へ複製し、ドリブンキーやディスプレイレイヤー設定もコピーします。([RigToolUI.py L175-L205](./RigToolUI.py#L175-L205)) ([MirrorTwistHalfJoint.py L413-L457](./MirrorTwistHalfJoint.py#L413-L457))
- **Driven Key Helper** — ドライバー軸と対象属性を選んで Twist / Half / Support ジョイント向けのドリブンキーを一括設定する UI を提供します。([RigToolUI.py L175-L213](./RigToolUI.py#L175-L213)) ([DrivenKeyTool.py L640-L720](./DrivenKeyTool.py#L640-L720))
- **Driven Key Matrix** — 選択ジョイントのドリブンキーを行列表で可視化し、値の編集やミラー更新を行える管理ツールです。([RigToolUI.py L175-L213](./RigToolUI.py#L175-L213)) ([DrivenKeyMatrixTool.py L500-L540](./DrivenKeyMatrixTool.py#L500-L540))
- **Check Motion Tool** — チェックモーション用の回転プリセットをもとにジョイントへキーを打つバッチツールで、チェーンごとの設定やコピー・ペーストに対応します。([RigToolUI.py L205-L219](./RigToolUI.py#L205-L219)) ([CheckMotionTool.py L218-L395](./CheckMotionTool.py#L218-L395))
- **Bind Skin (Skip Half)** — Half ジョイントを除外しつつ `_Half_INF` ジョイントは含めてバインド用ジョイントリストを自動収集し、選択ジオメトリへスキンバインドします。([RigToolUI.py L205-L239](./RigToolUI.py#L205-L239)) ([SkinBindTool.py L45-L112](./SkinBindTool.py#L45-L112))
- **Simple Rig From Ctrl + Joints** — コントローラーとジョイントの選択からゼログループ付き複製コントローラーを配置し、親子とコンストレイントを自動構築します。([RigToolUI.py L205-L239](./RigToolUI.py#L205-L239)) ([csimplerig.py L16-L60](./csimplerig.py#L16-L60))
- **Create Eyelid Rig** — ベースコントローラーとまぶたジョイントを基に Aim / Parent Constraint を含むまぶたリグをセットアップし、複製コントローラーを選択状態にします。([RigToolUI.py L205-L239](./RigToolUI.py#L205-L239)) ([ArigUtil.py L83-L139](./ArigUtil.py#L83-L139))
- **Create Stretchy Spline IK** — 開始ジョイントと終了ジョイントを指定してスプライン IK とストレッチ制御、クラスタを自動作成します。([RigToolUI.py L205-L239](./RigToolUI.py#L205-L239)) ([ArigUtil.py L209-L253](./ArigUtil.py#L209-L253))

### コントローラー補助

- **Build Poly Loop** — 選択した複数トランスフォームの位置を頂点とする 1 フェースポリゴンを生成します。([RigToolUI.py L243-L275](./RigToolUI.py#L243-L275)) ([buildpoly.py L14-L28](./buildpoly.py#L14-L28))
- **Build Poly + Nearest Constrain** — メッシュとコントローラーからゼログループを生成し、最寄り頂点へ `pointOnPolyConstraint` で拘束します。([RigToolUI.py L243-L275](./RigToolUI.py#L243-L275)) ([ArigUtil.py L143-L197](./ArigUtil.py#L143-L197))
- **Nearest PointOnPoly Constraint** — 指定メッシュの最も近い頂点に各トランスフォームを拘束する `pointOnPolyConstraint` を設定します。([RigToolUI.py L243-L275](./RigToolUI.py#L243-L275)) ([NearestPOPConstraint.py L5-L42](./NearestPOPConstraint.py#L5-L42))
- **Connect Translate Attributes** — 最初に選択したノードの `translate` 属性を後続選択へ一括接続します。([RigToolUI.py L243-L275](./RigToolUI.py#L243-L275)) ([ArigUtil.py L14-L29](./ArigUtil.py#L14-L29))
- **Delete Constraints In Hierarchy** — 選択階層以下に存在する全てのコンストレイントノードを検出して削除します。([RigToolUI.py L243-L275](./RigToolUI.py#L243-L275)) ([ArigUtil.py L31-L60](./ArigUtil.py#L31-L60))
- **Create Matched Locators** — 選択オブジェクトの位置・回転に一致するロケータを生成し、結果を選択し直します。([RigToolUI.py L243-L275](./RigToolUI.py#L243-L275)) ([ArigUtil.py L256-L272](./ArigUtil.py#L256-L272))

### 外部ツール

- **LMRigger** — LMrigger 2.7.23 の UI を Maya 内で開きます。([RigToolUI.py L277-L289](./RigToolUI.py#L277-L289))
- **rig111 Wire Controllers** — 付属 MEL スクリプトをロードしてワイヤーコントローラー UI を起動します。([RigToolUI.py L277-L289](./RigToolUI.py#L277-L289))

## ライセンス

本リポジトリにライセンス表記が存在しないため、利用形態に応じて作者へ確認してください。
