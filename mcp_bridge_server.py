#!/usr/bin/env python3
"""
Fusion 360 MCP Bridge Server - 動的API対応版
GitHub Copilot/Claude から Fusion 360 を制御するための MCP サーバー

このバージョンでは、adsk.core と adsk.fusion の全APIに
動的にアクセスできるようになっています。
"""

import asyncio
import json
import os
import sys
import urllib.request
import urllib.error
from typing import Any

# MCP SDK のインポート
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
)

# Fusion Add-in の HTTP サーバーアドレス
FUSION_HTTP_HOST = os.environ.get('FUSION_HTTP_HOST', 'localhost')
FUSION_HTTP_PORT = int(os.environ.get('FUSION_HTTP_PORT', '8080'))

# MCPサーバーのインスタンス
app = Server("fusion-cad-mcp-server")

# プロキシを無効化（localhost 接続用）
proxy_handler = urllib.request.ProxyHandler({})
opener = urllib.request.build_opener(proxy_handler)
urllib.request.install_opener(opener)


def send_command_to_fusion(command: str, timeout: float = 30.0) -> str:
    """
    HTTPでFusion Add-inにコマンドを送信し、レスポンスを受け取る
    プロキシを使用せずに直接接続
    """
    try:
        url = f"http://{FUSION_HTTP_HOST}:{FUSION_HTTP_PORT}/command"
        data = json.dumps({"command": command}).encode('utf-8')
        
        req = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        
        # プロキシを使用しないopenerを毎回作成して使用
        no_proxy_handler = urllib.request.ProxyHandler({})
        opener = urllib.request.build_opener(no_proxy_handler)
        
        with opener.open(req, timeout=timeout) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get('message', 'Command executed')
    
    except urllib.error.URLError as e:
        return f"Error: Fusion 360 Add-in に接続できません。Add-in が実行中か確認してください。({str(e)})"
    except Exception as e:
        return f"Error: {str(e)}"


def send_json_command(cmd_type: str, **kwargs) -> dict:
    """
    JSON形式のコマンドをFusion Add-inに送信する
    
    Args:
        cmd_type: コマンドタイプ（execute_code, get_api_info, get_state）
        **kwargs: コマンドに応じた追加パラメータ
        
    Returns:
        dict: Fusion Add-inからのレスポンス
    """
    try:
        command = json.dumps({'type': cmd_type, **kwargs})
        result_str = send_command_to_fusion(command)
        
        # JSONレスポンスをパース
        try:
            return json.loads(result_str)
        except json.JSONDecodeError:
            return {'success': False, 'error': result_str, 'raw': result_str}
            
    except Exception as e:
        return {'success': False, 'error': str(e)}


@app.list_tools()
async def list_tools() -> list[Tool]:
    """
    利用可能なツール（Fusionコマンド）の一覧を返す
    
    動的APIツール:
    - execute_fusion_code: 任意のPythonコードを実行
    - get_fusion_api_info: API情報を取得
    - get_fusion_state: 現在の状態を取得
    """
    return [
        Tool(
            name="execute_fusion_code",
            description="""Fusion 360で任意のPythonコードを実行します。
            
adsk.core, adsk.fusion, adsk.cam の全APIにアクセス可能です。

利用可能な事前定義変数:
- app: adsk.core.Application インスタンス
- ui: adsk.core.UserInterface インスタンス
- design: 現在のDesign (ある場合)
- root: ルートコンポーネント (ある場合)
- Point3D, Vector3D, Matrix3D, ObjectCollection, ValueInput: よく使う型

コード内で 'result' 変数に値を代入すると、その値が返されます。
print() の出力も 'output' として返されます。

例1: ボディ一覧を取得
```python
result = [b.name for b in root.bRepBodies]
```

例2: スケッチを作成して円を描く
```python
sketch = root.sketches.add(root.xYConstructionPlane)
circles = sketch.sketchCurves.sketchCircles
circle = circles.addByCenterRadius(Point3D.create(0, 0, 0), 2.0)
result = f"Circle created with radius {circle.radius}"
```

例3: パラメトリック設計
```python
params = design.allParameters
for p in params:
    print(f"{p.name} = {p.expression}")
```

例4: 立方体を作成
```python
sketch = root.sketches.add(root.xYConstructionPlane)
lines = sketch.sketchCurves.sketchLines
lines.addTwoPointRectangle(Point3D.create(-1, -1, 0), Point3D.create(1, 1, 0))
prof = sketch.profiles.item(0)
extrudes = root.features.extrudeFeatures
extInput = extrudes.createInput(prof, fusion.FeatureOperations.NewBodyFeatureOperation)
extInput.setDistanceExtent(False, ValueInput.createByReal(2))
extrudes.add(extInput)
result = "Cube created!"
```""",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "実行するPythonコード。adsk.core/fusion/cam の全APIが使用可能"
                    }
                },
                "required": ["code"]
            }
        ),
        Tool(
            name="get_fusion_api_info",
            description="""Fusion 360 APIのドキュメント情報を取得します。

モジュールやクラスのメソッド、プロパティ、定数などの情報を取得できます。

使用例:
- module_path="adsk.fusion.BRepBody" でBRepBodyクラスの情報を取得
- object_type="Component" でComponentの情報を取得
- 両方省略でモジュール一覧を取得""",
            inputSchema={
                "type": "object",
                "properties": {
                    "module_path": {
                        "type": "string",
                        "description": "モジュールパス (例: 'adsk.fusion.ExtrudeFeatures')"
                    },
                    "object_type": {
                        "type": "string",
                        "description": "オブジェクトタイプ名 (例: 'Sketch', 'Component')"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="get_fusion_state",
            description="""Fusion 360の現在の状態を取得します。

以下の情報を返します:
- アクティブドキュメント情報
- コンポーネント階層
- ボディ一覧（名前、可視性、体積、面/エッジ数）
- スケッチ一覧
- フィーチャー（タイムライン）一覧
- 現在の選択状態""",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """
    ツールを実行し、Fusion Add-inにコマンドを送信する
    """
    try:
        if name == "execute_fusion_code":
            code = arguments.get("code", "")
            result = send_json_command("execute_code", code=code)
            
            if result.get('success'):
                output_parts = []
                if result.get('output'):
                    output_parts.append(f"Output:\n{result['output']}")
                if result.get('result'):
                    output_parts.append(f"Result: {result['result']}")
                if not output_parts:
                    output_parts.append("Code executed successfully (no output)")
                return [TextContent(type="text", text="\n".join(output_parts))]
            else:
                return [TextContent(type="text", text=f"Error: {result.get('error', 'Unknown error')}")]
        
        elif name == "get_fusion_api_info":
            module_path = arguments.get("module_path")
            object_type = arguments.get("object_type")
            result = send_json_command("get_api_info", module_path=module_path, object_type=object_type)
            
            if result.get('success'):
                info = result.get('info', {})
                return [TextContent(type="text", text=json.dumps(info, indent=2, ensure_ascii=False))]
            else:
                return [TextContent(type="text", text=f"Error: {result.get('error', 'Unknown error')}")]
        
        elif name == "get_fusion_state":
            result = send_json_command("get_state")
            
            if result.get('success'):
                state = result.get('state', {})
                return [TextContent(type="text", text=json.dumps(state, indent=2, ensure_ascii=False))]
            else:
                return [TextContent(type="text", text=f"Error: {result.get('error', 'Unknown error')}")]
        
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
            
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    """
    MCPサーバーのメインエントリポイント
    """
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
