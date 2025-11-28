# Fusion 360 MCP Server セットアップガイド

このプロジェクトは、GitHub Copilot/Claude から MCP (Model Context Protocol) 経由で Fusion 360 を制御するためのシステムです。

## 🚀 新機能: 動的API実行

**adsk.core、adsk.fusion、adsk.cam の全APIに動的にアクセス可能になりました！**

従来は機能ごとに関数を作成する必要がありましたが、新しい `execute_fusion_code` ツールを使用することで、任意のPythonコードをFusion 360内で実行できます。

```python
# 例: カスタムスケッチとパス押し出しを作成
sketch = root.sketches.add(root.xYConstructionPlane)
sketch.sketchCurves.sketchLines.addByTwoPoints(
    Point3D.create(0, 0, 0),
    Point3D.create(10, 0, 0)
)
# ... 任意のFusion API操作
```

## アーキテクチャ

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│  GitHub Copilot │────>│  MCP Bridge Server   │────>│  Fusion 360 Add-in  │
│  / Claude       │ MCP │  (mcp_bridge_server) │HTTP │  (fusion_mcp_server)│
└─────────────────┘     └──────────────────────┘     └─────────────────────┘
```

## セットアップ手順

### 1. Python依存パッケージのインストール

```powershell
cd E:\work\FusionCAD_MCP
pip install -r requirements.txt
```

### 2. Fusion 360 Add-in のインストール

1. `fusion_mcp_server` フォルダを Fusion 360 の Add-ins フォルダにコピー：
   - Windows: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\`
   
2. Fusion 360 を起動し、スクリプトとアドイン (SHIFT+S) から `fusion_mcp_server` を実行
   - HTTPサーバーが `http://127.0.0.1:8080` で起動します

### 3. VS Code / Claude Desktop での MCP 設定

#### VS Code (GitHub Copilot) の場合

`.vscode/settings.json` に以下を追加：

```json
{
  "github.copilot.chat.codeGeneration.useInstructionFiles": true,
  "mcp": {
    "servers": {
      "fusion-cad": {
        "command": "python",
        "args": ["E:\\work\\FusionCAD_MCP\\mcp_bridge_server.py"],
        "env": {
          "FUSION_HTTP_HOST": "localhost",
          "FUSION_HTTP_PORT": "8080"
        }
      }
    }
  }
}
```

#### Claude Desktop の場合

`%APPDATA%\Claude\claude_desktop_config.json` に以下を追加：

```json
{
  "mcpServers": {
    "fusion-cad": {
      "command": "python",
      "args": ["E:\\work\\FusionCAD_MCP\\mcp_bridge_server.py"],
      "env": {
        "FUSION_HTTP_HOST": "localhost",
        "FUSION_HTTP_PORT": "8080"
      }
    }
  }
}
```

## 利用可能なツール

### 🆕 動的APIツール

| ツール名 | 説明 |
|---------|------|
| `execute_fusion_code` | 任意のPythonコードをFusion 360で実行 |
| `get_fusion_api_info` | APIのドキュメント情報を取得 |
| `get_fusion_state` | 現在のドキュメント/モデルの状態を取得 |

#### execute_fusion_code の使い方

コード内で利用可能な事前定義変数：
- `app`: adsk.core.Application インスタンス
- `ui`: adsk.core.UserInterface インスタンス
- `design`: 現在のDesign
- `root`: ルートコンポーネント
- `Point3D`, `Vector3D`, `Matrix3D`, `ObjectCollection`, `ValueInput`: よく使う型

