import adsk.core
import adsk.fusion
import os
from ...lib import fusionAddInUtils as futil
from ... import config
app = adsk.core.Application.get()
ui = app.userInterface


# TODO *** Specify the command identity information. ***
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_TubifyDialog'
CMD_NAME = 'Tubify Solid'
CMD_Description = 'Shell and create holes in a rectangular solid'

# Specify that the command will be promoted to the panel.
IS_PROMOTED = True

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []

wallThicknesses = ( 
    (0.050, '0.050"'),
    (0.0625, '1/16"'),
    (0.09375, '3/32"'),
    (0.1, '0.100"'),
    (0.125, '1/8"'),
)
wallThicknessesDefault = wallThicknesses.index( (0.125, '1/8"') )


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
    panel = workspace.toolbarPanels.itemById(config.PANEL_ID)

    # Create the the FRCTool submenu.
    submenu = panel.controls.itemById( config.DROPDOWN_ID )

    # Create the button command control in the UI.
    control = submenu.controls.addCommand(cmd_def)

    # Specify if the command is promoted to the main toolbar. 
    control.isPromoted = IS_PROMOTED


# Executed when add-in is stopped.
def stop():
    # Get the various UI elements for this command
    workspace = ui.workspaces.itemById(config.WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(config.PANEL_ID)
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

    # TODO Define the dialog for your command by adding different inputs to the command.

    # Create a Solid Body selection input.
    solidSelection = inputs.addSelectionInput('tube_solid', 'Solid', 'Select the solid to Tubify')
    solidSelection.addSelectionFilter( "SolidBodies" )
    solidSelection.setSelectionLimits( 1, 1 )

    # Create a simple text box input.
    holeSides = inputs.addDropDownCommandInput('hole_sides', 'Hole Sides', adsk.core.DropDownStyles.TextListDropDownStyle)
    holeSides.listItems.add('No Holes', False, '')
    holeSides.listItems.add('2 Sides', False, '')
    holeSides.listItems.add('4 Sides', True, '')

    # Create a simple text box input.
    wallThickInput = inputs.addDropDownCommandInput('wall_thickness', 'Wall Thickness', adsk.core.DropDownStyles.TextListDropDownStyle)
    for wallthick in wallThicknesses:
        wallThickInput.listItems.add( wallthick[1], False, '')
    wallThickInput.listItems.item( wallThicknessesDefault ).isSelected = True

    # Create a value input field and set the default using 1 unit of the default length unit.
    defaultLengthUnits = "in"
    default_value = adsk.core.ValueInput.createByString('0.5')
    inputs.addValueInput('end_offset', 'End Offset', defaultLengthUnits, default_value)

    # Create a checkbox for partial holes.
    inputs.addBoolValueInput( "create_partial_holes", "Show Partial Holes", True, "", True )

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

    # Get a reference to your command's inputs.
    inputs = args.command.commandInputs
    solidSelection: adsk.core.SelectionCommandInput = inputs.itemById('tube_solid')
    endOffset: adsk.core.ValueCommandInput = inputs.itemById('end_offset')
    holeSides: adsk.core.DropDownCommandInput = inputs.itemById('hole_sides')
    wallThickness: adsk.core.DropDownCommandInput = inputs.itemById('wall_thickness')
    showPartialHoles = inputs.itemById('create_partial_holes').value

    futil.print_Selection( solidSelection )
    solid: adsk.fusion.BRepBody = solidSelection.selection(0).entity
    if solid.vertices.count != 8 :
        futil.popup_error(f'Invalid number of vertices in body!  Should be 8 got {solid.vertices.count}')
        return
    
    orientedBB = solid.orientedMinimumBoundingBox
    futil.print_OrientedBB( orientedBB )
    longLength = orientedBB.height
    if orientedBB.width > longLength:
        longLength = orientedBB.width
    if orientedBB.length > longLength:
        longLength = orientedBB.length
    longLength /= 2.54 # convert to inches

    # Find end faces with the smallest area
    endArea = 999999
    sideMaxArea = 0
    i = 0
    while i < solid.faces.count :
        face = solid.faces.item(i)
        if face.area < endArea :
            endArea = face.area
        if face.area > sideMaxArea :
            sideMaxArea = face.area
        i += 1

    endFaces = adsk.core.ObjectCollection.create()
    i = 0
    while i < solid.faces.count :
        face = solid.faces.item(i)
        if abs(face.area - endArea) < 0.001:
            endFaces.add( face )
        i += 1

    hasWiderSides = False
    if abs(endArea - 12.9032) < 0.001 :
        futil.log( f'Found {len(endFaces)} end Faces of the Solid 2 x 1 Body.')
        hasWiderSides = True
    elif abs(endArea - 6.4516) < 0.001 :
        futil.log( f'Found {len(endFaces)} end Faces of the Solid 1 x 1 Body.')
    else :
        futil.log( f'Found {len(endFaces)} end Faces of the Solid ? x ? Body with area = {endArea}.')
        futil.popup_error(f'Body does not appear to be either 1x1 or 1x2')
        return

    # Determine the side faces and wide side faces if 2 x 1 body
    narrowSideFaces = adsk.core.ObjectCollection.create()
    wideSideFaces = adsk.core.ObjectCollection.create()
    otherWideSideFaces = adsk.core.ObjectCollection.create()
    i = 0
    while i < solid.faces.count :
        face = solid.faces.item(i)
        if abs(face.area - sideMaxArea) < 0.001:
            wideSideFaces.add( face )
        elif hasWiderSides and face.area - endArea > 0.001 :
            narrowSideFaces.add( face )
        i += 1

    if not hasWiderSides:
        otherWideSideFaces.add( wideSideFaces.item(1) )
        otherWideSideFaces.add( wideSideFaces.item(3) )
        wideSideFaces.removeByIndex( 1 )
        wideSideFaces.removeByIndex( 2 ) # 3 becomes 2

    futil.log( f'Found {len(wideSideFaces)} wide side Faces, {len(otherWideSideFaces)} other wide faces, and {len(narrowSideFaces)} narrow side Faces.')


    # Obtain the component of the solid body
    workingComp = solid.parentComponent

    # Shell out the tube 
    shells = workingComp.features.shellFeatures
    wallThickness.selectedItem.index
    shellThickness = adsk.core.ValueInput.createByReal( wallThicknesses[wallThickness.selectedItem.index][0] * 2.54 )
    shellSolidInput = shells.createInput( endFaces )
    shellSolidInput.insideThickness = shellThickness
    shells.add( shellSolidInput )

    # If no holes just return
    if holeSides.selectedItem.index == 0 :
        return

    # 2 Side Holes
    if hasWiderSides :
        createHoleProfiles( workingComp, narrowSideFaces, longLength, 1.0, 2.0, endOffset.value / 2.54, showPartialHoles )
    else:
        createHoleProfiles( workingComp, wideSideFaces, longLength, 1.0, 1.0, endOffset.value / 2.54, showPartialHoles )

    # 4 Side Holes
    if holeSides.selectedItem.index == 2 : 
        if hasWiderSides :
            createHoleProfiles( workingComp, wideSideFaces, longLength, 2.0, 1.0, endOffset.value / 2.54, showPartialHoles )
        else :
            createHoleProfiles( workingComp, otherWideSideFaces, longLength, 1.0, 1.0, endOffset.value / 2.54, showPartialHoles )


# This event handler is called when the command needs to compute a new preview in the graphics window.
def command_preview(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    # futil.log(f'{CMD_NAME} Command Preview Event')
    inputs = args.command.commandInputs

    command_execute( args )

# This event handler is called when the user changes anything in the command dialog
# allowing you to modify values of other inputs based on that change.
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    changed_input = args.input
    inputs = args.inputs

    # # General logging for debug.
    # futil.log(f'{CMD_NAME} Input Changed Event fired from a change to {changed_input.id}')


# This event handler is called when the user interacts with any of the inputs in the dialog
# which allows you to verify that all of the inputs are valid and enables the OK button.
def command_validate_input(args: adsk.core.ValidateInputsEventArgs):

    inputs = args.inputs

    solidSelection: adsk.core.SelectionCommandInput = inputs.itemById('tube_solid')
    endOffset: adsk.core.ValueCommandInput = inputs.itemById('end_offset')
    
    # Verify the validity of the input values. This controls if the OK button is enabled or not.

    if endOffset.value >= 0 and endOffset.value < 2.54 :  # in centimeters always
        args.areInputsValid = True
    else:
        args.areInputsValid = False
        

# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    # futil.log(f'{CMD_NAME} Command Destroy Event')

    global local_handlers
    local_handlers = []


def createHoleProfiles( 
        workingComp: adsk.fusion.Component, 
        sideFaces: adsk.core.ObjectCollection,
        length: float, width: float, cutDepth: float, offset: float, showPartialHoles: bool ) :

    # Create a new sketch for the wide side holes
    sketch = workingComp.sketches.add( sideFaces.item(0) )
    sketchEdges = adsk.core.ObjectCollection.create()
    for edge in sideFaces.item(0).edges :
        sketchEdges.add( sketch.project( edge ).item(0) )
    
    # futil.print_SketchObjectCollection( sketchEdges )

    longEdge: adsk.fusion.SketchLine = sketchEdges.item(0)
    shortEdge: adsk.fusion.SketchLine = sketchEdges.item(1)
    if shortEdge.length > longEdge.length :
        longEdge: adsk.fusion.SketchLine = sketchEdges.item(1)
        shortEdge: adsk.fusion.SketchLine = sketchEdges.item(0)
        
    cornerPoint = longEdge.endSketchPoint
    if longEdge.endSketchPoint.geometry.isEqualTo( shortEdge.startSketchPoint.geometry ) :
        # futil.log( f'longEdge end is shortEdge Start.')
        None
    elif longEdge.endSketchPoint.geometry.isEqualTo( shortEdge.endSketchPoint.geometry ) :
        # futil.log( f'longEdge end is shortEdge end.')
        None
    elif shortEdge.endSketchPoint.geometry.isEqualTo( longEdge.startSketchPoint.geometry ) :
        cornerPoint = shortEdge.endSketchPoint
        # futil.log( f'shortEdge end is longEdge Start.')
    elif shortEdge.startSketchPoint.geometry.isEqualTo( longEdge.startSketchPoint.geometry ) :
        cornerPoint = shortEdge.startSketchPoint
        # futil.log( f'shortEdge start is longEdge Start.')
    else:
        futil.print_Point3D( longEdge.startSketchPoint.geometry, "longEdge start: ")
        futil.print_Point3D( longEdge.endSketchPoint.geometry, "longEdge end: ")
        futil.print_Point3D( shortEdge.startSketchPoint.geometry, "shortEdge start: ")
        futil.print_Point3D( shortEdge.endSketchPoint.geometry, "shortEdge end: ")
        futil.popup_error(f'Unhandled shortEdge/longEdge point case.')
        return

    # Create the corner hole to use as the rectangular pattern
    centroid = futil.BBCentroid( sketch.boundingBox )
    cornerHole = sketch.sketchCurves.sketchCircles.addByCenterRadius( centroid, 0.196 * 2.54 / 2 )
    textPoint = futil.offsetPoint3D( cornerHole.centerSketchPoint.geometry, 0.1, 0.1, 0 )
    diamDim = sketch.sketchDimensions.addDiameterDimension( cornerHole, textPoint )
    diamDim.value = 0.196 * 2.54
    textPoint = cornerPoint.geometry
    horizDim = sketch.sketchDimensions.addDistanceDimension( 
        cornerHole.centerSketchPoint, cornerPoint, 
        adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation, textPoint )
    horizDim.value = 0.5 * 2.54
    textPoint = cornerPoint.geometry
    vertDim = sketch.sketchDimensions.addDistanceDimension( 
        cornerHole.centerSketchPoint, cornerPoint, 
        adsk.fusion.DimensionOrientations.VerticalDimensionOrientation, textPoint )
    if showPartialHoles :
        if offset < 0.5:
            vertDim.value = offset * 2.54
        else :
            vertDim.value = (offset - 0.5) * 2.54
    else:
        vertDim.value = offset * 2.54

    # Create the rectangular pattern
    rectPattern = sketch.geometricConstraints.createRectangularPatternInput( 
        [cornerHole], adsk.fusion.PatternDistanceType.SpacingPatternDistanceType )
    rectPattern.directionOneEntity = shortEdge
    rectPattern.directionTwoEntity = longEdge
    rectPattern.distanceOne = futil.Value( 0.5 )
    rectPattern.distanceTwo = futil.Value( 0.5 )
    rectPattern.quantityOne = futil.Value( int( (width / 0.5) - 0.5 ))
    if showPartialHoles :
        rectPattern.quantityTwo = futil.Value( int( (length / 0.5) + 1.5 ) )
    else:
        rectPattern.quantityTwo = futil.Value( int( (length / 0.5) - 0.5 ) )
    sketch.geometricConstraints.addRectangularPattern( rectPattern )

    # Extrude the holes through the tube
    circleProfileArea = sketch.profiles.item(0).areaProperties().area
    if circleProfileArea > sketch.profiles.item(1).areaProperties().area :
        circleProfileArea = sketch.profiles.item(1).areaProperties().area

    holeProfiles = adsk.core.ObjectCollection.create()
    for profile in sketch.profiles:
        if showPartialHoles:
            if profile.areaProperties().area - circleProfileArea < 0.001: 
                holeProfiles.add( profile )
        elif abs(profile.areaProperties().area - circleProfileArea) < 0.001:
            holeProfiles.add( profile )
    
    # futil.log( f'Found {len(holeProfiles)} hole profiles to extrude.')
    extrudes = workingComp.features.extrudeFeatures
    cutDistance = adsk.core.ValueInput.createByReal( cutDepth * 2.54 )
    extrudeCut = extrudes.createInput(holeProfiles, adsk.fusion.FeatureOperations.CutFeatureOperation)
    distance = adsk.fusion.DistanceExtentDefinition.create( cutDistance )
    extrudeCut.setOneSideExtent( distance, adsk.fusion.ExtentDirections.NegativeExtentDirection )
    extrudeCut.participantBodies = [ sideFaces.item(0).body ]
    extrudes.add( extrudeCut )
