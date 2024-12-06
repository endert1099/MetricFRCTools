# Assuming you have not changed the general structure of the template no modification is needed in this file.
import adsk.core
from . import commands
from .lib import fusionAddInUtils as futil
from . import config

app = adsk.core.Application.get()
ui = app.userInterface

def run(context):
    try:

        # ******** Add a button into the UI so the user can run the command. ********
        # Get the target workspace the button will be created in.
        workspace = ui.workspaces.itemById(config.WORKSPACE_ID)

        # Get the panel the button will be created in.
        panel = workspace.toolbarPanels.itemById(config.PANEL_ID)
        sketchpanel = workspace.toolbarPanels.itemById(config.SKETCH_CREATE_ID)

        # Create the the FRCTool submenu.
        submenu = panel.controls.addDropDown( "FRCTools", "", config.DROPDOWN_ID )
        submenu = sketchpanel.controls.addDropDown( "FRCTools", "", config.DROPDOWN_ID )

        # This will run the start function in each of your commands as defined in commands/__init__.py
        commands.start()

    except:
        futil.handle_error('run')


def stop(context):
    try:
        # Remove all of the event handlers your app has created
        futil.clear_handlers()

        # This will run the stop function in each of your commands as defined in commands/__init__.py
        commands.stop()

        workspace = ui.workspaces.itemById(config.WORKSPACE_ID)
        panel = workspace.toolbarPanels.itemById(config.PANEL_ID)
        submenu = panel.controls.itemById( config.DROPDOWN_ID )

        # Delete the FRCTools submenu
        if submenu:
            submenu.deleteMe()

        sketchpanel = workspace.toolbarPanels.itemById(config.SKETCH_CREATE_ID)
        submenu = sketchpanel.controls.itemById( config.DROPDOWN_ID )

        # Delete the FRCTools submenu
        if submenu:
            submenu.deleteMe()

    except:
        futil.handle_error('stop')