```python
# 例1: 全ボディの情報を取得
result = []
for body in root.bRepBodies:
    result.append({
        'name': body.name,
        'volume': body.volume,
        'faces': body.faces.count
    })

# 例2: パラメータを操作
params = design.userParameters
param = params.itemByName('width')
if param:
    param.expression = '50 mm'

# 例3: カスタム形状を作成
sketch = root.sketches.add(root.xYConstructionPlane)
lines = sketch.sketchCurves.sketchLines
# L字型を描画
lines.addByTwoPoints(Point3D.create(0, 0, 0), Point3D.create(3, 0, 0))
lines.addByTwoPoints(Point3D.create(3, 0, 0), Point3D.create(3, 1, 0))
lines.addByTwoPoints(Point3D.create(3, 1, 0), Point3D.create(1, 1, 0))
lines.addByTwoPoints(Point3D.create(1, 1, 0), Point3D.create(1, 2, 0))
lines.addByTwoPoints(Point3D.create(1, 2, 0), Point3D.create(0, 2, 0))
lines.addByTwoPoints(Point3D.create(0, 2, 0), Point3D.create(0, 0, 0))

# 押し出し
prof = sketch.profiles.item(0)
extrudes = root.features.extrudeFeatures
extInput = extrudes.createInput(prof, fusion.FeatureOperations.NewBodyFeatureOperation)
extInput.setDistanceExtent(False, ValueInput.createByReal(1))
extrudes.add(extInput)

result = "L-shaped extrusion created!"
```

### 基本形状作成（便利なショートカット）
| ツール名 | 説明 | 必須パラメータ |
|---------|------|---------------|
| `create_cube` | 立方体を作成 | size (mm) |
| `create_cylinder` | 円柱を作成 | radius, height (mm) |
| `create_box` | 直方体を作成 | width, depth, height (mm) |
| `create_sphere` | 球を作成 | radius (mm) |
| `create_cone` | 円錐を作成 | radius, height (mm) |
| `create_sq_pyramid` | 四角錐を作成 | side_length, height (mm) |
| `create_tri_pyramid` | 正三角錐を作成 | side_length, height (mm) |

### 選択操作
| ツール名 | 説明 | 必須パラメータ |
|---------|------|---------------|
| `select_body` | ボディを1つ選択 | body_name |
| `select_bodies` | ボディを2つ選択 | body_name1, body_name2 |
| `select_edges` | エッジを選択 | body_name, edge_type (all/circular) |

### 編集操作
| ツール名 | 説明 | 必須パラメータ |
|---------|------|---------------|
| `add_fillet` | フィレットを追加 | radius (mm) |
| `move_selection` | 選択を移動 | x_dist, y_dist, z_dist (mm) |
| `rotate_selection` | 選択を回転 | axis, angle, cx, cy, cz |

### ブール演算
| ツール名 | 説明 | 必須パラメータ |
|---------|------|---------------|
| `combine_selection` | 選択した2ボディを演算 | operation (join/cut/intersect) |
| `combine_by_name` | 名前指定でブール演算 | target_body, tool_body, operation |

### 履歴操作
| ツール名 | 説明 |
|---------|------|
| `undo` | 元に戻す |
| `redo` | やり直す |

## 使用例

### 基本的な使い方
```
「Fusion 360 で 20mm の立方体を作成して」
「半径10mm、高さ30mmの円柱を作って MyCylinder と名前を付けて」
「MyCube と MyCylinder を結合して」
```

### 動的API実行
```
「Fusion 360 でスプライン曲線を使ったカスタム形状を作成して」
「現在のモデルの全パラメータを表示して」
「選択したフェイスにテキストを刻印して」
「STEPファイルをエクスポートして」
```

## API リファレンス

動的APIを使用する際は、以下のAutodesk公式ドキュメントを参照してください：

- [Fusion 360 API リファレンス](https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-A92A4B10-3781-4925-94C6-47DA85A4F65A)
- [adsk.fusion モジュール](https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-7B5A90C8-E94C-48DA-B16B-430729B734DC)
- [adsk.core モジュール](https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-0F9C3BE1-5CB9-4B1A-A2C1-FD27B9E4B53D)

## トラブルシューティング

### MCPサーバーが接続できない
1. Python と mcp パッケージがインストールされているか確認
2. Fusion 360 の Add-in が実行中か確認（HTTPサーバーが起動しているか）
3. `http://localhost:8080/health` にアクセスして動作確認

### コマンドが実行されない
1. Fusion 360 のテキストコマンドパレットにログが出力されているか確認
2. Add-in のエラーログを確認

### 動的コードが失敗する
1. `get_fusion_state` で現在の状態を確認
2. `get_fusion_api_info` で使用するAPIのドキュメントを確認
3. エラーメッセージを確認し、コードを修正
