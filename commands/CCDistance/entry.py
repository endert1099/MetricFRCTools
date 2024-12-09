import adsk.core
import adsk.fusion
import os
import math
from ...lib import fusionAddInUtils as futil
from ... import config
app = adsk.core.Application.get()
ui = app.userInterface


# TODO *** Specify the command identity information. ***
CREATE_CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_CCDistanceDialog'
CREATE_CMD_NAME = 'C-C Distance'
CREATE_CMD_Description = 'Determine pitch diameters and C-C distances'

EDIT_CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_CCDistanceEdit'
EDIT_CMD_NAME = 'Edit C-C Distance'
EDIT_CMD_Description = 'Edit existing C-C Distance Object'

DELETE_CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_CCDistanceDelete'
DELETE_CMD_NAME = 'Delete C-C Distance'

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

# Global variable to hold the last selected feature that was part of a ccLine in the UI
last_selected = None
last_CCLine = None
edit_cmd_def = None

motionTypes = ( 
    'Gears 20DP',
    'HTD 5mm Belt',
    'GT2 3mm Belt',
)
motionTypesDefault = motionTypes.index( 'Gears 20DP' )

# Attribute constants
CC_ATTRIBUTE_GROUP = "CCDistance_Group"
CC_LINE_TEETH = "Teeth"
CC_LINE_N1 = "N1"
CC_LINE_N2 = "N2"
CC_LINE_EC = "EC"
CC_LINE_MOTION_TYPE = "MOTION"
CC_LINE_PITCH_CIRCLE1 = "PC1"
CC_LINE_PITCH_CIRCLE2 = "PC2"
CC_LINE_OD_CIRCLE1 = "OD1"
CC_LINE_OD_CIRCLE2 = "OD2"
CC_LINE_TEXT = "TEXT"
CC_LINE_MIDPT = "MIDPT"
# Dimensions
CC_LINE_LENGTH_DIM = "LENGTH_DIM"
CC_LINE_PITCH_CIRCLE1_DIM = "PC1_DIM"
CC_LINE_PITCH_CIRCLE2_DIM = "PC2_DIM"
CC_LINE_OD_CIRCLE1_DIM = "OD1_DIM"
CC_LINE_OD_CIRCLE2_DIM = "OD2_DIM"
CC_LINE_TEXT_HEIGHT_DIM = "TEXT_HEIGHT"

CC_LINE_PARENT_LINE = "CCLine"

class CCLineData :
    N1 = 0
    N2 = 0
    Teeth = 0
    ExtraCenterIN = 0.00
    motion = motionTypesDefault
    ccDistIN = 0.0    # Calculated before EC is added
    PD1 = 0.0
    PD2 = 0.0
    OD1 = 0.0
    OD2 = 0.0

class CCLine :
    data = CCLineData()
    line: adsk.fusion.SketchLine = None
    pitchCircle1: adsk.fusion.SketchCircle = None
    pitchCircle2: adsk.fusion.SketchCircle = None
    ODCircle1: adsk.fusion.SketchCircle = None
    ODCircle2: adsk.fusion.SketchCircle = None
    # Dimensions
    lengthDim: adsk.fusion.SketchLinearDimension = None
    PD1Dim: adsk.fusion.SketchDiameterDimension = None
    PD2Dim: adsk.fusion.SketchDiameterDimension = None
    OD1Dim: adsk.fusion.SketchDiameterDimension = None
    OD2Dim: adsk.fusion.SketchDiameterDimension = None
    textHeight: adsk.fusion.SketchLinearDimension = None
    # Line Label
    textBox: adsk.fusion.SketchText = None
    midPt: adsk.fusion.SketchPoint = None

# Executed when add-in is run.
def start():
    global edit_cmd_def, delete_cmd_def

    # Create a command Definition.
    create_cmd_def = ui.commandDefinitions.addButtonDefinition(CREATE_CMD_ID, CREATE_CMD_NAME, CREATE_CMD_Description, ICON_FOLDER)
    edit_cmd_def = ui.commandDefinitions.addButtonDefinition(EDIT_CMD_ID, EDIT_CMD_NAME, EDIT_CMD_Description, ICON_FOLDER)
    delete_cmd_def = ui.commandDefinitions.addButtonDefinition(DELETE_CMD_ID, DELETE_CMD_NAME, "Delete CCLine", ICON_FOLDER)

    # Define an event handler for the command created event. It will be called when the button is clicked.
    futil.add_handler(create_cmd_def.commandCreated, command_created)
    futil.add_handler(edit_cmd_def.commandCreated, edit_command_created)
    futil.add_handler(delete_cmd_def.commandCreated, delete_command_created)

    # ******** Add a button into the UI so the user can run the command. ********
    # Get the target workspace the button will be created in.
    workspace = ui.workspaces.itemById(config.WORKSPACE_ID)

    # Get the panel the button will be created in.
    panel = workspace.toolbarPanels.itemById(config.SKETCH_CREATE_ID)

    # Find the the FRCTools submenu.
    submenu = panel.controls.itemById( config.DROPDOWN_ID )

    # Create the button command control in the UI.
    control = submenu.controls.addCommand(create_cmd_def)

    # Specify if the command is promoted to the main toolbar. 
    control.isPromoted = IS_PROMOTED

    # Listen for activeSelectionChanged events
    futil.add_handler( ui.commandStarting, ui_command_starting, local_handlers=ui_handlers )
    futil.add_handler( ui.commandTerminated, ui_command_terminated, local_handlers=ui_handlers )
    futil.add_handler( ui.activeSelectionChanged, ui_selection_changed, local_handlers=ui_handlers )
    futil.add_handler( ui.markingMenuDisplaying, ui_marking_menu, local_handlers=ui_handlers )

