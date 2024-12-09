import adsk.core
import adsk.fusion
import os
import math
import typing
from ...lib import fusionAddInUtils as futil
from ... import config
app = adsk.core.Application.get()
ui = app.userInterface


# TODO *** Specify the command identity information. ***
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_BoltPatternDialog'
CMD_NAME = 'FRC Bolt Pattern'
CMD_Description = 'Create a bolt pattern for common FRC motors'

# Specify that the command will be promoted to the panel.
IS_PROMOTED = True

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []

# Local list of ui event handlers used to maintain a reference so
# they are not released and garbage collected.
ui_handlers = []

# Bolt Pattern struct
class BoltPattern(typing.NamedTuple) :
    name: str = ""
    centerDia: float = 0.0
    patternDia: float = 0.0
    holeSize: float = 0.0
    numberOfHoles: int = 0
    supression: list[int] = []

# Selection of Bolt Patterns
bolt_patterns: list[BoltPattern] = [
    # Name, center hole radius, pattern radius, hole size, # of holes, supression
    BoltPattern('Kraken X60', 0.75, 2.0, 0.196, 12, [1,1,1,1,1,1,1,1,1,1,1,0]),
    BoltPattern('Kraken X44', 0.75, 1.375, 0.196, 12, [1,1,1,1,1,1,1,1,1,1,1,0]),
    BoltPattern('NEO Vortex', 0.75, 2.0, 0.196, 8, [1,1,1,0,1,1,1,0]),
    BoltPattern('NEO 550', 0.5118, 0.9843, 0.125, 4, []),
]

# Executed when add-in is run.
def start():
    # Create a command Definition.
    cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER)

    # Define an event handler for the command created event. It will be called when the button is clicked.
    futil.add_handler(cmd_def.commandCreated, command_created)

    # ******** Add a button into the UI so the user can run the command. ********
    # Get the target workspace the button will be created in.
    workspace = ui.workspaces.itemById(config.WORKSPACE_ID)

    # Get the panel the button will be created in.
    panel = workspace.toolbarPanels.itemById(config.SKETCH_CREATE_ID)

    # Find the the FRCTools submenu.
    submenu = panel.controls.itemById( config.DROPDOWN_ID )

    # Create the button command control in the UI.
    control = submenu.controls.addCommand(cmd_def)

    # Specify if the command is promoted to the main toolbar. 
    control.isPromoted = IS_PROMOTED

# Executed when add-in is stopped.
def stop():
    global edit_cmd_def

    # Get the various UI elements for this command
    workspace = ui.workspaces.itemById(config.WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(config.SKETCH_CREATE_ID)
    submenu = panel.controls.itemById( config.DROPDOWN_ID )
    command_control = submenu.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)

    # Delete the button command control
    if command_control:
        command_control.isPromoted = False
        command_control.deleteMe()

    # Delete the command definition
    if command_definition:
        command_definition.deleteMe()

    global ui_handlers
    ui_handlers = []

# Function that is called when a user clicks the corresponding button in the UI.
# This defines the contents of the command dialog and connects to the command related events.
def command_created(args: adsk.core.CommandCreatedEventArgs):

    # General logging for debug.
    futil.log(f'{CMD_NAME} command Created Event')

    # https://help.autodesk.com/view/fusion360/ENU/?contextId=CommandInputs
    inputs = args.command.commandInputs

    # Bolt Patterns
    boltPattern = inputs.addDropDownCommandInput('bolt_pattern', 'Bolt Pattern', adsk.core.DropDownStyles.TextListDropDownStyle)
    for bp in bolt_patterns:
        boltPattern.listItems.add( bp.name, True, '')
    boltPattern.listItems.item( 0 ).isSelected = True

    # Create a selection input.
    centerSelection = inputs.addSelectionInput('center_selection', 'Center', 'Select the center of the bolt pattern')
    centerSelection.addSelectionFilter( "SketchPoints" )
    centerSelection.addSelectionFilter( "SketchCircles" )
    centerSelection.setSelectionLimits( 1, 1 )

    # TODO Connect to the events that are needed by this command.
    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
    futil.add_handler(args.command.executePreview, command_preview, local_handlers=local_handlers)
    futil.add_handler(args.command.validateInputs, command_validate_input, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)


# This event handler is called when the user clicks the OK button in the command dialog or 
# is immediately called after the created event not command inputs were created for the dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Execute Event')

 

# This event handler is called when the command needs to compute a new preview in the graphics window.
def command_preview(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Preview Event')


# This event handler is called when the user changes anything in the command dialog
# allowing you to modify values of other inputs based on that change.
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    changed_input = args.input
    inputs = args.inputs

    # General logging for debug.
    futil.log(f'{CMD_NAME} Input Changed Event fired from a change to {changed_input.id}')



# This event handler is called when the user interacts with any of the inputs in the dialog
# which allows you to verify that all of the inputs are valid and enables the OK button.
def command_validate_input(args: adsk.core.ValidateInputsEventArgs):

    futil.log(f'{CMD_NAME} Command Validate Event')

    inputs = args.inputs

# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Destroy Event')

    global local_handlers
    local_handlers = []
