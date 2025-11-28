#!/usr/bin/env python3
"""
Fusion 360 MCP Bridge Server
GitHub Copilot/Claude から Fusion 360 を制御するための MCP サーバー
"""

import asyncio
import json
import os
import sys
import time
from typing import Any

# MCP SDK のインポート
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
)

# コマンドファイルのパス（Fusion Add-in と共有）
COMMAND_FILE_PATH = os.environ.get(
    'FUSION_COMMAND_FILE',
    'C:\\Users\\tomo123\\Documents\\fusion_command.txt'
)

RESPONSE_FILE_PATH = os.environ.get(
    'FUSION_RESPONSE_FILE', 
    'C:\\Users\\tomo123\\Documents\\fusion_response.txt'
)

# MCPサーバーのインスタンス
app = Server("fusion-cad-mcp-server")


def send_command_to_fusion(command: str, timeout: float = 10.0) -> str:
    """
    コマンドをFusion Add-inに送信し、レスポンスを待つ
    """
    try:
        # レスポンスファイルをクリア（リトライ付き）
        for _ in range(5):
            try:
                if os.path.exists(RESPONSE_FILE_PATH):
                    os.remove(RESPONSE_FILE_PATH)
                break
            except PermissionError:
                time.sleep(0.2)
        
        # コマンドをファイルに書き込み
        with open(COMMAND_FILE_PATH, 'w', encoding='utf-8') as f:
            f.write(command)
        
        # レスポンスを待つ（タイムアウト付き）
        start_time = time.time()
        while time.time() - start_time < timeout:
            if os.path.exists(RESPONSE_FILE_PATH):
                # ファイルが書き込み完了するまで少し待つ
                time.sleep(0.3)
                try:
                    with open(RESPONSE_FILE_PATH, 'r', encoding='utf-8') as f:
                        response = f.read().strip()
                        if response:
                            try:
                                os.remove(RESPONSE_FILE_PATH)
                            except PermissionError:
                                pass  # 削除できなくても続行
                            return response
                except PermissionError:
                    time.sleep(0.2)
                    continue
            time.sleep(0.1)
        
        return f"Command sent: {command} (no response received within {timeout}s)"
    
    except Exception as e:
        return f"Error sending command: {str(e)}"


