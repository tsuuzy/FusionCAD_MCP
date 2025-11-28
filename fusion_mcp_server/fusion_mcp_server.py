"""This file acts as the main module for this script."""

# import traceback
# import adsk.core
# import adsk.fusion
# # import adsk.cam

# # Initialize the global variables for the Application and UserInterface objects.
# app = adsk.core.Application.get()
# ui  = app.userInterface


# def run(_context: str):
#     """This function is called by Fusion when the script is run."""

#     try:
#         # Your code goes here.
#         ui.messageBox(f'"{app.activeDocument.name}" is the active Document.')
#     except:  #pylint:disable=bare-except
#         # Write the error message to the TEXT COMMANDS window.
#         app.log(f'Failed:\n{traceback.format_exc()}')


import traceback
import adsk.core
import adsk.fusion

handlers = []

def create_cube(size):
    app = adsk.core.Application.get()
    ui = app.userInterface
    design = app.activeProduct
    root = design.rootComponent
    sketches = root.sketches
    xyPlane = root.xYConstructionPlane

    sketch = sketches.add(xyPlane)
    sketch.sketchCurves.sketchLines.addTwoPointRectangle(
        adsk.core.Point3D.create(0, 0, 0),
        adsk.core.Point3D.create(size, size, 0)
    )

    prof = sketch.profiles.item(0)
    extrudes = root.features.extrudeFeatures
    extInput = extrudes.createInput(prof, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    distance = adsk.core.ValueInput.createByReal(size)
    extInput.setDistanceExtent(False, distance)
    extrudes.add(extInput)
    ui.messageBox(f" Cube created: {size}mm")

def run(context):
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        ui.messageBox("Fusion MCP Add-in is running.")

        # ここで好きなサイズで立方体を試しに生成
        create_cube(10)

    except Exception as e:
        if ui:
            ui.messageBox(f"Error: {traceback.format_exc()}")

    def stop(context):
        app = adsk.core.Application.get()
        ui = app.userInterface
        ui.messageBox("Fusion MCP Add-in stopped.")