# Executed when add-in is stopped.
def stop():
    global edit_cmd_def

    # Get the various UI elements for this command
    workspace = ui.workspaces.itemById(config.WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(config.SKETCH_CREATE_ID)
    submenu = panel.controls.itemById( config.DROPDOWN_ID )
    command_control = submenu.controls.itemById(CREATE_CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CREATE_CMD_ID)
    edit_cmd_def = ui.commandDefinitions.itemById(EDIT_CMD_ID)
    delete_cmd_def = ui.commandDefinitions.itemById(DELETE_CMD_ID)

    # Delete the button command control
    if command_control:
        command_control.isPromoted = False
        command_control.deleteMe()

    # Delete the command definition
    if command_definition:
        command_definition.deleteMe()

    # Delete the edit command definition
    if edit_cmd_def:
        edit_cmd_def.deleteMe()

    # Delete the delete command definition
    if delete_cmd_def:
        delete_cmd_def.deleteMe()

    global ui_handlers
    ui_handlers = []

# Function that is called when a active selection is changed in the UI.
def ui_command_starting(args: adsk.core.ApplicationCommandEventArgs):

    global last_selected
    # futil.log(f' Command Starting={args.commandDefinition.name}')

    # Kill the editing of the dimensions within the CCLine
    if args.commandDefinition.name == 'Edit Sketch Dimension' :
        if last_selected :
            args.isCanceled = True

# Function that is called when a active selection is changed in the UI.
def ui_command_terminated(args: adsk.core.ApplicationCommandEventArgs):

    global last_selected, last_CCLine

    # futil.log(f' Command Terminated={args.commandDefinition.name}')
    if args.commandDefinition.name == 'Delete' :
        if last_selected:
            # If the last selected item was a CCLine and now a Delete 
            # command has just finished. Then we check if the CCLine entity
            # was deleted and delete the entire CCLine if it was.
            design = adsk.fusion.Design.cast(app.activeProduct)
            ccLineList = design.findEntityByToken( last_selected )
            # futil.log( f'   Token count = {len(ccLineList)}')
            if len(ccLineList) == 0:
                # futil.log( f'   ======= DELETING the ENTIRE ccLine object.')
                delete_cmd_def = ui.commandDefinitions.itemById( DELETE_CMD_ID )
                delete_cmd_def.execute()

# Function that is called when a active selection is changed in the UI.
def ui_selection_changed(args: adsk.core.ActiveSelectionEventArgs):

    global last_selected, last_CCLine

    # futil.log(f' Selection Changed Command')

    if len( args.currentSelection ) > 0:
        last_selected = None
    
        select = args.currentSelection[0].entity
        
        last_CCLine = getCCLineFromEntity( select )
        if last_CCLine:
            # futil.log( f' ===== New Selection IS A ccLine =====')
            last_selected = args.currentSelection[0].entity.entityToken

# Function that is called when the marking menu is going to be displayed.
def ui_marking_menu(args: adsk.core.MarkingMenuEventArgs):

    global edit_cmd_def, last_selected, last_CCLine

    controls = args.linearMarkingMenu.controls

    # Gather the menu items we need to control
    editMTextCmd = controls.itemById( 'EditMTextCmd' )
    explodeTextCmd = controls.itemById( 'ExplodeTextCmd' )
    toggleDrivenDimCmd = controls.itemById( 'ToggleDrivenDimCmd' )
    toggleRadialDimCmd = controls.itemById( 'ToggleRadialDimCmd' )

    editCCLineMenuItem = controls.itemById( EDIT_CMD_ID )
    if not editCCLineMenuItem:
        # Find the separator before the "Edit Text" command and add our commands after it
        i = editMTextCmd.index - 1
        while i > 0:
            control = controls.item( i )
            if control.objectType == adsk.core.SeparatorControl.classType():
                control = controls.item( i + 1 )
                break
            i -= 1
        editCCLineMenuItem = controls.addCommand( edit_cmd_def, control.id, True )
        editCCLineSep = controls.addSeparator( "EditCCLineSeparator", editCCLineMenuItem.id, False )

    editCCLineSep = controls.itemById( "EditCCLineSeparator" )

    if len(args.selectedEntities) > 0 :
        ccLine = getCCLineFromEntity( args.selectedEntities[0] )
        # for control in controls:
        #     if control.objectType == adsk.core.SeparatorControl.classType():
        #         sep: adsk.core.SeparatorControl = control
        #         # futil.log(f'Separator = {sep.id} at index {sep.index}')
        #     elif control.isVisible :
        #         futil.log(f'marking menu = {control.id} ,{control.isVisible}')
        if ccLine:
            editCCLineMenuItem.isVisible = True
            editCCLineSep.isVisible = True
            editMTextCmd.isVisible = False
            explodeTextCmd.isVisible = False
            toggleDrivenDimCmd.isVisible = False
            toggleRadialDimCmd.isVisible = False
            return
        
    editCCLineMenuItem.isVisible = False
    editCCLineSep.isVisible = False

# 
def edit_command_created(args: adsk.core.CommandCreatedEventArgs):
    global last_CCLine

    # futil.log(f'{args.command.parentCommandDefinition.name} edit_command_created()')

    # https://help.autodesk.com/view/fusion360/ENU/?contextId=CommandInputs
    inputs = args.command.commandInputs

    # Motion Component Type
    motionType = inputs.addDropDownCommandInput('motion_type', 'Motion Type', adsk.core.DropDownStyles.TextListDropDownStyle)
    for mtype in motionTypes:
        motionType.listItems.add( mtype, True, '')
    motionType.listItems.item( motionTypesDefault ).isSelected = True

    # Create a integer spinners for cog1 and cog2.
    cog1Teeth = inputs.addIntegerSpinnerCommandInput('cog1_teeth', 'Cog #1 Teeth', 8, 100, 1, 36)
    cog2Teeth = inputs.addIntegerSpinnerCommandInput('cog2_teeth', 'Cog #2 Teeth', 8, 100, 1, 24)

    inputs.addBoolValueInput( "swap_cogs", "Swap Cogs", True )

    beltTeeth = inputs.addIntegerSpinnerCommandInput( "belt_teeth", "Belt Teeth", 40, 400, 1, 70 )
    beltTeeth.isVisible = False

    # Create a value input field and set the default using 1 unit of the default length unit.
    defaultLengthUnits = "in"
    default_value = adsk.core.ValueInput.createByString('0.003')
    extraCenter = inputs.addValueInput('extra_center', 'Extra Center', defaultLengthUnits, default_value)

    # Fill the inputs with the ccLine info
    lineData = last_CCLine.data
    cog1Teeth.value = lineData.N1
    cog2Teeth.value = lineData.N2
    if lineData.motion != 0 :
        beltTeeth.value = lineData.Teeth
        beltTeeth.isVisible = True
    extraCenter.value = lineData.ExtraCenterIN * 2.54
    motionType.listItems.item( lineData.motion ).isSelected = True

    # Connect to the events that are needed by this command.
    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
    futil.add_handler(args.command.executePreview, command_preview, local_handlers=local_handlers)
    futil.add_handler(args.command.validateInputs, command_validate_input, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)

def delete_command_created(args: adsk.core.CommandCreatedEventArgs):

    # futil.log(f'{args.command.parentCommandDefinition.name} Delete Command Created Event')

    futil.add_handler(args.command.execute, delete_command_execute, local_handlers=local_handlers)

def delete_command_execute(args: adsk.core.CommandEventArgs):
    global last_CCLine

    # futil.log(f'{args.command.parentCommandDefinition.name} Delete Command Executed Event')
    deleteCCLine( last_CCLine )

# Function that is called when a user clicks the corresponding button in the UI.
# This defines the contents of the command dialog and connects to the command related events.
def command_created(args: adsk.core.CommandCreatedEventArgs):

    # General logging for debug.
    # futil.log(f'{args.command.parentCommandDefinition.name} Command Created Event')

    # https://help.autodesk.com/view/fusion360/ENU/?contextId=CommandInputs
    inputs = args.command.commandInputs

    # Motion Component Type
    motionType = inputs.addDropDownCommandInput('motion_type', 'Motion Type', adsk.core.DropDownStyles.TextListDropDownStyle)
    for mtype in motionTypes:
        motionType.listItems.add( mtype, True, '')
    motionType.listItems.item( motionTypesDefault ).isSelected = True

    # Create a selection input.
    curveSelection = inputs.addSelectionInput('curve_selection', 'Selection', 'Select nothing, a circle, a line, or two starting circles')
    curveSelection.addSelectionFilter( "SketchCurves" )
    curveSelection.setSelectionLimits( 1, 2 )

    inputs.addBoolValueInput( "require_selection", "Require Selection", True, "", True )

    # Create a integer spinners for cog1 and cog2.
    inputs.addIntegerSpinnerCommandInput('cog1_teeth', 'Cog #1 Teeth', 8, 100, 1, 36)
    inputs.addIntegerSpinnerCommandInput('cog2_teeth', 'Cog #2 Teeth', 8, 100, 1, 24)

    inputs.addBoolValueInput( "swap_cogs", "Swap Cogs", True )

    beltTeeth = inputs.addIntegerSpinnerCommandInput( "belt_teeth", "Belt Teeth", 40, 400, 1, 70 )
    beltTeeth.isVisible = False

    # Create a value input field and set the default using 1 unit of the default length unit.
    defaultLengthUnits = "in"
    default_value = adsk.core.ValueInput.createByString('0.003')
    inputs.addValueInput('extra_center', 'Extra Center', defaultLengthUnits, default_value)

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
    # futil.log(f'{args.command.parentCommandDefinition.name} Command Execute Event')

    ccLine = CCLine()

    # Get a reference to your command's inputs.
    inputs = args.command.commandInputs
    motionType: adsk.core.DropDownCommandInput = inputs.itemById('motion_type' )
    curveSelection: adsk.core.SelectionCommandInput = inputs.itemById('curve_selection')
    cog1TeethInp: adsk.core.IntegerSpinnerCommandInput = inputs.itemById('cog1_teeth')
    cog2TeethInp: adsk.core.IntegerSpinnerCommandInput = inputs.itemById('cog2_teeth')
    swapCogs = inputs.itemById( "swap_cogs" ).value
    beltTeethInp: adsk.core.IntegerSpinnerCommandInput = inputs.itemById( "belt_teeth" )
    extraCenterInp: adsk.core.ValueInput = inputs.itemById('extra_center')

    startSketchPt = None
    endSketchPt = None

    if not curveSelection:
        ccLine = last_CCLine
    elif curveSelection.selectionCount == 1 and \
       curveSelection.selection(0).entity.objectType == adsk.fusion.SketchCircle.classType() :
        startSketchPt = curveSelection.selection(0).entity.centerSketchPoint
    elif curveSelection.selectionCount == 1 and \
         curveSelection.selection(0).entity.objectType == adsk.fusion.SketchLine.classType() :
        ccLine.line = curveSelection.selection(0).entity
    elif curveSelection.selectionCount == 2 and \
         curveSelection.selection(0).entity.objectType == adsk.fusion.SketchCircle.classType() :
        startSketchPt = curveSelection.selection(0).entity.centerSketchPoint
        endSketchPt = curveSelection.selection(1).entity.centerSketchPoint

    if ccLine.line == None:
        ccLine.line = createCCLine( startSketchPt, endSketchPt )
    elif isCCLine( ccLine.line ):
        ccLine = getCCLineFromEntity( ccLine.line )

    ccLine.data.ExtraCenterIN = extraCenterInp.value / 2.54
    ccLine.data.Teeth = int(beltTeethInp.value)
    ccLine.data.N1 = int(cog1TeethInp.value)
    ccLine.data.N2 = int(cog2TeethInp.value)
    ccLine.data.motion = motionType.selectedItem.index

    if swapCogs :
        ccLine.data.N2 = int(cog1TeethInp.value)
        ccLine.data.N1 = int(cog2TeethInp.value)

    preview = False
    if args.firingEvent.name == "OnExecutePreview" :
        preview = True

    if not isCCLine( ccLine.line ):
        calcCCLineData( ccLine.data )
        dimAndLabelCCLine( ccLine )
        createEndCircles( ccLine )
    else:
        calcCCLineData( ccLine.data )
        modifyCCLine( ccLine )

    if not preview :
        setCCLineAttributes( ccLine )


# This event handler is called when the command needs to compute a new preview in the graphics window.
def command_preview(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    # futil.log(f'{args.command.parentCommandDefinition.name} Command Preview Event')

    command_execute( args )

# This event handler is called when the user changes anything in the command dialog
# allowing you to modify values of other inputs based on that change.
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    changed_input = args.input
    inputs = args.inputs

    # General logging for debug.
    futil.log(f'{args.firingEvent.name} Input Changed Event fired from a change to {changed_input.id}')

    motionType: adsk.core.DropDownCommandInput = inputs.itemById('motion_type')
    curveSelection: adsk.core.SelectionCommandInput = inputs.itemById('curve_selection')
    cog1Teeth: adsk.core.IntegerSpinnerCommandInput = inputs.itemById('cog1_teeth')
    cog2Teeth: adsk.core.IntegerSpinnerCommandInput = inputs.itemById('cog2_teeth')
    beltTeeth: adsk.core.IntegerSpinnerCommandInput = inputs.itemById( "belt_teeth" )
    extraCenter: adsk.core.ValueInput = inputs.itemById('extra_center')
    swapCogsInp = inputs.itemById( "swap_cogs" )
    requireSelectionInp = inputs.itemById( "require_selection" )

    if changed_input.id == 'motion_type':
        if motionType.selectedItem.index == 0:
            extraCenter.value = 0.003 * 2.54
        else:
            extraCenter.value = 0

    if changed_input.id == 'require_selection':
        if requireSelectionInp.value:
            curveSelection.isVisible = True
            curveSelection.setSelectionLimits( 1, 2 )
        else:
            curveSelection.isVisible = False
            curveSelection.setSelectionLimits( 0, 2 )
            curveSelection.clearSelection()

    if changed_input.id == 'curve_selection':
        if curveSelection.selectionCount == 2:
            # We have selected two entitites
            if curveSelection.selection(0).entity.objectType == adsk.fusion.SketchLine.classType() or\
            curveSelection.selection(1).entity.objectType == adsk.fusion.SketchLine.classType() :
                # If either the first entity selected was a line or the newly selected entity
                # is a line the only keep the newly selected item.  Don't allow a line with something else.
                newSel = curveSelection.selection(1).entity
                curveSelection.clearSelection()
                curveSelection.addSelection( newSel )

        # Check if we have a previously configured CCLine selected or one of its children entities
        ccLine = None
        if curveSelection.selectionCount == 1:
            ccLine = getParentLine( curveSelection.selection(0).entity )
            
        if ccLine and isCCLine( ccLine ):
            curveSelection.clearSelection()
            curveSelection.addSelection( ccLine )

            swapCogsInp.value = False
            # futil.log(f'    ==========  Selected an existing CCLine.')
            lineData = getLineData( ccLine )
            cog1Teeth.value = lineData.N1
            cog2Teeth.value = lineData.N2
            if lineData.motion != 0 :
                beltTeeth.value = lineData.Teeth
            extraCenter.value = lineData.ExtraCenterIN * 2.54
            motionType.listItems.item( lineData.motion ).isSelected = True
            # if motionType.selectedItem.index == 0 :
            #     beltTeeth.isVisible = False
            # else:
            #     beltTeeth.isVisible = True

    if motionType.selectedItem.index == 0 :
        beltTeeth.isVisible = False
    else:
        if beltTeeth.value == 0 :
            beltTeeth.value = 70
        beltTeeth.isVisible = True


# This event handler is called when the user interacts with any of the inputs in the dialog
# which allows you to verify that all of the inputs are valid and enables the OK button.
def command_validate_input(args: adsk.core.ValidateInputsEventArgs):

    # futil.log(f'{args.firingEvent.name} Command Validate Event')

    inputs = args.inputs
    cog1Teeth: adsk.core.IntegerSpinnerCommandInput = inputs.itemById('cog1_teeth')
    cog2Teeth: adsk.core.IntegerSpinnerCommandInput = inputs.itemById('cog2_teeth')

    if not (cog1Teeth.value >= 8 and cog1Teeth.value < 100 and cog2Teeth.value >= 8 and cog1Teeth.value < 100 ):
        args.areInputsValid = False
        return
    
    args.areInputsValid = True        

# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    # futil.log(f'{args.command.parentCommandDefinition.name} Command Destroy Event')

    global local_handlers
    local_handlers = []


def calcCCLineData( ld: CCLineData ):
    if ld.motion == 0:
        # 20DP Gears
        ld.Teeth = 0
        ld.ccDistIN = GearsCCDistanceIN( ld.N1, ld.N2, 20 )
        ld.PD1 = GearsPitchDiameterIN( ld.N1, 20 )
        ld.PD2 = GearsPitchDiameterIN( ld.N2, 20 )
        ld.OD1 = GearsOuterDiameterIN( ld.N1, 20 )
        ld.OD2 = GearsOuterDiameterIN( ld.N2, 20 )
    else :
        if ld.motion == 1:
            # HTD 5mm Belt
            beltPitchMM = 5
        else :
            # HTD 3mm Belt
            beltPitchMM = 3
        ld.ccDistIN = BeltCCDistanceIN( ld.N1, ld.N2, ld.Teeth, beltPitchMM )
        ld.PD1 = BeltPitchDiameterIN( ld.N1, beltPitchMM )
        ld.PD2 = BeltPitchDiameterIN( ld.N2, beltPitchMM )
        ld.OD1 = BeltOuterDiameterIN( ld.N1, beltPitchMM )
        ld.OD2 = BeltOuterDiameterIN( ld.N2, beltPitchMM )


def GearsCCDistanceIN( N1: int, N2: int, dp: int ) -> float:
    pitch_diameter1 = N1 / (1.0 * dp)
    pitch_diameter2 = N2 / (1.0 * dp)

    return (pitch_diameter1 + pitch_diameter2) / 2

def GearsPitchDiameterIN( NT: int, dp: int ) -> float:
    return NT / (1.0 * dp)

def GearsOuterDiameterIN( NT: int, dp: int ) -> float:
    return NT / (1.0 * dp) + 0.1

def BeltCCDistanceIN( N1: int, N2: int, beltTeeth: int, pitchMM: int ) -> float:
    PL = beltTeeth * pitchMM / 25.4 # in inches
    if N1 > N2:
        PD1 = BeltPitchDiameterIN( N1, pitchMM )
        PD2 = BeltPitchDiameterIN( N2, pitchMM )
    else:
        PD1 = BeltPitchDiameterIN( N2, pitchMM )
        PD2 = BeltPitchDiameterIN( N1, pitchMM )

    b = 2 * PL - math.pi * ( PD1 + PD2 )
    fourAC = 8 * (PD1 - PD2)*(PD1 - PD2)

    return ( b + math.sqrt( b*b - fourAC) ) / 8

def BeltPitchDiameterIN( NT: int, pitchMM: int ) -> float:
    return NT * pitchMM / ( 25.4 * math.pi )

def BeltOuterDiameterIN( NT: int, pitchMM: int ) -> float:
        # Approximation of the OD of the flanges on the pulleys
    return BeltPitchDiameterIN(NT, pitchMM) + 0.15

def createCCLine( 
    startpt: adsk.fusion.SketchPoint, 
    endpt: adsk.fusion.SketchPoint ) -> adsk.fusion.SketchLine :

    if startpt == None:
        design = adsk.fusion.Design.cast(app.activeProduct)
        sketch = design.activeEditObject
        startpt = sketch.sketchPoints.add( adsk.core.Point3D.create( 0, 0, 0 ) )
    
    sketch = startpt.parentSketch

    if endpt == None:
        endpt3D = futil.offsetPoint3D( startpt.geometry, 2 * 2.54, 0, 0 )
        endpt = sketch.sketchPoints.add( endpt3D )

    futil.log( f' createCCLine() points = {futil.format_Point3D(startpt.geometry)} -- {futil.format_Point3D(endpt.geometry)}')

    # Create C-C line a midpoint for it and dimension it
    ccLine = sketch.sketchCurves.sketchLines.addByTwoPoints( startpt, endpt )
    ccLine.isConstruction = True

    return ccLine

def dimAndLabelCCLine( ccLine: CCLine ) :

    sketch = ccLine.line.parentSketch
    line = ccLine.line
    ld = ccLine.data

    midPt = futil.midPoint3D( line.startSketchPoint.geometry, line.endSketchPoint.geometry )
    normal = futil.sketchLineNormal( line )
    normal = futil.multVector2D( normal, ld.ccDistIN / 4 )

    # Dimension C-C line
    if abs(normal.y) < 0.001  :
        textPt = futil.offsetPoint3D( midPt, normal.x, normal.y, 0 )
    elif normal.y < 0 :
        textPt = futil.offsetPoint3D( midPt, normal.x, normal.y, 0 )
    else:
        textPt = futil.offsetPoint3D( midPt, -normal.x, -normal.y, 0 )
    
    ccLine.lengthDim = sketch.sketchDimensions.addDistanceDimension( 
        line.startSketchPoint, line.endSketchPoint, 
        adsk.fusion.DimensionOrientations.AlignedDimensionOrientation, textPt )
    ccLine.lengthDim.value = (ld.ccDistIN + ld.ExtraCenterIN) * 2.54

    # Create SketchText and attach it to the C-C Line
    label = createLabelString( ld )
    textHeight = int((ld.ccDistIN + 1)) / 32.0
    # futil.log( f'ccDist = {ld.ccDistIN}in, Text Height = {textHeight}in')
    textHeight = textHeight * 2.54 # in cm
    cornerPt = line.startSketchPoint.geometry
    diagPt =  futil.addPoint3D( cornerPt, adsk.core.Point3D.create( line.length, textHeight, 0 ) )
    textInput = sketch.sketchTexts.createInput2( label, textHeight )
    textInput.setAsMultiLine( cornerPt, diagPt, 
                        adsk.core.HorizontalAlignments.CenterHorizontalAlignment,
                        adsk.core.VerticalAlignments.MiddleVerticalAlignment, 0 )
    ccLine.textBox = sketch.sketchTexts.add( textInput )
    textDef: adsk.fusion.MultiLineTextDefinition = ccLine.textBox.definition
    textBoxLines = textDef.rectangleLines
    textBaseLine = textBoxLines[0]
    TextHeightLine = textBoxLines[1]
    midPt3D = futil.midPoint3D(textBaseLine.startSketchPoint.geometry, textBaseLine.endSketchPoint.geometry )
    ccLine.midPt = sketch.sketchPoints.add( midPt3D )

    textPoint = futil.offsetPoint3D( TextHeightLine.startSketchPoint.geometry, -textHeight/2, textHeight/2, 0 )
    ccLine.textHeight = sketch.sketchDimensions.addDistanceDimension( TextHeightLine.startSketchPoint, TextHeightLine.endSketchPoint,
                                                              adsk.fusion.DimensionOrientations.AlignedDimensionOrientation,
                                                              textPoint  )
    ccLine.textHeight.value = textHeight * 2.0

    sketch.geometricConstraints.addMidPoint( ccLine.midPt, textBaseLine  )
    sketch.geometricConstraints.addMidPoint( ccLine.midPt, line  )
    sketch.geometricConstraints.addParallel( textBaseLine, line  )
    if textBaseLine.startSketchPoint.geometry.distanceTo(line.startSketchPoint.geometry) < \
        textBaseLine.startSketchPoint.geometry.distanceTo(line.endSketchPoint.geometry) :
        sketch.geometricConstraints.addCoincident( textBaseLine.startSketchPoint, line.startSketchPoint )
    else:
        sketch.geometricConstraints.addCoincident( textBaseLine.startSketchPoint, line.endSketchPoint )
     

def createLabelString( ld: CCLineData ) -> str:
    if ld.motion == 0:
        lineLabel = f'Gears 20DP ({ld.N1}T+{ld.N2}T)'
    else :
        if ld.motion == 1:
    #         # HTD 5mm Belt
            lineLabel = f'{ld.Teeth}T HTD 5mm ({ld.N1}Tx{ld.N2}T)'
        else :
    #         # HTD 3mm Belt
            lineLabel = f'{ld.Teeth}T GT2 3mm ({ld.N1}Tx{ld.N2}T)'
    
    if abs(ld.ExtraCenterIN) > 0.0005 :
        lineLabel += f' EC({ld.ExtraCenterIN:.3})'

    return lineLabel

def createEndCircles( ccLine: CCLine ) :
    PDcircleData = createCirclePair( ccLine.line, ccLine.data.PD1, ccLine.data.PD2, 45.0 )
    ccLine.pitchCircle1 = PDcircleData[0][0]
    ccLine.pitchCircle2 = PDcircleData[0][1]
    ccLine.PD1Dim = PDcircleData[1][0]
    ccLine.PD2Dim = PDcircleData[1][1]
    ODcircleData = createCirclePair( ccLine.line, ccLine.data.OD1, ccLine.data.OD2, 135.0 )
    ccLine.ODCircle1 = ODcircleData[0][0]
    ccLine.ODCircle2 = ODcircleData[0][1]
    ccLine.OD1Dim = ODcircleData[1][0]
    ccLine.OD2Dim = ODcircleData[1][1]

def createCirclePair( line: adsk.fusion.SketchLine, 
                      dia1IN: float, dia2IN: float, dimAngleDeg: float ) :

    sketch = line.parentSketch

    normal = futil.sketchLineNormal( line )

    # Create Start point centered circle and dimension it
    startCircle = sketch.sketchCurves.sketchCircles.addByCenterRadius( line.startSketchPoint, dia1IN * 2.54 / 2 )
    startCircle.isConstruction = True

    dimDir = adsk.core.Vector2D.create( dia1IN * 2.54 / 5, 0 )
    rotMatrix = adsk.core.Matrix2D.create()
    rotMatrix.setToRotation( dimAngleDeg * math.pi / 180, adsk.core.Point2D.create() )
    dimDir.transformBy( rotMatrix )
    textPoint = futil.offsetPoint3D( startCircle.centerSketchPoint.geometry, dimDir.x, dimDir.y, 0 )
    diaDim1 = sketch.sketchDimensions.addDiameterDimension( startCircle, textPoint )
    diaDim1.value = dia1IN * 2.54
    # sketch.geometricConstraints.addCoincident( startCircle.centerSketchPoint, line.startSketchPoint )

    # Create End point centered circle and dimension it
    endCircle = sketch.sketchCurves.sketchCircles.addByCenterRadius( line.endSketchPoint, dia2IN * 2.54 / 2 )
    endCircle.isConstruction = True

    textPoint = futil.offsetPoint3D( endCircle.centerSketchPoint.geometry, dimDir.x, dimDir.y, 0 )
    diaDim2 = sketch.sketchDimensions.addDiameterDimension( endCircle, textPoint )
    diaDim2.value = dia2IN * 2.54
    # sketch.geometricConstraints.addCoincident( endCircle.centerSketchPoint, line.endSketchPoint )

    return ([ startCircle, endCircle ], [diaDim1, diaDim2])

def modifyCCLine( ccLine: CCLine ):

    ld = ccLine.data

    label = createLabelString( ld )
    ccLine.textBox.text = label

    ccLine.lengthDim.value = (ld.ccDistIN + ld.ExtraCenterIN) * 2.54

    ccLine.PD1Dim.value = ld.PD1 * 2.54
    ccLine.PD2Dim.value = ld.PD2 * 2.54
    ccLine.OD1Dim.value = ld.OD1 * 2.54
    ccLine.OD2Dim.value = ld.OD2 * 2.54

def isCCLine( line: adsk.fusion.SketchLine ) -> bool :
    attr = line.attributes.itemByName( CC_ATTRIBUTE_GROUP, CC_LINE_N1 )
    if not attr:
        return False
    
    return True

def setAttribute( ent: adsk.fusion.SketchEntity, name: str, value: str ) :
    newattr = ent.attributes.add( CC_ATTRIBUTE_GROUP, name, value )
    if not newattr:
        futil.log(f'  ======== Adding attribute {name} = {value} FAILED!!')

def setAttributeList( ents: list[adsk.fusion.SketchEntity], name: str, value: str ) :
    for ent in ents:
        # futil.log(f'Setting attribute {name} on {ent.entityToken}')
        newattr = ent.attributes.add( CC_ATTRIBUTE_GROUP, name, value )
        if not newattr:
            futil.log(f'  ======== Adding attribute {name} = {value} FAILED!!')

def setCCLineAttributes( ccLine: CCLine ) :
    line = ccLine.line
    ld = ccLine.data

    # Set the data attributes
    setAttribute( line, CC_LINE_N1, str(ld.N1) )
    setAttribute( line, CC_LINE_N2, str(ld.N2) )
    setAttribute( line, CC_LINE_TEETH, str(ld.Teeth) )
    setAttribute( line, CC_LINE_EC, str(ld.ExtraCenterIN) )
    setAttribute( line, CC_LINE_MOTION_TYPE, str(ld.motion) )

    # Set the end circle tokens
    setAttribute( line, CC_LINE_PITCH_CIRCLE1, ccLine.pitchCircle1.entityToken )
    setAttribute( line, CC_LINE_PITCH_CIRCLE2, ccLine.pitchCircle2.entityToken )
    setAttribute( line, CC_LINE_OD_CIRCLE1, ccLine.ODCircle1.entityToken )
    setAttribute( line, CC_LINE_OD_CIRCLE2, ccLine.ODCircle2.entityToken )

    # Set the TextBox token
    setAttribute( line, CC_LINE_TEXT, ccLine.textBox.entityToken )
    setAttribute( line, CC_LINE_MIDPT, ccLine.midPt.entityToken )

    # Set the dimension tokens
    setAttribute( line, CC_LINE_LENGTH_DIM, ccLine.lengthDim.entityToken )
    setAttribute( line, CC_LINE_PITCH_CIRCLE1_DIM, ccLine.PD1Dim.entityToken )
    setAttribute( line, CC_LINE_PITCH_CIRCLE2_DIM, ccLine.PD2Dim.entityToken )
    setAttribute( line, CC_LINE_OD_CIRCLE1_DIM, ccLine.OD1Dim.entityToken )
    setAttribute( line, CC_LINE_OD_CIRCLE2_DIM, ccLine.OD2Dim.entityToken )
    setAttribute( line, CC_LINE_TEXT_HEIGHT_DIM, ccLine.textHeight.entityToken )

    # futil.print_Attributes( line )

    # Set the line as the parent to all the child entities
    setAttributeList( [ccLine.pitchCircle1, ccLine.pitchCircle2, ccLine.ODCircle1, ccLine.ODCircle2,
                       ccLine.PD1Dim, ccLine.PD2Dim, ccLine.OD1Dim, ccLine.OD2Dim, ccLine.lengthDim,
                       ccLine.textBox, ccLine.textHeight, ccLine.midPt],
                       CC_LINE_PARENT_LINE, line.entityToken )
    textDef: adsk.fusion.MultiLineTextDefinition = ccLine.textBox.definition
    for tbline in textDef.rectangleLines:
        setAttribute( tbline,  CC_LINE_PARENT_LINE, line.entityToken )

    # futil.print_Attributes( ccLine.pitchCircle1 )

def getLineData( line: adsk.fusion.SketchLine ) -> CCLineData :

    cclineData = CCLineData()
    attr = line.attributes.itemByName( CC_ATTRIBUTE_GROUP, CC_LINE_N1 )
    if not attr:
        return None
    
    cclineData.N1 = int(attr.value)
    attr = line.attributes.itemByName( CC_ATTRIBUTE_GROUP, CC_LINE_N2 )
    cclineData.N2 = int(attr.value)
    attr = line.attributes.itemByName( CC_ATTRIBUTE_GROUP, CC_LINE_TEETH )
    cclineData.Teeth = int(attr.value)
    attr = line.attributes.itemByName( CC_ATTRIBUTE_GROUP, CC_LINE_EC )
    cclineData.ExtraCenterIN = float(attr.value)
    attr = line.attributes.itemByName( CC_ATTRIBUTE_GROUP, CC_LINE_MOTION_TYPE )
    cclineData.motion = int(attr.value)

    return cclineData

# Returns the parent line of the CCLine or None if not a member of a CCLine
def getParentLine( curve: adsk.fusion.SketchCurve ) -> adsk.fusion.SketchLine :
    if not curve:
        return None
    
    # Check to see if the curve has the CC_LINE_PARENT_LINE attribute set
    token = curve.attributes.itemByName( CC_ATTRIBUTE_GROUP, CC_LINE_PARENT_LINE )
    if not token:
        # No parent line set.  Check if this is the actual CCLine by looking for N1
        token = curve.attributes.itemByName( CC_ATTRIBUTE_GROUP, CC_LINE_N1 )
        if not token:
            return None
        else:
            return curve
    
    # Get the Parent Line and return it if it exists
    line = curve.parentSketch.parentComponent.parentDesign.findEntityByToken( token.value )
    if len(line) == 0:
        return None
    
    return line[0]
    
def getChildCircles( line: adsk.fusion.SketchLine ) -> list[adsk.fusion.SketchCircle] :

    design = line.parentSketch.parentComponent.parentDesign

    attrNames = [ CC_LINE_PITCH_CIRCLE1, CC_LINE_PITCH_CIRCLE2, CC_LINE_OD_CIRCLE1, CC_LINE_OD_CIRCLE2 ]

    circles = []
    i = 0
    while i < len(attrNames):
        token = line.attributes.itemByName( CC_ATTRIBUTE_GROUP, attrNames[i] )
        circle = design.findEntityByToken( token.value )
        if len( circle ) == 0:
            futil.log(f'Error getting child circles of line...')
            return None
        circles.append( circle[0] )
        i += 1

    return circles

def getChildEntity( line: adsk.fusion.SketchLine, attribute: str ) :

    design = line.parentSketch.parentComponent.parentDesign

    token = line.attributes.itemByName( CC_ATTRIBUTE_GROUP, attribute )
    if not token:
        futil.log(f'Error getting attribute "{attribute}" from line')

    ents = design.findEntityByToken( token.value )
    if len( ents ) == 0:
        futil.log(f'Error getting child entity "{attribute}"')
        return None
    
    return ents[0]

def getCCLineFromEntity( curve: adsk.fusion.SketchCurve ) -> CCLine :
    ccLine = CCLine()

    # futil.log(f'getCCLineFromEntity --- ')
    # futil.print_Attributes( curve )

    ccLine.line = getParentLine( curve )
    if not ccLine.line:
        return None

    # Get the associated data from the line attributes
    ccLine.data = getLineData( ccLine.line )

    circles = getChildCircles( ccLine.line )
    if len(circles) != 4:
        futil.log( f'Error getting child circle data.')
        return ccLine
    
    ccLine.pitchCircle1 = circles[0]
    ccLine.pitchCircle2 = circles[1]
    ccLine.ODCircle1 = circles[2]
    ccLine.ODCircle2 = circles[3]

    ccLine.lengthDim = getChildEntity( ccLine.line, CC_LINE_LENGTH_DIM )
    ccLine.PD1Dim = getChildEntity( ccLine.line, CC_LINE_PITCH_CIRCLE1_DIM )
    ccLine.PD2Dim = getChildEntity( ccLine.line, CC_LINE_PITCH_CIRCLE2_DIM )
    ccLine.OD1Dim = getChildEntity( ccLine.line, CC_LINE_OD_CIRCLE1_DIM )
    ccLine.OD2Dim = getChildEntity( ccLine.line, CC_LINE_OD_CIRCLE2_DIM )
    ccLine.textBox = getChildEntity( ccLine.line, CC_LINE_TEXT )
    ccLine.midPt = getChildEntity( ccLine.line, CC_LINE_MIDPT )
    ccLine.textHeight = getChildEntity( ccLine.line, CC_LINE_TEXT_HEIGHT_DIM )

    return ccLine
    
def deleteCCLine( ccLine: CCLine ):
    try:
        ccLine.pitchCircle1.deleteMe()
    except:
        None
    try:
        ccLine.pitchCircle2.deleteMe()
    except:
        None
    try:
        ccLine.ODCircle1.deleteMe()
    except:
        None
    try:
        ccLine.ODCircle2.deleteMe()
    except:
        None
    try:
        ccLine.textBox.deleteMe()
    except:
        None
    try:
        ccLine.line.deleteMe()
    except:
        None
    try:
        ccLine.midPt.deleteMe()
    except:
        None