@app.list_tools()
async def list_tools() -> list[Tool]:
    """
    利用可能なツール（Fusionコマンド）の一覧を返す
    """
    return [
        # === 基本形状作成 ===
        Tool(
            name="create_cube",
            description="Fusion 360で立方体を作成します。サイズはmmで指定。",
            inputSchema={
                "type": "object",
                "properties": {
                    "size": {
                        "type": "number",
                        "description": "立方体の一辺のサイズ (mm)"
                    },
                    "name": {
                        "type": "string",
                        "description": "ボディの名前（オプション）"
                    },
                    "plane": {
                        "type": "string",
                        "enum": ["xy", "yz", "xz"],
                        "description": "作成する平面 (デフォルト: xy)"
                    },
                    "cx": {
                        "type": "number",
                        "description": "中心X座標 (mm, デフォルト: 0)"
                    },
                    "cy": {
                        "type": "number",
                        "description": "中心Y座標 (mm, デフォルト: 0)"
                    },
                    "cz": {
                        "type": "number",
                        "description": "中心Z座標 (mm, デフォルト: 0)"
                    }
                },
                "required": ["size"]
            }
        ),
        Tool(
            name="create_cylinder",
            description="Fusion 360で円柱を作成します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "radius": {
                        "type": "number",
                        "description": "円柱の半径 (mm)"
                    },
                    "height": {
                        "type": "number",
                        "description": "円柱の高さ (mm)"
                    },
                    "name": {
                        "type": "string",
                        "description": "ボディの名前（オプション）"
                    },
                    "plane": {
                        "type": "string",
                        "enum": ["xy", "yz", "xz"],
                        "description": "作成する平面 (デフォルト: xy)"
                    },
                    "cx": {"type": "number", "description": "中心X座標 (mm)"},
                    "cy": {"type": "number", "description": "中心Y座標 (mm)"},
                    "cz": {"type": "number", "description": "中心Z座標 (mm)"}
                },
                "required": ["radius", "height"]
            }
        ),
        Tool(
            name="create_box",
            description="Fusion 360で直方体（ボックス）を作成します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "width": {"type": "number", "description": "幅 (mm)"},
                    "depth": {"type": "number", "description": "奥行き (mm)"},
                    "height": {"type": "number", "description": "高さ (mm)"},
                    "name": {"type": "string", "description": "ボディの名前"},
                    "plane": {"type": "string", "enum": ["xy", "yz", "xz"]},
                    "cx": {"type": "number", "description": "中心X座標 (mm)"},
                    "cy": {"type": "number", "description": "中心Y座標 (mm)"},
                    "cz": {"type": "number", "description": "中心Z座標 (mm)"}
                },
                "required": ["width", "depth", "height"]
            }
        ),
        Tool(
            name="create_sphere",
            description="Fusion 360で球を作成します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "radius": {"type": "number", "description": "半径 (mm)"},
                    "name": {"type": "string", "description": "ボディの名前"},
                    "plane": {"type": "string", "enum": ["xy", "yz", "xz"]},
                    "cx": {"type": "number", "description": "中心X座標 (mm)"},
                    "cy": {"type": "number", "description": "中心Y座標 (mm)"},
                    "cz": {"type": "number", "description": "中心Z座標 (mm)"}
                },
                "required": ["radius"]
            }
        ),
        Tool(
            name="create_cone",
            description="Fusion 360で円錐を作成します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "radius": {"type": "number", "description": "底面の半径 (mm)"},
                    "height": {"type": "number", "description": "高さ (mm)"},
                    "name": {"type": "string", "description": "ボディの名前"},
                    "plane": {"type": "string", "enum": ["xy", "yz", "xz"]},
                    "cx": {"type": "number", "description": "中心X座標 (mm)"},
                    "cy": {"type": "number", "description": "中心Y座標 (mm)"},
                    "cz": {"type": "number", "description": "中心Z座標 (mm)"}
                },
                "required": ["radius", "height"]
            }
        ),
        Tool(
            name="create_sq_pyramid",
            description="Fusion 360で四角錐を作成します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "side_length": {"type": "number", "description": "底面の一辺の長さ (mm)"},
                    "height": {"type": "number", "description": "高さ (mm)"},
                    "name": {"type": "string", "description": "ボディの名前"},
                    "plane": {"type": "string", "enum": ["xy", "yz", "xz"]},
                    "cx": {"type": "number", "description": "中心X座標 (mm)"},
                    "cy": {"type": "number", "description": "中心Y座標 (mm)"},
                    "cz": {"type": "number", "description": "中心Z座標 (mm)"}
                },
                "required": ["side_length", "height"]
            }
        ),
        Tool(
            name="create_tri_pyramid",
            description="Fusion 360で正三角錐を作成します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "side_length": {"type": "number", "description": "底面の一辺の長さ (mm)"},
                    "height": {"type": "number", "description": "高さ (mm)"},
                    "name": {"type": "string", "description": "ボディの名前"},
                    "plane": {"type": "string", "enum": ["xy", "yz", "xz"]},
                    "cx": {"type": "number", "description": "中心X座標 (mm)"},
                    "cy": {"type": "number", "description": "中心Y座標 (mm)"},
                    "cz": {"type": "number", "description": "中心Z座標 (mm)"}
                },
                "required": ["side_length", "height"]
            }
        ),
        
        # === 選択操作 ===
        Tool(
            name="select_body",
            description="指定した名前のボディを選択します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "body_name": {"type": "string", "description": "選択するボディの名前"}
                },
                "required": ["body_name"]
            }
        ),
        Tool(
            name="select_bodies",
            description="指定した2つのボディを選択します（結合操作用）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "body_name1": {"type": "string", "description": "1つ目のボディの名前"},
                    "body_name2": {"type": "string", "description": "2つ目のボディの名前"}
                },
                "required": ["body_name1", "body_name2"]
            }
        ),
        Tool(
            name="select_edges",
            description="指定したボディのエッジを選択します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "body_name": {"type": "string", "description": "ボディの名前"},
                    "edge_type": {
                        "type": "string",
                        "enum": ["all", "circular"],
                        "description": "選択するエッジの種類"
                    }
                },
                "required": ["body_name", "edge_type"]
            }
        ),
        
        # === 編集操作 ===
        Tool(
            name="add_fillet",
            description="選択されているエッジにフィレット（角の丸み）を追加します。事前にselect_edgesでエッジを選択してください。",
            inputSchema={
                "type": "object",
                "properties": {
                    "radius": {"type": "number", "description": "フィレットの半径 (mm)"}
                },
                "required": ["radius"]
            }
        ),
        Tool(
            name="move_selection",
            description="選択されているボディを移動します。事前にselect_bodyでボディを選択してください。",
            inputSchema={
                "type": "object",
                "properties": {
                    "x_dist": {"type": "number", "description": "X方向の移動距離 (mm)"},
                    "y_dist": {"type": "number", "description": "Y方向の移動距離 (mm)"},
                    "z_dist": {"type": "number", "description": "Z方向の移動距離 (mm)"}
                },
                "required": ["x_dist", "y_dist", "z_dist"]
            }
        ),
        Tool(
            name="rotate_selection",
            description="選択されているボディを回転します。事前にselect_bodyでボディを選択してください。",
            inputSchema={
                "type": "object",
                "properties": {
                    "axis": {
                        "type": "string",
                        "enum": ["x", "y", "z"],
                        "description": "回転軸"
                    },
                    "angle": {"type": "number", "description": "回転角度 (度)"},
                    "cx": {"type": "number", "description": "回転中心X座標 (mm)"},
                    "cy": {"type": "number", "description": "回転中心Y座標 (mm)"},
                    "cz": {"type": "number", "description": "回転中心Z座標 (mm)"}
                },
                "required": ["axis", "angle", "cx", "cy", "cz"]
            }
        ),
        
        # === ブール演算 ===
        Tool(
            name="combine_selection",
            description="選択されている2つのボディを結合/切り取り/交差させます。事前にselect_bodiesで2つのボディを選択してください。",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["join", "cut", "intersect"],
                        "description": "操作の種類: join(結合), cut(切り取り), intersect(交差)"
                    }
                },
                "required": ["operation"]
            }
        ),
        Tool(
            name="combine_by_name",
            description="名前で指定した2つのボディに対してブール演算を実行します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "target_body": {"type": "string", "description": "ターゲットボディの名前（残る方）"},
                    "tool_body": {"type": "string", "description": "ツールボディの名前（操作に使用）"},
                    "operation": {
                        "type": "string",
                        "enum": ["join", "cut", "intersect"],
                        "description": "操作の種類"
                    }
                },
                "required": ["target_body", "tool_body", "operation"]
            }
        ),
        
        # === 履歴操作 ===
        Tool(
            name="undo",
            description="直前の操作を元に戻します。",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="redo",
            description="元に戻した操作をやり直します。",
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
        command = build_command(name, arguments)
        result = send_command_to_fusion(command)
        return [TextContent(type="text", text=result)]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


def build_command(name: str, args: dict[str, Any]) -> str:
    """
    ツール名と引数からFusion Add-in用のコマンド文字列を構築
    """
    
    if name == "create_cube":
        size = args.get("size", 10)
        body_name = args.get("name", "none")
        plane = args.get("plane", "xy")
        cx = args.get("cx", 0)
        cy = args.get("cy", 0)
        cz = args.get("cz", 0)
        return f"create_cube {size} {body_name} {plane} {cx} {cy} {cz}"
    
    elif name == "create_cylinder":
        radius = args.get("radius", 5)
        height = args.get("height", 10)
        body_name = args.get("name", "none")
        plane = args.get("plane", "xy")
        cx = args.get("cx", 0)
        cy = args.get("cy", 0)
        cz = args.get("cz", 0)
        return f"create_cylinder {radius} {height} {body_name} {plane} {cx} {cy} {cz}"
    
    elif name == "create_box":
        width = args.get("width", 10)
        depth = args.get("depth", 10)
        height = args.get("height", 10)
        body_name = args.get("name", "none")
        plane = args.get("plane", "xy")
        cx = args.get("cx", 0)
        cy = args.get("cy", 0)
        cz = args.get("cz", 0)
        return f"create_box {width} {depth} {height} {body_name} {plane} {cx} {cy} {cz}"
    
    elif name == "create_sphere":
        radius = args.get("radius", 5)
        body_name = args.get("name", "none")
        plane = args.get("plane", "xy")
        cx = args.get("cx", 0)
        cy = args.get("cy", 0)
        cz = args.get("cz", 0)
        return f"create_sphere {radius} {body_name} {plane} {cx} {cy} {cz}"
    
    elif name == "create_cone":
        radius = args.get("radius", 5)
        height = args.get("height", 10)
        body_name = args.get("name", "none")
        plane = args.get("plane", "xy")
        cx = args.get("cx", 0)
        cy = args.get("cy", 0)
        cz = args.get("cz", 0)
        return f"create_cone {radius} {height} {body_name} {plane} {cx} {cy} {cz}"
    
    elif name == "create_sq_pyramid":
        side = args.get("side_length", 10)
        height = args.get("height", 10)
        body_name = args.get("name", "none")
        plane = args.get("plane", "xy")
        cx = args.get("cx", 0)
        cy = args.get("cy", 0)
        cz = args.get("cz", 0)
        return f"create_sq_pyramid {side} {height} {body_name} {plane} {cx} {cy} {cz}"
    
    elif name == "create_tri_pyramid":
        side = args.get("side_length", 10)
        height = args.get("height", 10)
        body_name = args.get("name", "none")
        plane = args.get("plane", "xy")
        cx = args.get("cx", 0)
        cy = args.get("cy", 0)
        cz = args.get("cz", 0)
        return f"create_tri_pyramid {side} {height} {body_name} {plane} {cx} {cy} {cz}"
    
    elif name == "select_body":
        body_name = args.get("body_name", "")
        return f"select_body {body_name}"
    
    elif name == "select_bodies":
        body_name1 = args.get("body_name1", "")
        body_name2 = args.get("body_name2", "")
        return f"select_bodies {body_name1} {body_name2}"
    
    elif name == "select_edges":
        body_name = args.get("body_name", "")
        edge_type = args.get("edge_type", "all")
        return f"select_edges {body_name} {edge_type}"
    
    elif name == "add_fillet":
        radius = args.get("radius", 1)
        return f"add_fillet {radius}"
    
    elif name == "move_selection":
        x = args.get("x_dist", 0)
        y = args.get("y_dist", 0)
        z = args.get("z_dist", 0)
        return f"move_selection {x} {y} {z}"
    
    elif name == "rotate_selection":
        axis = args.get("axis", "z")
        angle = args.get("angle", 0)
        cx = args.get("cx", 0)
        cy = args.get("cy", 0)
        cz = args.get("cz", 0)
        return f"rotate_selection {axis} {angle} {cx} {cy} {cz}"
    
    elif name == "combine_selection":
        operation = args.get("operation", "join")
        return f"combine_selection {operation}"
    
    elif name == "combine_by_name":
        target = args.get("target_body", "")
        tool = args.get("tool_body", "")
        operation = args.get("operation", "join")
        return f"combine_by_name {target} {tool} {operation}"
    
    elif name == "undo":
        return "undo"
    
    elif name == "redo":
        return "redo"
    
    else:
        raise ValueError(f"Unknown tool: {name}")


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
