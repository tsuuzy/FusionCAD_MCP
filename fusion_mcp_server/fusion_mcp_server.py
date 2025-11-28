# fusion_mcp_server.py
"""
Fusion 360 MCP Add-in - 動的Pythonコード実行対応版

このアドインは、adsk.core と adsk.fusion の全APIを
動的に実行できるようにすることで、拡張性を大幅に向上させています。
"""
import adsk.core, adsk.fusion, adsk.cam, traceback
import threading
import time
import os
import math
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from functools import partial
from io import StringIO
import sys

# --- グローバル変数 ---
_app = None
_ui = None
_http_server = None
_http_server_thread = None
_stop_flag = None 
_command_received_event_id = 'FusionMCPCommandReceived'
_command_received_event = None
_event_handler = None
_last_response = None  # HTTP レスポンス用
_response_ready = threading.Event()

# HTTP サーバー設定
HTTP_HOST = '127.0.0.1'
HTTP_PORT = 8080


def write_response(message: str):
    """MCPサーバーへのレスポンスを設定する（HTTP用）"""
    global _last_response
    _last_response = message
    _response_ready.set()


# --- 動的コード実行エンジン ---

def execute_dynamic_code(code: str) -> dict:
    """
    任意のPythonコードを Fusion 360 のコンテキストで実行する。
    
    Args:
        code: 実行するPythonコード
        
    Returns:
        dict: {'success': bool, 'result': Any, 'output': str, 'error': str}
    """
    global _app, _ui
    
    # 標準出力をキャプチャ
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = StringIO()
    sys.stderr = StringIO()
    
    result = {
        'success': False,
        'result': None,
        'output': '',
        'error': ''
    }
    
    try:
        # 実行コンテキストを準備
        # adsk.core, adsk.fusion, adsk.cam と便利な変数を提供
        exec_globals = {
            'adsk': adsk,
            'core': adsk.core,
            'fusion': adsk.fusion,
            'cam': adsk.cam,
            'app': _app,
            'ui': _ui,
            'design': _app.activeProduct if _app.activeProduct and _app.activeProduct.productType == 'DesignProductType' else None,
            'root': _app.activeProduct.rootComponent if _app.activeProduct and hasattr(_app.activeProduct, 'rootComponent') else None,
            'math': math,
            'json': json,
            # よく使う型のショートカット
            'Point3D': adsk.core.Point3D,
            'Vector3D': adsk.core.Vector3D,
            'Matrix3D': adsk.core.Matrix3D,
            'ObjectCollection': adsk.core.ObjectCollection,
            'ValueInput': adsk.core.ValueInput,
        }
        
        exec_locals = {}
        
        # コードを実行
        exec(code, exec_globals, exec_locals)
        
        # 'result' 変数があれば結果として返す
        if 'result' in exec_locals:
            result['result'] = str(exec_locals['result'])
        
        result['success'] = True
        result['output'] = sys.stdout.getvalue()
        
    except Exception as e:
        result['success'] = False
        result['error'] = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        result['output'] = sys.stdout.getvalue()
        
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
    
    return result


def get_api_info(module_path: str = None, object_type: str = None) -> dict:
    """
    Fusion 360 APIの情報を取得する。
    
    Args:
        module_path: モジュールパス (例: 'adsk.fusion.BRepBody')
        object_type: オブジェクトタイプ (例: 'Component')
        
    Returns:
        dict: APIの情報（メソッド、プロパティ、ドキュメントなど）
    """
    result = {
        'success': False,
        'info': {},
        'error': ''
    }
    
    try:
        if module_path:
            # モジュールパスからオブジェクトを取得
            parts = module_path.split('.')
            obj = adsk
            for part in parts[1:]:  # 'adsk' をスキップ
                obj = getattr(obj, part)
        elif object_type:
            # 一般的なタイプを検索
            if hasattr(adsk.fusion, object_type):
                obj = getattr(adsk.fusion, object_type)
            elif hasattr(adsk.core, object_type):
                obj = getattr(adsk.core, object_type)
            else:
                result['error'] = f"Unknown type: {object_type}"
                return result
        else:
            # デフォルトでモジュール一覧を返す
            result['info'] = {
                'modules': {
                    'adsk.core': [name for name in dir(adsk.core) if not name.startswith('_')],
                    'adsk.fusion': [name for name in dir(adsk.fusion) if not name.startswith('_')],
                    'adsk.cam': [name for name in dir(adsk.cam) if not name.startswith('_')]
                }
            }
            result['success'] = True
            return result
        
        # オブジェクトの情報を収集
        info = {
            'name': obj.__name__ if hasattr(obj, '__name__') else str(obj),
            'doc': obj.__doc__ if hasattr(obj, '__doc__') else '',
            'methods': [],
            'properties': [],
            'constants': []
        }
        
        for attr_name in dir(obj):
            if attr_name.startswith('_'):
                continue
            try:
                attr = getattr(obj, attr_name)
                if callable(attr):
                    doc = attr.__doc__ if hasattr(attr, '__doc__') else ''
                    info['methods'].append({
                        'name': attr_name,
                        'doc': doc[:200] if doc else ''  # ドキュメントを短縮
                    })
                elif isinstance(attr, (int, float, str, bool)):
                    info['constants'].append({
                        'name': attr_name,
                        'value': attr
                    })
                else:
                    info['properties'].append({
                        'name': attr_name,
                        'type': type(attr).__name__
                    })
            except:
                pass
        
        result['info'] = info
        result['success'] = True
        
    except Exception as e:
        result['error'] = f"{type(e).__name__}: {str(e)}"
    
    return result


