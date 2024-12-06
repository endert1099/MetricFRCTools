import adsk.core
import adsk.fusion
import os
import math
from ...lib import fusionAddInUtils as futil
from ... import config
app = adsk.core.Application.get()
ui = app.userInterface


# TODO *** Specify the command identity information. ***
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_CCDistanceDialog'
CMD_NAME = 'C-C Distance'
CMD_Description = 'Determine pitch diameters and C-C distances'

# Specify that the command will be promoted to the panel.
IS_PROMOTED = True

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []


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


# Function that is called when a user clicks the corresponding button in the UI.
# This defines the contents of the command dialog and connects to the command related events.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Created Event')

    # https://help.autodesk.com/view/fusion360/ENU/?contextId=CommandInputs
    inputs = args.command.commandInputs

    # Motion Component Type
    motionType = inputs.addDropDownCommandInput('motion_type', 'Motion Tranfer Type', adsk.core.DropDownStyles.TextListDropDownStyle)
    motionType.listItems.add('20DP Gears', True, '')
    motionType.listItems.add('HTD 5mm Belt', False, '')
    motionType.listItems.add('GT2 3mm Belt', False, '')

    # Create a selection input.
    curveSelection = inputs.addSelectionInput('curve_selection', 'Starting Circles', 'Select nothing, a circle, a line, or two starting circles')
    curveSelection.addSelectionFilter( "SketchCurves" )
    curveSelection.setSelectionLimits( 0, 2 )

    # Create a value input field and set the default using 1 unit of the default length unit.
    defaultLengthUnits = ""
    default_value = adsk.core.ValueInput.createByString('24')
    inputs.addValueInput('cog1_teeth', 'Cog#1 Number of Teeth', defaultLengthUnits, default_value)

    # Create a value input field and set the default using 1 unit of the default length unit.
    defaultLengthUnits = ""
    default_value = adsk.core.ValueInput.createByString('36')
    inputs.addValueInput('cog2_teeth', 'Cog#2 Number of Teeth', defaultLengthUnits, default_value)

    inputs.addBoolValueInput( "swap_cogs", "Swap Cogs", True )

    beltTeeth = inputs.addIntegerSpinnerCommandInput( "belt_teeth", "Belt Teeth", 40, 400, 1, 70 )
    beltTeeth.isVisible = False

    # Create a value input field and set the default using 1 unit of the default length unit.
    defaultLengthUnits = "in"
    default_value = adsk.core.ValueInput.createByString('0.003')
    inputs.addValueInput('extra_center', 'Extra Center Distance', defaultLengthUnits, default_value)

    # TODO Connect to the events that are needed by this command.
    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
    futil.add_handler(args.command.executePreview, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.validateInputs, command_validate_input, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)


# This event handler is called when the user clicks the OK button in the command dialog or 
# is immediately called after the created event not command inputs were created for the dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Execute Event')

    # Get a reference to your command's inputs.
    inputs = args.command.commandInputs
    motionType: adsk.core.DropDownCommandInput = inputs.itemById('motion_type' )
    curveSelection: adsk.core.SelectionCommandInput = inputs.itemById('curve_selection')
    cog1TeethInp: adsk.core.ValueInput = inputs.itemById('cog1_teeth')
    cog2TeethInp: adsk.core.ValueInput = inputs.itemById('cog2_teeth')
    swapCogs =  inputs.itemById( "swap_cogs" ).value
    beltTeeth: adsk.core.IntegerSpinnerCommandInput = inputs.itemById( "belt_teeth" )
    extraCenterInp: adsk.core.ValueInput = inputs.itemById('extra_center')
    extraCenterIN = extraCenterInp.value / 2.54

    N1Teeth = int(cog1TeethInp.value)
    N2Teeth = int(cog2TeethInp.value)

    if swapCogs :
        N2Teeth = int(cog1TeethInp.value)
        N1Teeth = int(cog2TeethInp.value)

    startSketchPt = None
    endSketchPt = None
    ccLine = None

    futil.log( f'Selection count = {curveSelection.selectionCount}')
    futil.print_Selection( curveSelection )
    if curveSelection.selectionCount == 1 and \
       curveSelection.selection(0).entity.objectType == adsk.fusion.SketchCircle.classType() :
        startSketchPt = curveSelection.selection(0).entity.centerSketchPoint
    elif curveSelection.selectionCount == 1 and \
         curveSelection.selection(0).entity.objectType == adsk.fusion.SketchLine.classType() :
        ccLine = curveSelection.selection(0).entity
    elif curveSelection.selectionCount == 2 and \
         curveSelection.selection(0).entity.objectType == adsk.fusion.SketchCircle.classType() :
        startSketchPt = curveSelection.selection(0).entity.centerSketchPoint
        endSketchPt = curveSelection.selection(1).entity.centerSketchPoint

    if motionType.selectedItem.index == 0:
        # 20DP Gears
        ccDistIN = GearsCCDistanceIN( N1Teeth, N2Teeth, 20 )
        lineLabel = f'Gears 20DP ({N1Teeth}T+{N2Teeth}T)'
        PD1 = GearsPitchDiameterIN( N1Teeth, 20 )
        PD2 = GearsPitchDiameterIN( N2Teeth, 20 )
        OD1 = GearsOuterDiameterIN( N1Teeth, 20 )
        OD2 = GearsOuterDiameterIN( N2Teeth, 20 )
    else :
        if motionType.selectedItem.index == 1:
            # HTD 5mm Belt
            lineLabel = f'HTD 5mm ({int(beltTeeth.value)}T)'
            beltPitchMM = 5
        else :
            # HTD 3mm Belt
            lineLabel = f'GT2 3mm ({int(beltTeeth.value)}T)'
            beltPitchMM = 3
        ccDistIN = BeltCCDistanceIN( N1Teeth, N2Teeth, beltTeeth.value, beltPitchMM )
        PD1 = BeltPitchDiameterIN( N1Teeth, beltPitchMM )
        PD2 = BeltPitchDiameterIN( N2Teeth, beltPitchMM )
        OD1 = BeltOuterDiameterIN( N1Teeth, beltPitchMM)
        OD2 = BeltOuterDiameterIN( N2Teeth, beltPitchMM )

    if ccLine == None:
        ccLine = createCCLine( startSketchPt, endSketchPt )
    dimAndLabelCCLine( ccLine, ccDistIN + extraCenterIN, lineLabel )
    createEndCircles( ccLine, PD1, PD2 )
    createEndCircles( ccLine, OD1, OD2 )


