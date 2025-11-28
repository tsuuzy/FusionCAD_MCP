# fusion_mcp_server.py
import adsk.core, adsk.fusion, traceback
import threading
import time
import os
import math
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from functools import partial

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

# --- ヘルパー関数 ---
def get_construction_plane(root: adsk.fusion.Component, plane_str: str):
    """文字列に応じて適切な構築平面を返す"""
    if plane_str and plane_str.lower() == 'yz':
        return root.yZConstructionPlane
    elif plane_str and plane_str.lower() == 'xz':
        return root.xZConstructionPlane
    else: # デフォルトまたは 'xy' の場合
        return root.xYConstructionPlane

# --- コマンド実行関数 ---

def create_cube(size: float, body_name: str = None, plane_str: str = 'xy', cx: float = 0, cy: float = 0, cz: float = 0):
    """指定されたサイズ、平面、中心点で立方体を作成し、名前を付ける"""
    try:
        root = _app.activeProduct.rootComponent
        plane = get_construction_plane(root, plane_str)
        sketch = root.sketches.add(plane)
        
        transform = sketch.transform
        transform.invert()
        
        p1_model = adsk.core.Point3D.create(cx - size / 2, cy - size / 2, cz)
        p2_model = adsk.core.Point3D.create(cx + size / 2, cy + size / 2, cz)

        p1_model.transformBy(transform)
        p2_model.transformBy(transform)

        sketch.sketchCurves.sketchLines.addTwoPointRectangle(p1_model, p2_model)

        prof = sketch.profiles.item(0)
        extrudes = root.features.extrudeFeatures
        extInput = extrudes.createInput(prof, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        distance = adsk.core.ValueInput.createByReal(size)
        extInput.setDistanceExtent(False, distance)
        
        extrude_feature = extrudes.add(extInput)
        new_body = extrude_feature.bodies.item(0)

        if body_name:
            new_body.name = body_name
        
        msg = f"SUCCESS: Cube '{new_body.name}' of size {size*10}mm created!"
        write_response(msg)
        _ui.messageBox(msg)
    except:
        err_msg = f"FAILED: create_cube - {traceback.format_exc()}"
        write_response(err_msg)
        if _ui:
            _ui.messageBox(f'Failed to create cube:\n{traceback.format_exc()}')


def create_cylinder(radius: float, height: float, body_name: str = None, plane_str: str = 'xy', cx: float = 0, cy: float = 0, cz: float = 0):
    """指定されたパラメータで円柱を作成し、名前を付ける"""
    try:
        root = _app.activeProduct.rootComponent
        plane = get_construction_plane(root, plane_str)
        sketch = root.sketches.add(plane)
        
        transform = sketch.transform
        transform.invert()
        
        center_point_model = adsk.core.Point3D.create(cx, cy, cz)
        center_point_model.transformBy(transform)

        sketch.sketchCurves.sketchCircles.addByCenterRadius(center_point_model, radius)

        prof = sketch.profiles.item(0)
        extrudes = root.features.extrudeFeatures
        extInput = extrudes.createInput(prof, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        distance = adsk.core.ValueInput.createByReal(height)
        extInput.setDistanceExtent(False, distance)
        extrude_feature = extrudes.add(extInput)

        new_body = extrude_feature.bodies.item(0)
        
        if body_name:
            new_body.name = body_name

        msg = f"SUCCESS: Cylinder '{new_body.name}' (radius:{radius*10}mm, height:{height*10}mm) created!"
        write_response(msg)
        _ui.messageBox(msg)
        
    except:
        err_msg = f"FAILED: create_cylinder - {traceback.format_exc()}"
        write_response(err_msg)
        if _ui:
            _ui.messageBox(f'Failed to create cylinder:\n{traceback.format_exc()}')


def create_box(width: float, depth: float, height: float, body_name: str = None, plane_str: str = 'xy', cx: float = 0, cy: float = 0, cz: float = 0):
    """指定されたパラメータで直方体を作成し、名前を付ける"""
    try:
        root = _app.activeProduct.rootComponent
        plane = get_construction_plane(root, plane_str)
        sketch = root.sketches.add(plane)
        
        transform = sketch.transform
        transform.invert()

        p1_model = adsk.core.Point3D.create(cx - width / 2, cy - depth / 2, cz)
        p2_model = adsk.core.Point3D.create(cx + width / 2, cy + depth / 2, cz)
        
        p1_model.transformBy(transform)
        p2_model.transformBy(transform)

        sketch.sketchCurves.sketchLines.addTwoPointRectangle(p1_model, p2_model)

        prof = sketch.profiles.item(0)
        extrudes = root.features.extrudeFeatures
        extInput = extrudes.createInput(prof, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        distance = adsk.core.ValueInput.createByReal(height)
        extInput.setDistanceExtent(False, distance)
        
        extrude_feature = extrudes.add(extInput)
        new_body = extrude_feature.bodies.item(0)

        if body_name:
            new_body.name = body_name
        
        msg = f"SUCCESS: Box '{new_body.name}' (W:{width*10}, D:{depth*10}, H:{height*10}mm) created!"
        write_response(msg)
        _ui.messageBox(msg)
    except:
        err_msg = f"FAILED: create_box - {traceback.format_exc()}"
        write_response(err_msg)
        if _ui:
            _ui.messageBox(f'Failed to create box:\n{traceback.format_exc()}')


def create_sphere(radius: float, body_name: str = None, plane_str: str = 'xy', cx: float = 0, cy: float = 0, cz: float = 0):
    """指定されたパラメータで球を作成し、名前を付ける"""
    try:
        root = _app.activeProduct.rootComponent
        
        # XZ平面にスケッチを作成（Y軸を回転軸として使用）
        tempSketch = root.sketches.add(root.xZConstructionPlane)
        
        # 半円を描画（X軸に沿って配置、Y軸で回転）
        # 円弧の中心を原点に、X方向にオフセットした半円を描く
        startPt = adsk.core.Point3D.create(radius, 0, 0)
        endPt = adsk.core.Point3D.create(-radius, 0, 0)
        centerPt = adsk.core.Point3D.create(0, 0, 0)
        
        # 3点で円弧を作成
        arc = tempSketch.sketchCurves.sketchArcs.addByThreePoints(
            startPt,
            adsk.core.Point3D.create(0, radius, 0),
            endPt
        )
        
        # 円弧の端点を直線で結ぶ
        tempSketch.sketchCurves.sketchLines.addByTwoPoints(arc.startSketchPoint, arc.endSketchPoint)
        
        prof = tempSketch.profiles.item(0)
        
        # Z軸を回転軸として使用
        revolves = root.features.revolveFeatures
        
        # 回転軸として直線を作成
        axisLine = tempSketch.sketchCurves.sketchLines.addByTwoPoints(
            adsk.core.Point3D.create(0, 0, -1),
            adsk.core.Point3D.create(0, 0, 1)
        )
        axisLine.isConstruction = True
        
        revolveInput = revolves.createInput(prof, axisLine, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        angle = adsk.core.ValueInput.createByReal(math.pi * 2)
        revolveInput.setAngleExtent(False, angle)

        revolveFeature = revolves.add(revolveInput)
        new_body = revolveFeature.bodies.item(0)
        
        tempSketch.isVisible = False
        
        # 指定された位置に移動
        if cx != 0 or cy != 0 or cz != 0:
            bodiesToMove = adsk.core.ObjectCollection.create()
            bodiesToMove.add(new_body)
            vector = adsk.core.Vector3D.create(cx, cy, cz)
            transform = adsk.core.Matrix3D.create()
            transform.translation = vector
            
            moveFeats = root.features.moveFeatures
            moveInput = moveFeats.createInput(bodiesToMove, transform)
            moveFeats.add(moveInput)
        
        if body_name:
            new_body.name = body_name

        msg = f"SUCCESS: Sphere '{new_body.name}' (radius:{radius*10}mm) created!"
        write_response(msg)
        _ui.messageBox(msg)
    except:
        err_msg = f"FAILED: create_sphere - {traceback.format_exc()}"
        write_response(err_msg)
        if _ui:
            _ui.messageBox(f'Failed to create sphere:\n{traceback.format_exc()}')


def create_cone(radius: float, height: float, body_name: str = None, plane_str: str = 'xy', cx: float = 0, cy: float = 0, cz: float = 0):
    """指定されたパラメータで円錐を作成し、名前を付ける"""
    try:
        root = _app.activeProduct.rootComponent
        plane = get_construction_plane(root, plane_str)
        sketch = root.sketches.add(plane)
        
        transform = sketch.transform
        transform.invert()

        p1_model = adsk.core.Point3D.create(cx, cy, cz)
        p2_model = adsk.core.Point3D.create(cx, cy, cz + height)
        p3_model = adsk.core.Point3D.create(cx + radius, cy, cz)
        
        p1_model.transformBy(transform)
        p2_model.transformBy(transform)
        p3_model.transformBy(transform)

        lines = sketch.sketchCurves.sketchLines
        line1 = lines.addByTwoPoints(p1_model, p2_model)
        lines.addByTwoPoints(p2_model, p3_model)
        lines.addByTwoPoints(p3_model, p1_model)

        prof = sketch.profiles.item(0)
        revolves = root.features.revolveFeatures
        revolve_input = revolves.createInput(prof, line1, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        angle = adsk.core.ValueInput.createByReal(math.pi * 2)
        revolve_input.setAngleExtent(False, angle)

        revolve_feature = revolves.add(revolve_input)
        new_body = revolve_feature.bodies.item(0)

        if body_name:
            new_body.name = body_name

        msg = f"SUCCESS: Cone '{new_body.name}' (radius:{radius*10}mm, height:{height*10}mm) created!"
        write_response(msg)
        _ui.messageBox(msg)
    except:
        err_msg = f"FAILED: create_cone - {traceback.format_exc()}"
        write_response(err_msg)
        if _ui:
            _ui.messageBox(f'Failed to create cone:\n{traceback.format_exc()}')
            

def create_sq_pyramid(side_length: float, height: float, body_name: str = None, plane_str: str = 'xy', cx: float = 0, cy: float = 0, cz: float = 0):
    """指定されたパラメータで四角錐を作成し、名前を付ける"""
    try:
        root = _app.activeProduct.rootComponent
        plane = get_construction_plane(root, plane_str)
        
        sketch_base = root.sketches.add(plane)
        s = side_length
        
        transform = sketch_base.transform
        transform.invert()
        
        p1_base_model = adsk.core.Point3D.create(cx - s/2, cy - s/2, cz)
        p2_base_model = adsk.core.Point3D.create(cx + s/2, cy + s/2, cz)
        p1_base_model.transformBy(transform)
        p2_base_model.transformBy(transform)
        sketch_base.sketchCurves.sketchLines.addTwoPointRectangle(p1_base_model, p2_base_model)
        prof_base = sketch_base.profiles.item(0)

        planes = root.constructionPlanes
        plane_input = planes.createInput()
        plane_input.setByOffset(plane, adsk.core.ValueInput.createByReal(height))
        plane_top = planes.add(plane_input)
        sketch_top = root.sketches.add(plane_top)

        top_point_model = adsk.core.Point3D.create(cx, cy, cz)
        top_point_model.transformBy(transform)
        top_point = sketch_top.sketchPoints.add(top_point_model)

        lofts = root.features.loftFeatures
        loft_input = lofts.createInput(adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        loft_input.loftSections.add(prof_base)
        loft_input.loftSections.add(top_point)
        
        loft_feature = lofts.add(loft_input)
        new_body = loft_feature.bodies.item(0)

        if body_name:
            new_body.name = body_name

        msg = f"SUCCESS: Square Pyramid '{new_body.name}' (base:{s*10}mm, height:{height*10}mm) created!"
        write_response(msg)
        _ui.messageBox(msg)
    except:
        err_msg = f"FAILED: create_sq_pyramid - {traceback.format_exc()}"
        write_response(err_msg)
        if _ui:
            _ui.messageBox(f'Failed to create square pyramid:\n{traceback.format_exc()}')


def create_tri_pyramid(side_length: float, height: float, body_name: str = None, plane_str: str = 'xy', cx: float = 0, cy: float = 0, cz: float = 0):
    """指定されたパラメータで正三角錐を作成し、名前を付ける"""
    try:
        root = _app.activeProduct.rootComponent
        plane = get_construction_plane(root, plane_str)
        
        sketch_base = root.sketches.add(plane)
        
        transform = sketch_base.transform
        transform.invert()
        
        s = side_length
        h_tri = s * math.sqrt(3) / 2
        
        p1_model = adsk.core.Point3D.create(cx - s/2, cy - h_tri/3, cz)
        p2_model = adsk.core.Point3D.create(cx + s/2, cy - h_tri/3, cz)
        p3_model = adsk.core.Point3D.create(cx, cy + h_tri*2/3, cz)
        
        p1_model.transformBy(transform)
        p2_model.transformBy(transform)
        p3_model.transformBy(transform)

        lines = sketch_base.sketchCurves.sketchLines
        lines.addByTwoPoints(p1_model, p2_model)
        lines.addByTwoPoints(p2_model, p3_model)
        lines.addByTwoPoints(p3_model, p1_model)
        prof_base = sketch_base.profiles.item(0)

        planes = root.constructionPlanes
        plane_input = planes.createInput()
        plane_input.setByOffset(plane, adsk.core.ValueInput.createByReal(height))
        plane_top = planes.add(plane_input)
        sketch_top = root.sketches.add(plane_top)
        
        top_point_model = adsk.core.Point3D.create(cx, cy, cz)
        top_point_model.transformBy(transform)
        top_point = sketch_top.sketchPoints.add(top_point_model)

        lofts = root.features.loftFeatures
        loft_input = lofts.createInput(adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        loft_input.loftSections.add(prof_base)
        loft_input.loftSections.add(top_point)
        
        loft_feature = lofts.add(loft_input)
        new_body = loft_feature.bodies.item(0)

        if body_name:
            new_body.name = body_name

        msg = f"SUCCESS: Triangular Pyramid '{new_body.name}' (base side:{s*10}mm, height:{height*10}mm) created!"
        write_response(msg)
        _ui.messageBox(msg)
    except:
        err_msg = f"FAILED: create_tri_pyramid - {traceback.format_exc()}"
        write_response(err_msg)
        if _ui:
            _ui.messageBox(f'Failed to create triangular pyramid:\n{traceback.format_exc()}')


def add_fillet_to_selection(radius: float):
    """現在選択されているエッジに指定された半径のフィレットを適用する"""
    try:
        selections = _ui.activeSelections
        if selections.count == 0:
            _ui.messageBox("フィレットを適用するエッジが選択されていません。")
            return

        edges_to_fillet = adsk.core.ObjectCollection.create()
        for i in range(selections.count):
            selection = selections.item(i)
            entity = selection.entity
            if entity.objectType == adsk.fusion.BRepEdge.classType():
                edges_to_fillet.add(entity)

        if edges_to_fillet.count == 0:
            _ui.messageBox("選択されたオブジェクトにエッジが見つかりませんでした。")
            return

        root = _app.activeProduct.rootComponent
        fillets = root.features.filletFeatures
        fillet_input = fillets.createInput()
        
        fillet_radius = adsk.core.ValueInput.createByReal(radius)
        fillet_input.addConstantRadiusEdgeSet(edges_to_fillet, fillet_radius, True)
        
        fillets.add(fillet_input)
        msg = f"SUCCESS: 選択した {edges_to_fillet.count} 本のエッジに R{radius*10} のフィレットを適用しました。"
        write_response(msg)
        _ui.messageBox(msg)
    except:
        err_msg = f"FAILED: add_fillet - {traceback.format_exc()}"
        write_response(err_msg)
        if _ui:
            _ui.messageBox(f'フィレットの適用に失敗しました:\n{traceback.format_exc()}')


def select_edges_of_body(body_name: str, edge_type: str):
    """指定された名前のボディを検索し、そのエッジを選択状態にする"""
    try:
        root = _app.activeProduct.rootComponent
        target_body = None
        for body in root.bRepBodies:
            if body.name == body_name:
                target_body = body
                break
        
        if not target_body:
            _ui.messageBox(f"名前が '{body_name}' のボディが見つかりませんでした。")
            return

        _ui.activeSelections.clear()

        selected_count = 0
        for edge in target_body.edges:
            if edge_type == 'all':
                _ui.activeSelections.add(edge)
                selected_count += 1
            elif edge_type == 'circular' and edge.geometry.curveType == adsk.core.Curve3DTypes.Circle3DCurveType:
                _ui.activeSelections.add(edge)
                selected_count += 1
        
        if selected_count > 0:
            msg = f"SUCCESS: ボディ '{body_name}' の {edge_type} エッジを {selected_count} 本選択しました。"
            write_response(msg)
            _ui.messageBox(msg)
        else:
            msg = f"WARNING: ボディ '{body_name}' に '{edge_type}' の条件に合うエッジが見つかりませんでした。"
            write_response(msg)
            _ui.messageBox(msg)

    except:
        err_msg = f"FAILED: select_edges - {traceback.format_exc()}"
        write_response(err_msg)
        if _ui:
            _ui.messageBox(f'エッジの選択に失敗しました:\n{traceback.format_exc()}')


def perform_combine_on_selection(operation: str):
    """現在選択されている2つのボディに対してブール演算（結合、切り取り、交差）を実行する"""
    try:
        selections = _ui.activeSelections
        if selections.count != 2:
            _ui.messageBox("操作を実行するには、ボディを2つだけ選択してください。\n（ターゲットを1つ目、ツールを2つ目に選択）")
            return

        body1 = selections.item(0).entity
        body2 = selections.item(1).entity
        if not (body1.objectType == adsk.fusion.BRepBody.classType() and body2.objectType == adsk.fusion.BRepBody.classType()):
            _ui.messageBox("選択されたものがボディではありません。2つのボディを選択してください。")
            return

        target_body = body1
        tool_body = body2
        
        tool_bodies_collection = adsk.core.ObjectCollection.create()
        tool_bodies_collection.add(tool_body)

        root = _app.activeProduct.rootComponent
        combine_features = root.features.combineFeatures
        combine_input = combine_features.createInput(target_body, tool_bodies_collection)

        op_map = {
            'join': adsk.fusion.FeatureOperations.JoinFeatureOperation,
            'cut': adsk.fusion.FeatureOperations.CutFeatureOperation,
            'intersect': adsk.fusion.FeatureOperations.IntersectFeatureOperation
        }
        
        op_str = operation.lower()
        if op_str not in op_map:
            _ui.messageBox(f"無効な操作です: '{operation}'。'join', 'cut', 'intersect'のいずれかを指定してください。")
            return
            
        combine_input.operation = op_map[op_str]
        
        combine_features.add(combine_input)
        msg = f"SUCCESS: '{target_body.name}' と '{tool_body.name}' の {op_str} 操作が完了しました。"
        write_response(msg)
        _ui.messageBox(msg)

    except:
        err_msg = f"FAILED: combine_selection - {traceback.format_exc()}"
        write_response(err_msg)
        if _ui:
            _ui.messageBox(f'結合/切り取り操作に失敗しました:\n{traceback.format_exc()}')


def select_two_bodies_by_name(body_name1: str, body_name2: str):
    """指定された2つの名前のボディを検索し、選択状態にする"""
    try:
        root = _app.activeProduct.rootComponent
        body1 = None
        body2 = None
        for body in root.bRepBodies:
            if body.name == body_name1:
                body1 = body
            elif body.name == body_name2:
                body2 = body

        if not body1:
            _ui.messageBox(f"ボディ '{body_name1}' が見つかりませんでした。")
            return
        if not body2:
            _ui.messageBox(f"ボディ '{body_name2}' が見つかりませんでした。")
            return

        _ui.activeSelections.clear()
        _ui.activeSelections.add(body1)
        _ui.activeSelections.add(body2)

        msg = f"SUCCESS: ボディ '{body_name1}' と '{body_name2}' を選択しました。"
        write_response(msg)
        _ui.messageBox(msg)
    except:
        err_msg = f"FAILED: select_bodies - {traceback.format_exc()}"
        write_response(err_msg)
        if _ui:
            _ui.messageBox(f'ボディの選択に失敗しました:\n{traceback.format_exc()}')


def perform_combine_by_name(target_body_name: str, tool_body_name: str, operation: str):
    """指定された2つの名前のボディに対してブール演算（結合、切り取り、交差）を実行する"""
    try:
        root = _app.activeProduct.rootComponent
        
        target_body = None
        tool_body = None
        for body in root.bRepBodies:
            if body.name == target_body_name:
                target_body = body
            elif body.name == tool_body_name:
                tool_body = body
        
        if not target_body:
            _ui.messageBox(f"ターゲットボディ '{target_body_name}' が見つかりませんでした。")
            return
        if not tool_body:
            _ui.messageBox(f"ツールボディ '{tool_body_name}' が見つかりませんでした。")
            return

        tool_bodies_collection = adsk.core.ObjectCollection.create()
        tool_bodies_collection.add(tool_body)

        combine_features = root.features.combineFeatures
        combine_input = combine_features.createInput(target_body, tool_bodies_collection)

        op_map = {
            'join': adsk.fusion.FeatureOperations.JoinFeatureOperation,
            'cut': adsk.fusion.FeatureOperations.CutFeatureOperation,
            'intersect': adsk.fusion.FeatureOperations.IntersectFeatureOperation
        }
        
        op_str = operation.lower()
        if op_str not in op_map:
            _ui.messageBox(f"無効な操作です: '{op_str}'。'join', 'cut', 'intersect'のいずれかを指定してください。")
            return
            
        combine_input.operation = op_map[op_str]
        
        combine_features.add(combine_input)
        msg = f"SUCCESS: '{target_body_name}' をターゲットに '{tool_body_name}' を使って {op_str} 操作が完了しました。"
        write_response(msg)
        _ui.messageBox(msg)

    except:
        err_msg = f"FAILED: combine_by_name - {traceback.format_exc()}"
        write_response(err_msg)
        if _ui:
            _ui.messageBox(f'結合/切り取り操作に失敗しました:\n{traceback.format_exc()}')


def move_selection(x_dist: float, y_dist: float, z_dist: float):
    """現在選択されているすべてのボディを、指定された距離だけ移動させる"""
    try:
        selections = _ui.activeSelections
        if selections.count == 0:
            _ui.messageBox("移動させるボディが選択されていません。")
            return

        bodies_to_move = adsk.core.ObjectCollection.create()
        for selection in selections:
            if selection.entity.objectType == adsk.fusion.BRepBody.classType():
                bodies_to_move.add(selection.entity)
        
        if bodies_to_move.count == 0:
            _ui.messageBox("移動対象としてボディが選択されていません。")
            return

        vector = adsk.core.Vector3D.create(x_dist, y_dist, z_dist)
        transform = adsk.core.Matrix3D.create()
        transform.translation = vector

        root = _app.activeProduct.rootComponent
        move_features = root.features.moveFeatures
        
        move_input = move_features.createInput(bodies_to_move, transform)
        move_features.add(move_input)

        msg = f"SUCCESS: {bodies_to_move.count}個のボディを (X:{x_dist*10}, Y:{y_dist*10}, Z:{z_dist*10}) mm 移動しました。"
        write_response(msg)
        _ui.messageBox(msg)

    except:
        err_msg = f"FAILED: move_selection - {traceback.format_exc()}"
        write_response(err_msg)
        if _ui:
            _ui.messageBox(f'ボディの移動に失敗しました:\n{traceback.format_exc()}')


def select_one_body_by_name(body_name: str):
    """指定された名前のボディを1つだけ検索し、選択状態にする"""
    try:
        root = _app.activeProduct.rootComponent
        target_body = None
        for body in root.bRepBodies:
            if body.name == body_name:
                target_body = body
                break
        
        if not target_body:
            _ui.messageBox(f"名前が '{body_name}' のボディが見つかりませんでした。")
            return

        _ui.activeSelections.clear()
        _ui.activeSelections.add(target_body)
        msg = f"SUCCESS: ボディ '{body_name}' を選択しました。"
        write_response(msg)
        _ui.messageBox(msg)
    except:
        err_msg = f"FAILED: select_body - {traceback.format_exc()}"
        write_response(err_msg)
        if _ui:
            _ui.messageBox(f'ボディの選択に失敗しました:\n{traceback.format_exc()}')


def perform_undo():
    """デザインの履歴を1つ元に戻す"""
    try:
        cmd_def = _ui.commandDefinitions.itemById('UndoCommand')
        if cmd_def:
            cmd_def.execute()
            msg = "SUCCESS: Undo command executed successfully."
            write_response(msg)
            _ui.palettes.itemById('TextCommands').writeText(msg)
        else:
            msg = "FAILED: Undo command definition not found."
            write_response(msg)
            _ui.messageBox(msg)
    except:
        err_msg = f"FAILED: undo - {traceback.format_exc()}"
        write_response(err_msg)
        if _ui:
            _ui.messageBox(f'Undo operation failed:\n{traceback.format_exc()}')


def perform_redo():
    """アンドゥで元に戻した操作を1つやり直す"""
    try:
        cmd_def = _ui.commandDefinitions.itemById('RedoCommand')
        if cmd_def:
            cmd_def.execute()
            msg = "SUCCESS: Redo command executed successfully."
            write_response(msg)
            _ui.palettes.itemById('TextCommands').writeText(msg)
        else:
            msg = "FAILED: Redo command definition not found."
            write_response(msg)
            _ui.messageBox(msg)
    except:
        err_msg = f"FAILED: redo - {traceback.format_exc()}"
        write_response(err_msg)
        if _ui:
            _ui.messageBox(f'Redo operation failed:\n{traceback.format_exc()}')

# ★ 新機能 ★ 選択された1つのボディを回転させる関数
def rotate_selection(axis_str: str, angle_degrees: float, cx: float, cy: float, cz: float):
    """現在選択されている1つのボディを、指定された軸、角度、中心点で回転させる"""
    try:
        selections = _ui.activeSelections
        if selections.count != 1:
            _ui.messageBox("回転させるボディを1つだけ選択してください。")
            return
        
        target_body = selections.item(0).entity
        if target_body.objectType != adsk.fusion.BRepBody.classType():
            _ui.messageBox("選択されたものがボディではありません。")
            return
        
        bodies_to_move = adsk.core.ObjectCollection.create()
        bodies_to_move.add(target_body)
        
        axis_str = axis_str.lower()
        if axis_str == 'x':
            axis_vector = adsk.core.Vector3D.create(1, 0, 0)
        elif axis_str == 'y':
            axis_vector = adsk.core.Vector3D.create(0, 1, 0)
        elif axis_str == 'z':
            axis_vector = adsk.core.Vector3D.create(0, 0, 1)
        else:
            _ui.messageBox(f"無効な回転軸です: '{axis_str}'。'x', 'y', 'z'のいずれかを指定してください。")
            return
        
        center_point = adsk.core.Point3D.create(cx, cy, cz)
        
        angle_rad = math.radians(angle_degrees)
        
        transform = adsk.core.Matrix3D.create()
        transform.setToRotation(angle_rad, axis_vector, center_point)
        
        root = _app.activeProduct.rootComponent
        move_features = root.features.moveFeatures
        move_input = move_features.createInput(bodies_to_move, transform)
        move_features.add(move_input)
        
        msg = f"SUCCESS: ボディ '{target_body.name}' を {axis_str.upper()}軸周りに {angle_degrees}度 回転させました。"
        write_response(msg)
        _ui.messageBox(msg)
        
    except:
        err_msg = f"FAILED: rotate_selection - {traceback.format_exc()}"
        write_response(err_msg)
        if _ui:
            _ui.messageBox(f'ボディの回転に失敗しました:\n{traceback.format_exc()}')

# --- ファイル監視とイベントハンドラ ---

class CommandReceivedEventHandler(adsk.core.CustomEventHandler):
    """カスタムイベントを受け取ってコマンドを処理するハンドラ"""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            command = args.additionalInfo
            _ui.palettes.itemById('TextCommands').writeText(f"Executing: {command}")

            parts = command.split()
            command_name = parts[0]

            if command_name == 'create_cube':
                try:
                    size = float(parts[1]) / 10.0
                    body_name = parts[2] if (len(parts) > 2 and parts[2].lower() not in ['xy','yz','xz','none','null']) else None
                    plane_str = parts[3] if len(parts) > 3 else 'xy'
                    cx = float(parts[4]) / 10.0 if len(parts) > 4 else 0
                    cy = float(parts[5]) / 10.0 if len(parts) > 5 else 0
                    cz = float(parts[6]) / 10.0 if len(parts) > 6 else 0
                    create_cube(size, body_name, plane_str, cx, cy, cz)
                except (ValueError, IndexError):
                    _ui.messageBox(f"Invalid format. Usage: create_cube <size> [name] [plane] [cx] [cy] [cz]")
            
            elif command_name == 'create_cylinder':
                try:
                    radius = float(parts[1]) / 10.0
                    height = float(parts[2]) / 10.0
                    body_name = parts[3] if (len(parts) > 3 and parts[3].lower() not in ['xy','yz','xz','none','null']) else None
                    plane_str = parts[4] if len(parts) > 4 else 'xy'
                    cx = float(parts[5]) / 10.0 if len(parts) > 5 else 0
                    cy = float(parts[6]) / 10.0 if len(parts) > 6 else 0
                    cz = float(parts[7]) / 10.0 if len(parts) > 7 else 0
                    create_cylinder(radius, height, body_name, plane_str, cx, cy, cz)
                except (ValueError, IndexError):
                     _ui.messageBox(f"Invalid format. Usage: create_cylinder <radius> <height> [name] [plane] [cx] [cy] [cz]")
            
            elif command_name == 'create_box':
                try:
                    width = float(parts[1]) / 10.0
                    depth = float(parts[2]) / 10.0
                    height = float(parts[3]) / 10.0
                    body_name = parts[4] if (len(parts) > 4 and parts[4].lower() not in ['xy','yz','xz','none','null']) else None
                    plane_str = parts[5] if len(parts) > 5 else 'xy'
                    cx = float(parts[6]) / 10.0 if len(parts) > 6 else 0
                    cy = float(parts[7]) / 10.0 if len(parts) > 7 else 0
                    cz = float(parts[8]) / 10.0 if len(parts) > 8 else 0
                    create_box(width, depth, height, body_name, plane_str, cx, cy, cz)
                except(ValueError, IndexError):
                    _ui.messageBox(f"Invalid format. Usage: create_box <w> <d> <h> [name] [plane] [cx] [cy] [cz]")

            elif command_name == 'create_sphere':
                try:
                    radius = float(parts[1]) / 10.0
                    body_name = parts[2] if (len(parts) > 2 and parts[2].lower() not in ['xy','yz','xz','none','null']) else None
                    plane_str = parts[3] if len(parts) > 3 else 'xy'
                    cx = float(parts[4]) / 10.0 if len(parts) > 4 else 0
                    cy = float(parts[5]) / 10.0 if len(parts) > 5 else 0
                    cz = float(parts[6]) / 10.0 if len(parts) > 6 else 0
                    create_sphere(radius, body_name, plane_str, cx, cy, cz)
                except(ValueError, IndexError):
                    _ui.messageBox(f"Invalid format. Usage: create_sphere <radius> [name] [plane] [cx] [cy] [cz]")

            elif command_name == 'create_cone':
                try:
                    radius = float(parts[1]) / 10.0
                    height = float(parts[2]) / 10.0
                    body_name = parts[3] if (len(parts) > 3 and parts[3].lower() not in ['xy','yz','xz','none','null']) else None
                    plane_str = parts[4] if len(parts) > 4 else 'xy'
                    cx = float(parts[5]) / 10.0 if len(parts) > 5 else 0
                    cy = float(parts[6]) / 10.0 if len(parts) > 6 else 0
                    cz = float(parts[7]) / 10.0 if len(parts) > 7 else 0
                    create_cone(radius, height, body_name, plane_str, cx, cy, cz)
                except(ValueError, IndexError):
                    _ui.messageBox(f"Invalid format. Usage: create_cone <radius> <height> [name] [plane] [cx] [cy] [cz]")

            elif command_name == 'create_sq_pyramid':
                try:
                    side = float(parts[1]) / 10.0
                    height = float(parts[2]) / 10.0
                    body_name = parts[3] if (len(parts) > 3 and parts[3].lower() not in ['xy','yz','xz','none','null']) else None
                    plane_str = parts[4] if len(parts) > 4 else 'xy'
                    cx = float(parts[5]) / 10.0 if len(parts) > 5 else 0
                    cy = float(parts[6]) / 10.0 if len(parts) > 6 else 0
                    cz = float(parts[7]) / 10.0 if len(parts) > 7 else 0
                    create_sq_pyramid(side, height, body_name, plane_str, cx, cy, cz)
                except(ValueError, IndexError):
                    _ui.messageBox(f"Invalid format. Usage: create_sq_pyramid <side> <h> [name] [plane] [cx] [cy] [cz]")
            
            elif command_name == 'create_tri_pyramid':
                try:
                    side = float(parts[1]) / 10.0
                    height = float(parts[2]) / 10.0
                    body_name = parts[3] if (len(parts) > 3 and parts[3].lower() not in ['xy','yz','xz','none','null']) else None
                    plane_str = parts[4] if len(parts) > 4 else 'xy'
                    cx = float(parts[5]) / 10.0 if len(parts) > 5 else 0
                    cy = float(parts[6]) / 10.0 if len(parts) > 6 else 0
                    cz = float(parts[7]) / 10.0 if len(parts) > 7 else 0
                    create_tri_pyramid(side, height, body_name, plane_str, cx, cy, cz)
                except(ValueError, IndexError):
                    _ui.messageBox(f"Invalid format. Usage: create_tri_pyramid <side> <h> [name] [plane] [cx] [cy] [cz]")
            
            elif command_name == 'add_fillet':
                try:
                    radius = float(parts[1]) / 10.0
                    add_fillet_to_selection(radius)
                except (ValueError, IndexError):
                    _ui.messageBox(f"Invalid format. Expected: add_fillet <radius_mm>")

            elif command_name == 'select_edges':
                try:
                    body_name = parts[1]
                    edge_type = parts[2]
                    select_edges_of_body(body_name, edge_type)
                except (ValueError, IndexError):
                    _ui.messageBox(f"Invalid format. Expected: select_edges <body_name> <all|circular>")
            
            elif command_name == 'combine_selection':
                try:
                    operation = parts[1]
                    perform_combine_on_selection(operation)
                except (ValueError, IndexError):
                    _ui.messageBox(f"Invalid format. Expected: combine_selection <join|cut|intersect>")

            elif command_name == 'select_bodies':
                try:
                    body_name1 = parts[1]
                    body_name2 = parts[2]
                    select_two_bodies_by_name(body_name1, body_name2)
                except (ValueError, IndexError):
                    _ui.messageBox(f"Invalid format. Expected: select_bodies <body_name1> <body_name2>")
            
            elif command_name == 'combine_by_name':
                try:
                    target_body_name = parts[1]
                    tool_body_name = parts[2]
                    operation = parts[3]
                    perform_combine_by_name(target_body_name, tool_body_name, operation)
                except (ValueError, IndexError):
                    _ui.messageBox(f"Invalid format. Expected: combine_by_name <target_body> <tool_body> <join|cut|intersect>")
            
            elif command_name == 'move_selection':
                try:
                    x = float(parts[1]) / 10.0
                    y = float(parts[2]) / 10.0
                    z = float(parts[3]) / 10.0
                    move_selection(x, y, z)
                except(ValueError, IndexError):
                    _ui.messageBox(f"Invalid format. Expected: move_selection <x_dist> <y_dist> <z_dist>")

            elif command_name == 'select_body':
                try:
                    body_name = parts[1]
                    select_one_body_by_name(body_name)
                except (ValueError, IndexError):
                    _ui.messageBox(f"Invalid format. Expected: select_body <body_name>")
            
            elif command_name == 'undo':
                perform_undo()

            elif command_name == 'redo':
                perform_redo()
            
            elif command_name == 'rotate_selection':
                try:
                    axis = parts[1]
                    angle = float(parts[2])
                    cx = float(parts[3]) / 10.0
                    cy = float(parts[4]) / 10.0
                    cz = float(parts[5]) / 10.0
                    rotate_selection(axis, angle, cx, cy, cz)
                except(ValueError, IndexError):
                    _ui.messageBox(f"Invalid format. Expected: rotate_selection <axis> <angle> <cx> <cy> <cz>")

            else:
                _ui.messageBox(f"Unknown command: '{command_name}'")
        except:
            _ui.messageBox(f'An unexpected error occurred in notify handler:\n{traceback.format_exc()}')


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