def get_current_state() -> dict:
    """
    Fusion 360の現在の状態を取得する。
    
    Returns:
        dict: 現在のドキュメント、コンポーネント、ボディなどの情報
    """
    global _app, _ui
    
    result = {
        'success': False,
        'state': {},
        'error': ''
    }
    
    try:
        state = {
            'activeDocument': None,
            'activeProduct': None,
            'components': [],
            'bodies': [],
            'sketches': [],
            'features': [],
            'selections': []
        }
        
        # アクティブドキュメント
        if _app.activeDocument:
            state['activeDocument'] = {
                'name': _app.activeDocument.name,
                'isSaved': _app.activeDocument.isSaved
            }
        
        # アクティブプロダクト
        if _app.activeProduct:
            state['activeProduct'] = {
                'productType': _app.activeProduct.productType
            }
            
            # デザインの場合
            if _app.activeProduct.productType == 'DesignProductType':
                design = adsk.fusion.Design.cast(_app.activeProduct)
                root = design.rootComponent
                
                # コンポーネント
                def get_component_info(comp, level=0):
                    info = {
                        'name': comp.name,
                        'level': level,
                        'bodies': [b.name for b in comp.bRepBodies],
                        'sketches': [s.name for s in comp.sketches],
                        'occurrences': []
                    }
                    for occ in comp.occurrences:
                        info['occurrences'].append(get_component_info(occ.component, level + 1))
                    return info
                
                state['components'] = [get_component_info(root)]
                
                # ルートボディ
                state['bodies'] = [
                    {
                        'name': b.name,
                        'isVisible': b.isVisible,
                        'isSolid': b.isSolid,
                        'volume': b.volume if b.isSolid else 0,
                        'faces': b.faces.count,
                        'edges': b.edges.count
                    }
                    for b in root.bRepBodies
                ]
                
                # スケッチ
                state['sketches'] = [
                    {
                        'name': s.name,
                        'isVisible': s.isVisible,
                        'profiles': s.profiles.count
                    }
                    for s in root.sketches
                ]
                
                # フィーチャー（タイムライン）
                timeline = design.timeline
                state['features'] = [
                    {
                        'index': i,
                        'name': timeline.item(i).name if hasattr(timeline.item(i), 'name') else f'Feature_{i}',
                        'isSuppressed': timeline.item(i).isSuppressed
                    }
                    for i in range(timeline.count)
                ]
        
        # 選択状態
        if _ui.activeSelections:
            for i in range(_ui.activeSelections.count):
                sel = _ui.activeSelections.item(i)
                state['selections'].append({
                    'objectType': sel.entity.objectType,
                    'name': sel.entity.name if hasattr(sel.entity, 'name') else 'N/A'
                })
        
        result['state'] = state
        result['success'] = True
        
    except Exception as e:
        result['error'] = f"{type(e).__name__}: {str(e)}"
    
    return result


# --- HTTP サーバー ---

