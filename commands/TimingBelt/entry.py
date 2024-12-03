import adsk.core
import adsk.fusion
import os
from ...lib import fusionAddInUtils as futil
from ... import config
app = adsk.core.Application.get()
ui = app.userInterface


# TODO *** Specify the command identity information. ***
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_cmdDialog'
CMD_NAME = 'Extrude Timing Belt'
CMD_Description = 'Extrude a Timing Belt from a pitch line or pitch circles'

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

    # Create a Sketch Curve selection input.
    pitchLineSelection = inputs.addSelectionInput('belt_pitch_line', 'Pitch Line', 'Select the belt pitch line')
    pitchLineSelection.addSelectionFilter( "SketchCurves" )
    pitchLineSelection.setSelectionLimits( 2, 4 )

    # Create a simple text box input.
    belt_type = inputs.addDropDownCommandInput('belt_type', 'Timing Belt Type', adsk.core.DropDownStyles.TextListDropDownStyle)
    belt_type.listItems.add('HTD 5mm Pitch', True, '')
    belt_type.listItems.add('GT2 3mm Pitch', False, '')

    # Create a value input field and set the default using 1 unit of the default length unit.
    defaultLengthUnits = "mm"
    default_value = adsk.core.ValueInput.createByString('9')
    inputs.addValueInput('belt_width', 'Belt Width', defaultLengthUnits, default_value)

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
    pitchLineSelection: adsk.core.SelectionCommandInput = inputs.itemById('belt_pitch_line')
    belt_width: adsk.core.ValueCommandInput = inputs.itemById('belt_width')
    belt_type: adsk.core.DropDownCommandInput = inputs.itemById('belt_type')
    futil.log(f'Selection count is {pitchLineSelection.selectionCount}...')

    userSelections = []
    i = 0 
    while i < pitchLineSelection.selectionCount:
        userSelections.append( pitchLineSelection.selection(i).entity )
        i += 1
    
    originalSketch: adsk.fusion.Sketch = pitchLineSelection.selection(0).entity.parentSketch

    # Create a new component to put the sketches and geometry into
    design = adsk.fusion.Design.cast(app.activeProduct)
    rootComp = design.rootComponent
    trans = adsk.core.Matrix3D.create()
    workingOcc = rootComp.occurrences.addNewComponent( trans )
    workingComp = workingOcc.component
    # Create a new sketch for the belt
    sketch = workingComp.sketches.add( originalSketch.referencePlane, workingOcc )

    if belt_type.selectedItem.index == 0:
        beltPitchLength = 5
        beltThickness = 0.174
    else:
        beltPitchLength = 3
        beltThickness = 0.126


    # Determine if two circles are selected or a pitch loop is selected
    curves = []
    pathCurves = adsk.core.ObjectCollection.create()
    if userSelections[0].objectType == adsk.fusion.SketchCircle.classType():
        i = 0
        while i < len(userSelections):
            newCurve = sketch.include( userSelections[i] )
            newCurve.item(0).isConstruction = True
            i += 1
        PitchLoop = createPitchLoopFromCircles( sketch )
        for curve in PitchLoop:
            pathCurves.add( curve.createForAssemblyContext(workingOcc))
            curves.append( curve )
    else :
        PitchLoop = originalSketch.findConnectedCurves( userSelections[0] )
        for curve in PitchLoop:
            newCurve = sketch.include( curve )
            newCurve.item(0).isConstruction = True
            pathCurves.add( curve )
            curves.append( newCurve.item(0) )

    curveLength = 0.0
    for curve in curves:
        curveLength += curve.length

    toothCount = int( (curveLength * 10 / beltPitchLength) + 0.5 )
    futil.log(f'Loop length is {curveLength} number of teeth is {toothCount}...')

    if beltPitchLength == 5:
        comp_name = f"Belt_HTD_5mm-{toothCount}Tx{int(belt_width.value*10)}mm"
    else:
        comp_name = f"Belt_GT2_3mm-{toothCount}Tx{int(belt_width.value*10)}mm"

    workingComp.name = comp_name


    # Create the Offsets for the belt thickness.
    half_belt_thickness = adsk.core.ValueInput.createByReal( beltThickness / 2 ) # half of thickness

    geoConstraints = sketch.geometricConstraints
    offsetInput = geoConstraints.createOffsetInput( curves, half_belt_thickness )
    geoConstraints.addTwoSidesOffset( offsetInput, True )

    maxArea = 0
    insideLoop = None
    i = 0
    while i < sketch.profiles.count:
        profile = sketch.profiles.item(i)
        if profile.areaProperties().area > maxArea:
            maxArea = profile.areaProperties().area
            insideLoop = profile.profileLoops.item(0)
        i += 1

    futil.log(f'Inside loop has {insideLoop.profileCurves.count} curves in it.')

    # Determin the inside curves and the centroid
    bbox = insideLoop.profileCurves.item(0).sketchEntity.boundingBox
    i = 0
    while i < insideLoop.profileCurves.count:
        curve = insideLoop.profileCurves.item(i).sketchEntity
        bbox.combine( curve.boundingBox )
        i += 1

    centroid = adsk.core.Point2D.create()
    centroid.x = (bbox.maxPoint.x + bbox.minPoint.x) / 2.0
    centroid.y = (bbox.maxPoint.y + bbox.minPoint.y) / 2.0
    lineCurve: adsk.fusion.SketchLine = None
    lineNormal = adsk.core.Point2D.create()
    i = 0
    while i < insideLoop.profileCurves.count:
        curve = insideLoop.profileCurves.item(i).sketchEntity
        futil.log(f'Found a curve of type {curve.objectType} from ({curve.startSketchPoint.geometry.x:.3},{curve.startSketchPoint.geometry.y:.3}) to (({curve.endSketchPoint.geometry.x:.3},{curve.endSketchPoint.geometry.y:.3})')
        if curve.objectType == adsk.fusion.SketchLine.classType():
            StartPt = curve.startSketchPoint.geometry
            EndPt = curve.endSketchPoint.geometry
            insideNormal = adsk.core.Point2D.create()
            insideNormal.x = -(EndPt.y - StartPt.y)
            insideNormal.y = (EndPt.x - StartPt.x)
            centroidVec = adsk.core.Point2D.create(EndPt.x, EndPt.y).vectorTo( centroid )
            angle = centroidVec.angleTo( insideNormal.asVector())
            futil.log(f'    Centroid to Normal angle={angle:.3}...')
            if( abs(angle) > 3.14159 / 2.0 ):
                futil.log(f'    Reversing Normal.')
                insideNormal.x *= -1.0
                insideNormal.y *= -1.0
            futil.log(f'    Checking Line from ({StartPt.x:.3},{StartPt.y:.3}) to ({EndPt.x:.3},{EndPt.y:.3}), Normal=({insideNormal.x:.3},{insideNormal.y:.3})...')
            if insideNormal.y > -0.000001 :
                lineCurve = curve
                lineNormal = insideNormal
                if insideNormal.y > abs(insideNormal.x):
                    # Line has a slope between -45 and +45 degrees
                    if lineCurve.endSketchPoint.geometry.x < lineCurve.startSketchPoint.geometry.x:
                        toothAnchorPoint = lineCurve.endSketchPoint
                    else:
                        toothAnchorPoint = lineCurve.startSketchPoint
                elif insideNormal.x > 0 :
                    # Line has a slope of -90 to -45
                    if lineCurve.endSketchPoint.geometry.y > lineCurve.startSketchPoint.geometry.y:
                        toothAnchorPoint = lineCurve.endSketchPoint
                    else:
                        toothAnchorPoint = lineCurve.startSketchPoint
                else:
                    # Line has a slope of 45 to 90
                    if lineCurve.endSketchPoint.geometry.y < lineCurve.startSketchPoint.geometry.y:
                        toothAnchorPoint = lineCurve.endSketchPoint
                    else:
                        toothAnchorPoint = lineCurve.startSketchPoint

                futil.log(f'    Using Line from ({StartPt.x:.3},{StartPt.y:.3}) to ({EndPt.x:.3},{EndPt.y:.3}), Normal=({insideNormal.x:.3},{insideNormal.y:.3})...')
                futil.log(f'     toothAnchor =  ({toothAnchorPoint.geometry.x:.3},{toothAnchorPoint.geometry.y:.3}).')
        i += 1

    if beltPitchLength == 5:
        baseLine = createHTD_5mmProfile( sketch )
    else:
        baseLine = createGT2_3mmProfile( sketch )


    geoConstraints.addCoincident( baseLine.startSketchPoint, toothAnchorPoint )
    if abs( lineNormal.y ) < 0.0001:
        # Line is nearly vertical
        if lineNormal.x > 0:
            # Need to drop the baseline point by rotation
            length = baseLine.endSketchPoint.geometry.x - baseLine.startSketchPoint.geometry.x
            success = baseLine.endSketchPoint.move( adsk.core.Vector3D.create( -0.1339746*length, -0.5*length, 0 ) )
            success = baseLine.endSketchPoint.move( adsk.core.Vector3D.create( -length, -length, 0 ) )
            futil.log(f'     Dropping baseLine point returned {success}....')
        else:
            # Need to raise the baseline point by rotation
            length = baseLine.endSketchPoint.geometry.x - baseLine.startSketchPoint.geometry.x
            success = baseLine.endSketchPoint.move( adsk.core.Vector3D.create( -0.1339746*length, 0.5*length, 0 ) )
            success = baseLine.endSketchPoint.move( adsk.core.Vector3D.create( -length, length, 0 ) )
            futil.log(f'     Raising baseLine of length {length} returned {success}....')

    geoConstraints.addCollinear( baseLine, lineCurve )


    # Determine the profiles of the belt and tooth
    maxArea = 0
    minArea = 9999999
    insideLoop = None
    i = 0
    while i < sketch.profiles.count:
        profile = sketch.profiles.item(i)
        if profile.areaProperties().area > maxArea:
            maxArea = profile.areaProperties().area
            insideLoop = profile.profileLoops.item(0)
        if profile.areaProperties().area < minArea:
            minArea = profile.areaProperties().area
        i += 1

    beltLoop = None
    profileLoop = None
    i = 0
    while i < sketch.profiles.count:
        profile = sketch.profiles.item(i)
        if profile.areaProperties().area > minArea and profile.areaProperties().area < maxArea:
            beltLoop = profile
        elif profile.areaProperties().area < maxArea:
            profileLoop = profile
        i += 1

    extrudes = workingComp.features.extrudeFeatures
    beltWidthValue = adsk.core.ValueInput.createByReal( belt_width.value )
    extrudeBelt = extrudes.addSimple(beltLoop, beltWidthValue, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    extrudeTooth = extrudes.addSimple(profileLoop, beltWidthValue, adsk.fusion.FeatureOperations.JoinFeatureOperation)


    pathPatterns = workingComp.features.pathPatternFeatures
    beltPitch = adsk.core.ValueInput.createByReal( beltPitchLength / 10.0 )
    toothCountVI = adsk.core.ValueInput.createByReal( toothCount )
    patternCollection = adsk.core.ObjectCollection.create()
    patternCollection.add( extrudeTooth )
    
#    pathCurves = sketch.findConnectedCurves( originalConnectedCurves.item(0) )
#    futil.print_SketchObjectCollection( pathCurves )
    patternPath = adsk.fusion.Path.create( pathCurves, adsk.fusion.ChainedCurveOptions.noChainedCurves )
#    patternPath = adsk.fusion.Path.create( originalConnectedCurves.item(0), adsk.fusion.ChainedCurveOptions.connectedChainedCurves )
    toothPatternInput = pathPatterns.createInput( 
        patternCollection, patternPath, toothCountVI, beltPitch, adsk.fusion.PatternDistanceType.SpacingPatternDistanceType )
    toothPatternInput.isOrientationAlongPath = True
    toothPatternInput.patternComputeOption = adsk.fusion.PatternComputeOptions.IdenticalPatternCompute
    toothPattern = pathPatterns.add( toothPatternInput )


# This event handler is called when the command needs to compute a new preview in the graphics window.
def command_preview(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Preview Event')
    inputs = args.command.commandInputs


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

    inputs = args.inputs

    pitchLineSelection: adsk.core.SelectionCommandInput = inputs.itemById('belt_pitch_line')
    
    parentSketch: adsk.fusion.Sketch = pitchLineSelection.selection(0).entity.parentSketch
    connectedCurves = parentSketch.findConnectedCurves( pitchLineSelection.selection(0).entity )
            
    if connectedCurves.count > pitchLineSelection.selectionCount:
        pitchLineSelection.clearSelection()
        for curve in connectedCurves:
            pitchLineSelection.addSelection( curve )

    inputs = args.inputs
    
    # Verify the validity of the input values. This controls if the OK button is enabled or not.
    valueInput = inputs.itemById('belt_width')

    futil.log(f'{CMD_NAME} Validate:: num selected = {pitchLineSelection.selectionCount}')

    if valueInput.value >= 0 and ((pitchLineSelection.selectionCount == 2) or (pitchLineSelection.selectionCount == 4)):
        args.areInputsValid = True
    else:
        args.areInputsValid = False
        

# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Destroy Event')

    global local_handlers
    local_handlers = []


# Create the HTD 5mm tooth profile.
def createHTD_5mmProfile( sketch: adsk.fusion.Sketch ):
    geoConstraints = sketch.geometricConstraints
    sketchCurves = sketch.sketchCurves
    sketchDims = sketch.sketchDimensions

    baseLineLength = 0.385373
    filletRadius = 0.043
    toothBumpRadius = 0.15
    toothBumpOffset = 0.054
    filletSweepAngle = 1.6284  # 93.3 degrees
    toothBumpSweepAngle = -3.25548  # 186.525 degrees

    # Create the tooth profile at the origin
    originPt = adsk.core.Point3D.create( 0, 0, 0)
    baseLine = sketchCurves.sketchLines.addByTwoPoints( 
        originPt, adsk.core.Point3D.create( baseLineLength, 0, 0) )
    arcEndLine = sketchCurves.sketchLines.addByTwoPoints( 
        baseLine.startSketchPoint, adsk.core.Point3D.create( 0, filletRadius, 0) )
    arcEndLine.isConstruction = True
    geoConstraints.addPerpendicular( arcEndLine, baseLine )
    textPoint = adsk.core.Point3D.create(-0.01, 0.02, 0)
    linearDim = sketchDims.addDistanceDimension(arcEndLine.startSketchPoint, arcEndLine.endSketchPoint, 
                                                       adsk.fusion.DimensionOrientations.AlignedDimensionOrientation,
                                                       textPoint )
    linearDim.value = filletRadius

    toothline = sketchCurves.sketchLines.addByTwoPoints( 
        adsk.core.Point3D.create( baseLineLength/2, 0, 0), adsk.core.Point3D.create(  baseLineLength/2, toothBumpOffset, 0) )
    toothline.isConstruction = True
    geoConstraints.addPerpendicular( toothline, baseLine )
    geoConstraints.addCoincident( toothline.startSketchPoint, baseLine )
    textPoint = adsk.core.Point3D.create( baseLineLength/2, toothBumpOffset, 0)
    textPoint.translateBy( adsk.core.Vector3D.create( -0.02, 0, 0) )
    linearDim = sketchDims.addDistanceDimension(toothline.startSketchPoint, toothline.endSketchPoint, 
                                                       adsk.fusion.DimensionOrientations.AlignedDimensionOrientation,
                                                       textPoint )
    linearDim.value = toothBumpOffset

    firstFillet = sketchCurves.sketchArcs.addByCenterStartSweep( 
        arcEndLine.endSketchPoint, baseLine.startSketchPoint, filletSweepAngle )
    geoConstraints.addTangent( firstFillet, baseLine )
    geoConstraints.addCoincident( firstFillet.centerSketchPoint, arcEndLine.endSketchPoint )

    toothBump = sketchCurves.sketchArcs.addByCenterStartSweep( 
        toothline.endSketchPoint, firstFillet.endSketchPoint, toothBumpSweepAngle )
    geoConstraints.addCoincident(toothBump.centerSketchPoint, toothline.endSketchPoint )
    geoConstraints.addTangent(firstFillet, toothBump )
    textPoint = toothline.startSketchPoint.geometry.copy()
    textPoint.translateBy( adsk.core.Vector3D.create( -.05, .05, 0) )
    cirDim = sketchDims.addRadialDimension( toothBump, textPoint )
    cirDim.value = toothBumpRadius

    secondFillet = sketchCurves.sketchArcs.addByCenterStartSweep( 
        adsk.core.Point3D.create( baseLineLength, filletRadius, 0), toothBump.startSketchPoint, filletSweepAngle )
    geoConstraints.addCoincident( secondFillet.endSketchPoint, baseLine.endSketchPoint )
    geoConstraints.addTangent( secondFillet, baseLine )
    geoConstraints.addTangent( secondFillet, toothBump )

    textPoint = secondFillet.centerSketchPoint.geometry.copy()
    textPoint.translateBy( adsk.core.Vector3D.create( .05, .05, 0) )
    arcDim = sketchDims.addRadialDimension( secondFillet, textPoint )
    arcDim.value = filletRadius

    return baseLine

# Create the GT2 3mm tooth profile.
def createGT2_3mmProfile( parentSketch: adsk.fusion.Sketch ):
    geoConstraints = parentSketch.geometricConstraints

    baseLineLength = 0.2044505
    filletRadius = 0.035
    toothBumpRadius = 0.085
    toothBumpOffset = 0.025
    filletSweepAngle = 1.64322  # 94.14961 degrees
    toothBumpSweepAngle = -3.28806  # 188.3922 degrees

    # Create the tooth profile at the origin
    originPt = adsk.core.Point3D.create( 0, 0, 0)
    baseLine = parentSketch.sketchCurves.sketchLines.addByTwoPoints( 
        originPt, adsk.core.Point3D.create( baseLineLength, 0, 0) )
    arcEndLine = parentSketch.sketchCurves.sketchLines.addByTwoPoints( 
        baseLine.startSketchPoint, adsk.core.Point3D.create( 0, filletRadius, 0) )
    arcEndLine.isConstruction = True
    geoConstraints.addPerpendicular( arcEndLine, baseLine )
    textPoint = adsk.core.Point3D.create(-0.01, 0.02, 0)
    linearDim = parentSketch.sketchDimensions.addDistanceDimension(arcEndLine.startSketchPoint, arcEndLine.endSketchPoint, 
                                                       adsk.fusion.DimensionOrientations.AlignedDimensionOrientation,
                                                       textPoint )
    linearDim.value = filletRadius

    toothline = parentSketch.sketchCurves.sketchLines.addByTwoPoints( 
        adsk.core.Point3D.create( baseLineLength/2, 0, 0), adsk.core.Point3D.create(  baseLineLength/2, toothBumpOffset, 0) )
    toothline.isConstruction = True
    geoConstraints.addPerpendicular( toothline, baseLine )
    geoConstraints.addCoincident( toothline.startSketchPoint, baseLine )
    textPoint = adsk.core.Point3D.create( baseLineLength/2, toothBumpOffset, 0)
    textPoint.translateBy( adsk.core.Vector3D.create( -0.02, 0, 0) )
    linearDim = parentSketch.sketchDimensions.addDistanceDimension(toothline.startSketchPoint, toothline.endSketchPoint, 
                                                       adsk.fusion.DimensionOrientations.AlignedDimensionOrientation,
                                                       textPoint )
    linearDim.value = toothBumpOffset

    firstFillet = parentSketch.sketchCurves.sketchArcs.addByCenterStartSweep( 
        arcEndLine.endSketchPoint, baseLine.startSketchPoint, filletSweepAngle )
    geoConstraints.addTangent( firstFillet, baseLine )
    geoConstraints.addCoincident( firstFillet.centerSketchPoint, arcEndLine.endSketchPoint )

    toothBump = parentSketch.sketchCurves.sketchArcs.addByCenterStartSweep( 
        toothline.endSketchPoint, firstFillet.endSketchPoint, toothBumpSweepAngle )
    geoConstraints.addCoincident(toothBump.centerSketchPoint, toothline.endSketchPoint )
    geoConstraints.addTangent(firstFillet, toothBump )
    textPoint = toothline.startSketchPoint.geometry.copy()
    textPoint.translateBy( adsk.core.Vector3D.create( -.05, .05, 0) )
    cirDim = parentSketch.sketchDimensions.addRadialDimension( toothBump, textPoint )
    cirDim.value = toothBumpRadius

    secondFillet = parentSketch.sketchCurves.sketchArcs.addByCenterStartSweep( 
        adsk.core.Point3D.create( baseLineLength, filletRadius, 0), toothBump.startSketchPoint, filletSweepAngle )
    geoConstraints.addCoincident( secondFillet.endSketchPoint, baseLine.endSketchPoint )
    geoConstraints.addTangent( secondFillet, baseLine )
    geoConstraints.addTangent( secondFillet, toothBump )

    textPoint = secondFillet.centerSketchPoint.geometry.copy()
    textPoint.translateBy( adsk.core.Vector3D.create( .05, .05, 0) )
    arcDim = parentSketch.sketchDimensions.addRadialDimension( secondFillet, textPoint )
    arcDim.value = filletRadius

    return baseLine

def createPitchLoopFromCircles( sketch: adsk.fusion.Sketch ) :
    geoConstraints = sketch.geometricConstraints

    # Create the pitch line curves from two circles
    circle1: adsk.fusion.SketchCircle = sketch.sketchCurves.item(0)
    circle2: adsk.fusion.SketchCircle = sketch.sketchCurves.item(1)

    # centerline = sketch.sketchCurves.sketchLines.addByTwoPoints( circle1.centerSketchPoint, circle2.centerSketchPoint )
    # geoConstraints.addCoincident( centerline.startSketchPoint, circle1.centerSketchPoint )
    # geoConstraints.addCoincident( centerline.endSketchPoint, circle2.centerSketchPoint )
    # centerline.isConstruction = True
    CLstartPt = futil.toPoint2D( circle1.centerSketchPoint.geometry )
    CLendPt = futil.toPoint2D( circle2.centerSketchPoint.geometry )
    CLnormal = futil.lineNormal( CLstartPt, CLendPt )

    T1startPt = futil.addPoint2D( CLstartPt, futil.multVector2D( CLnormal, circle1.radius ) )
    T1endPt = futil.addPoint2D( CLendPt, futil.multVector2D( CLnormal, circle2.radius ) )
    tangentLine1 = sketch.sketchCurves.sketchLines.addByTwoPoints( futil.toPoint3D(T1startPt), futil.toPoint3D(T1endPt) )
    tangentLine1.isConstruction = True
    geoConstraints.addTangent( tangentLine1, circle1 )
    geoConstraints.addTangent( tangentLine1, circle2 )

    T2startPt = futil.addPoint2D( CLstartPt, futil.multVector2D( CLnormal, -circle1.radius ) )
    T2endPt = futil.addPoint2D( CLendPt, futil.multVector2D( CLnormal, -circle2.radius ) )
    tangentLine2 = sketch.sketchCurves.sketchLines.addByTwoPoints( futil.toPoint3D(T2startPt), futil.toPoint3D(T2endPt) )
    tangentLine2.isConstruction = True
    geoConstraints.addTangent( tangentLine2, circle1 )
    geoConstraints.addTangent( tangentLine2, circle2 )

    arc1 = sketch.sketchCurves.sketchArcs.addByCenterStartEnd( 
        circle1.centerSketchPoint, tangentLine1.startSketchPoint, tangentLine2.startSketchPoint )
    arc1.isConstruction = True
    geoConstraints.addConcentric( arc1, circle1 )
    geoConstraints.addTangent( arc1, tangentLine1 )

    arc2 = sketch.sketchCurves.sketchArcs.addByCenterStartEnd( 
        circle2.centerSketchPoint, tangentLine2.endSketchPoint, tangentLine1.endSketchPoint )
    arc2.isConstruction = True
    geoConstraints.addConcentric( arc2, circle2 )
    geoConstraints.addTangent( arc2, tangentLine2 )

    connectedCurves = sketch.findConnectedCurves( tangentLine1 )
    # curves = []
    # for curve in connectedCurves:
    #     curves.append( curve )

    return connectedCurves