# # This event handler is called when the command needs to compute a new preview in the graphics window.
# def command_preview(args: adsk.core.CommandEventArgs):
#     # General logging for debug.
#     # futil.log(f'{CMD_NAME} Command Preview Event')
#     inputs = args.command.commandInputs
#     motionType: adsk.core.DropDownCommandInput = inputs.itemById('motion_type' )
#     curveSelection: adsk.core.SelectionCommandInput = inputs.itemById('curve_selection')
#     cog1Teeth: adsk.core.ValueInput = inputs.itemById('cog1_teeth')
#     cog2Teeth: adsk.core.ValueInput = inputs.itemById('cog2_teeth')
#     beltTeeth: adsk.core.IntegerSpinnerCommandInput = inputs.itemById( "belt_teeth" )

#     startSketchPt = None
#     endSketchPt = None
#     ccLine = None

#     if curveSelection.selectionCount == 1 and \
#        curveSelection.selection(0).entity.objectType == adsk.fusion.SketchCircle.classType() :
#         startSketchPt = curveSelection.selection(0).entity.centerSketchPoint
#     elif curveSelection.selectionCount == 1 and \
#          curveSelection.selection(0).entity.objectType == adsk.fusion.SketchLine.classType() :
#         ccLine = curveSelection.selection(0).entity
#     elif curveSelection.selectionCount == 2 and \
#          curveSelection.selection(0).entity.objectType == adsk.fusion.SketchCircle.classType() :
#         startSketchPt = curveSelection.selection(0).entity.centerSketchPoint
#         endSketchPt = curveSelection.selection(1).entity.centerSketchPoint

#     if motionType.selectedItem.index == 0:
#         # 20DP Gears
#         ccDistIN = GearsCCDistanceIN( cog1Teeth.value, cog2Teeth.value, 20 )
#         lineLabel = f'Gear 20DP - {cog1Teeth.value}T+{cog2Teeth.value}T'
#         PD1 = GearsPitchDiameterIN( cog1Teeth.value, 20 )
#         PD2 = GearsPitchDiameterIN( cog2Teeth.value, 20 )
#         OD1 = GearsOuterDiameterIN( cog1Teeth.value, 20 )
#         OD2 = GearsOuterDiameterIN( cog2Teeth.value, 20 )
#     elif motionType.selectedItem.index == 1:
#         # HTD 5mm Belt
#         ccDistIN = BeltCCDistanceIN( cog1Teeth.value, cog2Teeth.value, beltTeeth.value, 5 )
#         lineLabel = f'HTD 5mm - {beltTeeth.value}T Belt'
#         PD1 = BeltPitchDiameterIN( cog1Teeth.value, 5 )
#         PD2 = BeltPitchDiameterIN( cog2Teeth.value, 5 )
#         OD1 = BeltOuterDiameterIN( cog1Teeth.value, 5 )
#         OD2 = BeltOuterDiameterIN( cog2Teeth.value, 5 )
#     else:
#         # HTD 3mm Belt
#         ccDistIN = BeltCCDistanceIN( cog1Teeth.value, cog2Teeth.value, beltTeeth.value, 3 )
#         lineLabel = f'GT2 3mm - {beltTeeth.value}T Belt'
#         PD1 = BeltPitchDiameterIN( cog1Teeth.value, 3 )
#         PD2 = BeltPitchDiameterIN( cog2Teeth.value, 3 )
#         OD1 = BeltOuterDiameterIN( cog1Teeth.value, 3 )
#         OD2 = BeltOuterDiameterIN( cog2Teeth.value, 3 )

