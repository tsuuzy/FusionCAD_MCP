# Fusion 360 MCP Server セットアップガイド

このプロジェクトは、GitHub Copilot/Claude から MCP (Model Context Protocol) 経由で Fusion 360 を制御するためのシステムです。

## アーキテクチャ

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│  GitHub Copilot │────>│  MCP Bridge Server   │────>│  Fusion 360 Add-in  │
│  / Claude       │ MCP │  (mcp_bridge_server) │FILE │  (fusion_mcp_server)│
└─────────────────┘     └──────────────────────┘     └─────────────────────┘
```

## セットアップ手順

### 1. Python依存パッケージのインストール

```powershell
cd E:\work\FusionCAD_MCP
pip install -r requirements.txt
```

### 2. ファイルパスの設定

`mcp_bridge_server.py` と `fusion_mcp_server/fusion_mcp_server.py` の両方で、以下のパスを環境に合わせて変更してください：

```python
# コマンドファイル（MCPサーバー → Fusion Add-in）
COMMAND_FILE_PATH = 'C:\\Users\\YOUR_USERNAME\\Documents\\fusion_command.txt'

# レスポンスファイル（Fusion Add-in → MCPサーバー）
RESPONSE_FILE_PATH = 'C:\\Users\\YOUR_USERNAME\\Documents\\fusion_response.txt'
```

### 3. Fusion 360 Add-in のインストール

1. `fusion_mcp_server` フォルダを Fusion 360 の Add-ins フォルダにコピー：
   - Windows: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\`
   
2. Fusion 360 を起動し、スクリプトとアドイン (SHIFT+S) から `fusion_mcp_server` を実行

### 4. VS Code / Claude Desktop での MCP 設定

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
          "FUSION_COMMAND_FILE": "C:\\Users\\tomo123\\Documents\\fusion_command.txt",
          "FUSION_RESPONSE_FILE": "C:\\Users\\tomo123\\Documents\\fusion_response.txt"
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
        "FUSION_COMMAND_FILE": "C:\\Users\\tomo123\\Documents\\fusion_command.txt",
        "FUSION_RESPONSE_FILE": "C:\\Users\\tomo123\\Documents\\fusion_response.txt"
      }
    }
  }
}
```

## 利用可能なコマンド（MCPツール）

### 基本形状作成
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

GitHub Copilot / Claude に以下のように指示できます：

```
「Fusion 360 で 20mm の立方体を作成して」
「半径10mm、高さ30mmの円柱を作って MyCylinder と名前を付けて」
「MyCube と MyCylinder を結合して」
「選択したボディを X 方向に 50mm 移動して」
```

## トラブルシューティング

### MCPサーバーが接続できない
1. Python と mcp パッケージがインストールされているか確認
2. ファイルパスが正しいか確認
3. Fusion 360 の Add-in が実行中か確認

### コマンドが実行されない
1. `fusion_command.txt` が指定したパスに作成されるか確認
2. Fusion 360 のテキストコマンドパレットにログが出力されているか確認

### レスポンスが返らない
1. `fusion_response.txt` のパスを確認
2. Fusion Add-in のエラーログを確認