class FusionHTTPHandler(BaseHTTPRequestHandler):
    """HTTP リクエストを処理するハンドラ"""
    
    def log_message(self, format, *args):
        # ログ出力を抑制（必要なら有効化）
        pass
    
    def do_POST(self):
        global _last_response
        
        if self.path == '/command':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data.decode('utf-8'))
                command = data.get('command', '')
                
                # レスポンスをリセット
                _last_response = None
                _response_ready.clear()
                
                # Fusion のメインスレッドでコマンドを実行
                _app.fireCustomEvent(_command_received_event_id, command)
                
                # レスポンスを待つ（最大30秒）
                if _response_ready.wait(timeout=30.0):
                    response = {'status': 'success', 'message': _last_response}
                else:
                    response = {'status': 'timeout', 'message': 'Command execution timeout'}
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode('utf-8'))
                
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                error_response = {'status': 'error', 'message': str(e)}
                self.wfile.write(json.dumps(error_response).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_GET(self):
        """ヘルスチェック用"""
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok'}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()


def run_http_server(stop_flag):
    """HTTP サーバーを別スレッドで実行"""
    global _http_server
    try:
        _http_server = HTTPServer((HTTP_HOST, HTTP_PORT), FusionHTTPHandler)
        _http_server.timeout = 1.0  # 1秒ごとにチェック
        
        while not stop_flag.is_set():
            _http_server.handle_request()
    except Exception as e:
        if _ui:
            _ui.palettes.itemById('TextCommands').writeText(f"HTTP Server error: {str(e)}")
    finally:
        if _http_server:
            _http_server.server_close() 


# --- イベントハンドラ ---

class CommandReceivedEventHandler(adsk.core.CustomEventHandler):
    """カスタムイベントを受け取ってコマンドを処理するハンドラ
    
    JSONベースのコマンド形式をサポート:
    - execute_code: 任意のPythonコードを実行
    - get_api_info: APIのドキュメント情報を取得
    - get_state: 現在のドキュメント/モデルの状態を取得
    """
    def __init__(self):
        super().__init__()
        
    def notify(self, args):
        try:
            command_str = args.additionalInfo
            
            # JSONコマンドを処理
            if command_str.startswith('{'):
                self._handle_json_command(command_str)
            else:
                # 非JSONコマンドはエラー
                write_response(json.dumps({
                    'success': False,
                    'error': f"Invalid command format. Expected JSON. Got: {command_str[:100]}"
                }))
                
        except:
            err_msg = f'An unexpected error occurred in notify handler:\n{traceback.format_exc()}'
            write_response(json.dumps({'success': False, 'error': err_msg}))
    
    def _handle_json_command(self, command_str: str):
        """JSON形式のコマンドを処理する"""
        try:
            cmd = json.loads(command_str)
            cmd_type = cmd.get('type', '')
            
            if cmd_type == 'execute_code':
                # 動的Pythonコード実行
                code = cmd.get('code', '')
                _ui.palettes.itemById('TextCommands').writeText(f"Executing dynamic code...")
                result = execute_dynamic_code(code)
                write_response(json.dumps(result, ensure_ascii=False, default=str))
                
            elif cmd_type == 'get_api_info':
                # API情報取得
                module_path = cmd.get('module_path')
                object_type = cmd.get('object_type')
                result = get_api_info(module_path, object_type)
                write_response(json.dumps(result, ensure_ascii=False, default=str))
                
            elif cmd_type == 'get_state':
                # 現在の状態取得
                result = get_current_state()
                write_response(json.dumps(result, ensure_ascii=False, default=str))
                
            else:
                write_response(json.dumps({
                    'success': False,
                    'error': f"Unknown JSON command type: {cmd_type}"
                }))
                
        except json.JSONDecodeError as e:
            write_response(json.dumps({
                'success': False,
                'error': f"Invalid JSON: {str(e)}"
            }))
        except Exception as e:
            write_response(json.dumps({
                'success': False,
                'error': f"{type(e).__name__}: {str(e)}"
            }))


# --- アドインのメインライフサイクル ---

def run(context):
    global _app, _ui, _http_server_thread, _stop_flag, _command_received_event, _event_handler

    _app = adsk.core.Application.get()
    _ui  = _app.userInterface

    try:
        _command_received_event = _app.registerCustomEvent(_command_received_event_id)
        _event_handler = CommandReceivedEventHandler()
        _command_received_event.add(_event_handler)
    except:
        _ui.messageBox(f'Failed to register custom event:\n{traceback.format_exc()}')
        return

    # HTTP サーバーを開始
    _stop_flag = threading.Event()
    _http_server_thread = threading.Thread(target=run_http_server, args=(_stop_flag,))
    _http_server_thread.daemon = True
    _http_server_thread.start()

    _ui.palettes.itemById('TextCommands').writeText(f"Fusion MCP Add-in (HTTP) started. Listening on http://{HTTP_HOST}:{HTTP_PORT}")


def stop(context):
    global _http_server
    
    if _stop_flag:
        _stop_flag.set()
    
    if _http_server:
        try:
            _http_server.shutdown()
        except:
            pass
    
    if _command_received_event and _event_handler:
        _command_received_event.remove(_event_handler)
        _app.unregisterCustomEvent(_command_received_event_id)

    _ui.palettes.itemById('TextCommands').writeText("Fusion MCP Add-in has stopped.")