#     if ccLine == None:
#         ccLine = createCCLine( startSketchPt, endSketchPt )
#     dimAndLabelCCLine( ccLine, ccDistIN, lineLabel )
#     createEndCircles( ccLine, PD1, PD2 )
#     createEndCircles( ccLine, OD1, OD2 )

# This event handler is called when the user changes anything in the command dialog
# allowing you to modify values of other inputs based on that change.
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    changed_input = args.input
    inputs = args.inputs

    # General logging for debug.
    # futil.log(f'{CMD_NAME} Input Changed Event fired from a change to {changed_input.id}')

    motionType: adsk.core.DropDownCommandInput = inputs.itemById('motion_type')
    beltTeeth: adsk.core.IntegerSpinnerCommandInput = inputs.itemById( "belt_teeth" )

    if motionType.selectedItem.index == 0 :
        futil.log(f'   Turning off belt teeth')
        beltTeeth.isVisible = False
    else:
        futil.log(f'   Turning ON belt teeth')
        beltTeeth.isVisible = True


# This event handler is called when the user interacts with any of the inputs in the dialog
# which allows you to verify that all of the inputs are valid and enables the OK button.
def command_validate_input(args: adsk.core.ValidateInputsEventArgs):

    # futil.log(f'{CMD_NAME} Command Validate Event')

    inputs = args.inputs
    motionType: adsk.core.DropDownCommandInput = inputs.itemById('motion_type')
    curveSelection: adsk.core.SelectionCommandInput = inputs.itemById('curve_selection')
    cog1Teeth: adsk.core.ValueInput = inputs.itemById('cog1_teeth')
    cog2Teeth: adsk.core.ValueInput = inputs.itemById('cog2_teeth')
    beltTeeth: adsk.core.IntegerSpinnerCommandInput = inputs.itemById( "belt_teeth" )
    extraCenter: adsk.core.ValueInput = inputs.itemById('extra_center')

    if curveSelection.selectionCount == 2:
        # We have selected two entitites
        if curveSelection.selection(0).entity.objectType == adsk.fusion.SketchLine.classType() or\
           curveSelection.selection(1).entity.objectType == adsk.fusion.SketchLine.classType() :
            # If either the first entity selected was a line or the newly selected entity
            # is a line the only keep the newly selected item.  Don't allow a line with something else.
            newSel = curveSelection.selection(1).entity
            curveSelection.clearSelection()
            curveSelection.addSelection( newSel )

    if not (cog1Teeth.value >= 8 and cog1Teeth.value < 100 and cog2Teeth.value >= 8 and cog1Teeth.value < 100 ):
        args.areInputsValid = False
        return

    # if motionType.selectedItem.index == 0:
    #     ccDist = GearsCCDistance( cog1Teeth.value, cog2Teeth.value )
    # elif motionType.selectedItem.index == 1:
    #     ccDist = BeltCCDistance( cog1Teeth.value, cog2Teeth.value, beltTeeth.value, 5 )
    # else:
    #     ccDist = BeltCCDistance( cog1Teeth.value, cog2Teeth.value, beltTeeth.value, 3 )

    args.areInputsValid = True        

# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    # futil.log(f'{CMD_NAME} Command Destroy Event')

    global local_handlers
    local_handlers = []


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

    futil.log( f'startpt = {startpt}')
    futil.log( f'endpt = {endpt}')

    if startpt == None:
        design = adsk.fusion.Design.cast(app.activeProduct)
        sketch = design.activeEditObject
        startpt = sketch.sketchPoints.add( adsk.core.Point3D.create( 0, 0, 0 ) )
    
    sketch = startpt.parentSketch

    if endpt == None:
        endpt3D = futil.offsetPoint3D( startpt.geometry, 2 * 2.54, 0, 0 )
        endpt = sketch.sketchPoints.add( endpt3D )

    # Create C-C line a midpoint for it and dimension it
    ccLine = sketch.sketchCurves.sketchLines.addByTwoPoints( startpt, endpt )
    ccLine.isConstruction = True

    return ccLine

def dimAndLabelCCLine( line: adsk.fusion.SketchLine, ccDistIN: float, label: str ) :

    sketch = line.parentSketch

    midPt = futil.midPoint3D( line.startSketchPoint.geometry, line.endSketchPoint.geometry )
    normal = futil.sketchLineNormal( line )
    normal = futil.multVector2D( normal, ccDistIN / 4 )

    # Dimension C-C line
    if abs(normal.y) < 0.001  :
        textPt = futil.offsetPoint3D( midPt, normal.x, normal.y, 0 )
    elif normal.y < 0 :
        textPt = futil.offsetPoint3D( midPt, normal.x, normal.y, 0 )
    else:
        textPt = futil.offsetPoint3D( midPt, -normal.x, -normal.y, 0 )
    
    ccDim = sketch.sketchDimensions.addDistanceDimension( 
        line.startSketchPoint, line.endSketchPoint, 
        adsk.fusion.DimensionOrientations.AlignedDimensionOrientation, textPt )
    ccDim.value = ccDistIN * 2.54

    # Create SketchText and attach it to the C-C Line
    textHeight = int((ccDistIN + 1)) / 32.0
    futil.log( f'ccDist = {ccDistIN}in, Text Height = {textHeight}in')
    textHeight = textHeight * 2.54 # in cm
    # cornerPt = adsk.core.Point3D.create( 0, 0, 0 )
    # diagPt =  adsk.core.Point3D.create( ccLine.length, textHeight, 0 )
    cornerPt = line.startSketchPoint.geometry
    diagPt =  futil.addPoint3D( cornerPt, adsk.core.Point3D.create( line.length, textHeight, 0 ) )
    textInput = sketch.sketchTexts.createInput2( label, textHeight )
    textInput.setAsMultiLine( cornerPt, diagPt, 
                        adsk.core.HorizontalAlignments.CenterHorizontalAlignment,
                        adsk.core.VerticalAlignments.MiddleVerticalAlignment, 0 )
    text = sketch.sketchTexts.add( textInput )
    textDef: adsk.fusion.MultiLineTextDefinition = text.definition
    textBoxLines = textDef.rectangleLines
    textBaseLine = textBoxLines[0]
    TextHeightLine = textBoxLines[1]
    midPt3D = futil.midPoint3D(textBaseLine.startSketchPoint.geometry, textBaseLine.endSketchPoint.geometry )
    midPt = sketch.sketchPoints.add( midPt3D )

    textPoint = futil.offsetPoint3D( midPt3D, -textHeight/2, textHeight/2, 0 )
    heightDim = sketch.sketchDimensions.addDistanceDimension( TextHeightLine.startSketchPoint, TextHeightLine.endSketchPoint,
                                                              adsk.fusion.DimensionOrientations.AlignedDimensionOrientation,
                                                              textPoint  )
    heightDim.value = textHeight * 2.0

    sketch.geometricConstraints.addMidPoint( midPt, textBaseLine  )
    sketch.geometricConstraints.addMidPoint( midPt, line  )
    sketch.geometricConstraints.addParallel( textBaseLine, line  )
    if textBaseLine.startSketchPoint.geometry.distanceTo(line.startSketchPoint.geometry) < \
        textBaseLine.startSketchPoint.geometry.distanceTo(line.endSketchPoint.geometry) :
        sketch.geometricConstraints.addCoincident( textBaseLine.startSketchPoint, line.startSketchPoint )
    else:
        sketch.geometricConstraints.addCoincident( textBaseLine.startSketchPoint, line.endSketchPoint )


def createEndCircles( line: adsk.fusion.SketchLine, dia1IN: float, dia2IN: float ) -> float :

    sketch = line.parentSketch

    normal = futil.sketchLineNormal( line )

    # Create Start point centered circle and dimension it
    startCircle = sketch.sketchCurves.sketchCircles.addByCenterRadius( line.startSketchPoint, dia1IN * 2.54 / 2 )
    startCircle.isConstruction = True

    textPoint = futil.offsetPoint3D( startCircle.centerSketchPoint.geometry, normal.x, normal.y, 0 )
    diaDim = sketch.sketchDimensions.addDiameterDimension( startCircle, textPoint )
    diaDim.value = dia1IN * 2.54
    # sketch.geometricConstraints.addCoincident( startCircle.centerSketchPoint, line.startSketchPoint )

    # Create End point centered circle and dimension it
    endCircle = sketch.sketchCurves.sketchCircles.addByCenterRadius( line.endSketchPoint, dia2IN * 2.54 / 2 )
    endCircle.isConstruction = True

    textPoint = futil.offsetPoint3D( endCircle.centerSketchPoint.geometry, normal.x, normal.y, 0 )
    diaDim = sketch.sketchDimensions.addDiameterDimension( endCircle, textPoint )
    diaDim.value = dia2IN * 2.54
    # sketch.geometricConstraints.addCoincident( endCircle.centerSketchPoint, line.endSketchPoint )