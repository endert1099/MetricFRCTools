import adsk.core
import adsk.fusion
import os
import math
import time
from ...lib import fusionAddInUtils as futil
from ... import config
app = adsk.core.Application.get()
ui = app.userInterface


# TODO *** Specify the command identity information. ***
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_LightenDialog'
CMD_NAME = 'Lighten'
CMD_Description = 'Lighten a solid by pocketing'

# Specify that the command will be promoted to the panel.
IS_PROMOTED = True

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []


# Class to hold lighten profile info
class LightenProfile:
    profile: adsk.fusion.Profile = None
    filletRadius: float = 0.0
    outerLoop: adsk.fusion.ProfileLoop = None
    centroid: adsk.core.Point3D = None
    area: float = 0.0

    def __init__(self, profile: adsk.fusion.Profile, radius: float ):
        self.profile = profile
        self.filletRadius = radius
        for loop in self.profile.profileLoops:
            if loop.isOuter:
                self.outerLoop = loop
                break
        
        self.centroid = self.profile.areaProperties().centroid
        self.area = self.profile.areaProperties().area


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

    # # Create the button command control in the UI.
    control = submenu.controls.addCommand(cmd_def)

    # # Specify if the command is promoted to the main toolbar. 
    # control.isPromoted = IS_PROMOTED

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

    global ui_handlers
    ui_handlers = []

# Function that is called when a user clicks the corresponding button in the UI.
# This defines the contents of the command dialog and connects to the command related events.
def command_created(args: adsk.core.CommandCreatedEventArgs):

    # General logging for debug.
    futil.log(f'{CMD_NAME} command Created Event')

    # https://help.autodesk.com/view/fusion360/ENU/?contextId=CommandInputs
    inputs = args.command.commandInputs

    # Create a solid selection input.
    solidSelection = inputs.addSelectionInput('solid_selection', 'Solid', 'Select the solid body to pocket')
    solidSelection.addSelectionFilter( "SolidBodies" )
    solidSelection.setSelectionLimits( 1, 1 )

    # Create a profile selection input.
    profileSelection = inputs.addSelectionInput('profile_selection', 'Profiles', 'Select the profiles to use for pocketing')
    profileSelection.addSelectionFilter( "Profiles" )
    profileSelection.setSelectionLimits( 1, 0 )

    # Create a pocket depth value input.
    defaultLengthUnits = "in"
    default_value = adsk.core.ValueInput.createByString('0.125')
    pocketDepth = inputs.addValueInput('pocket_depth', 'Pocket Depth', defaultLengthUnits, default_value)

    inputs.addBoolValueInput( "full_depth", "Through Body", True )

    # Create a corner radius value input.
    defaultLengthUnits = "in"
    default_value = adsk.core.ValueInput.createByString('0.125')
    cornerRadius = inputs.addValueInput('corner_radius', 'Corner Radius', defaultLengthUnits, default_value)

    # Connect to the events that are needed by this command.
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

    inputs = args.command.commandInputs
    solidSelection: adsk.core.SelectionCommandInput = inputs.itemById('solid_selection')
    profileSelection: adsk.core.SelectionCommandInput = inputs.itemById('profile_selection')
    pocketDepth: adsk.core.ValueCommandInput = inputs.itemById('pocket_depth')
    isFullDepth: adsk.core.BoolValueCommandInput = inputs.itemById( "full_depth" )
    cornerRadius: adsk.core.ValueCommandInput = inputs.itemById('corner_radius')

    workingComp = solidSelection.selection(0).entity.parentComponent
    sketch = workingComp.sketches.add( profileSelection.selection(0).entity )

    profiles: list[LightenProfile] = []
    i = 0
    while i < profileSelection.selectionCount:
        lightenProfile = LightenProfile( profileSelection.selection(i).entity, cornerRadius.value )
        profiles.append( lightenProfile )
        i += 1

    for profile in profiles:
        toolProfile = offsetProfile( sketch, profile )
        extrudeProfile( solidSelection.selection(0).entity, toolProfile )

# This event handler is called when the command needs to compute a new preview in the graphics window.
def command_preview(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Preview Event')

    command_execute( args )
    args.isValidResult = True

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

    # futil.log(f'{CMD_NAME} Command Validate Event')

    inputs = args.inputs

# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Destroy Event')

    global local_handlers
    local_handlers = []

def offsetProfilesTest( sketch: adsk.fusion.Sketch, faces: list[adsk.fusion.BRepFace], 
                    templates: list[adsk.fusion.ProfileCurves] ) -> list[adsk.fusion.Profile] :

    for profCurves in templates:
        offsetCurves = []
        for pcurve in profCurves:
            # Project the Template profile curves into this sketch
            projectObjs = sketch.project( pcurve.sketchEntity )
            projectObjs[0].isConstruction = True

            offsetCurves.append( projectObjs[0] )
        offset = adsk.core.ValueInput.createByReal( -0.125 * 2.54 )
        offsetInput = sketch.geometricConstraints.createOffsetInput( offsetCurves, offset )
        sketch.geometricConstraints.addOffset2( offsetInput )

def offsetProfiles_old( sketch: adsk.fusion.Sketch, faces: list[adsk.fusion.BRepFace], 
                    templates: list[adsk.fusion.ProfileCurves], radius: float ) -> list[adsk.fusion.Profile] :

    newLoops = []
    i = 0 
    startTime = time.time()
    while i < len(templates) :
        curves = templates[i]
        loop = []
        firstStartPt = None
        # futil.log(f'Before Reverses {i} :: ts = {time.time()}, delta = {time.time()-startTime}')
        # reverses = findReverses( faces[i], curves )
        j = 0
        # futil.log(f'Working of profile {i}, {len(curves)} curves :: ts = {time.time()}, delta = {time.time()-startTime}')
        startTime = time.time()
        while j < len(curves) :
            # futil.log(f'         Projecting curve {j} :: ts = {time.time()}, delta = {time.time()-startTime}')
            curve = curves[j]
            # projectObjs = sketch.project( curve.sketchEntity )
            # projCurve = projectObjs[0]
            # projCurve.isConstruction = True
            # futil.log(f'         Projected sketchEntity {j} :: ts = {time.time()}, delta = {time.time()-startTime}')
            # futil.log(f'Offsetting curve :: ts = {time.time()}')
            # futil.print_Curve3D(curve.geometry)
            if curve.geometry.objectType == adsk.core.Line3D.classType() :
                line: adsk.core.Line3D = curve.geometry
                sketchCurve = sketch.sketchCurves.sketchLines.addByTwoPoints( line.startPoint, line.endPoint )
                # sketch.geometricConstraints.addCollinear( sketchCurve, projCurve )
            elif curve.geometry.objectType == adsk.core.Arc3D.classType() :
                arc: adsk.core.Arc3D = curve.geometry
                sketchCurve = sketch.sketchCurves.sketchArcs.addByCenterStartEnd( arc.center, arc.startPoint, arc.endPoint )
                # sketch.geometricConstraints.addCoincident( sketchCurve.startSketchPoint, projCurve )
                # sketch.geometricConstraints.addCoincident( sketchCurve.endSketchPoint, projCurve )
                # sketch.geometricConstraints.addConcentric( sketchCurve, projCurve )
            else :
                futil.log(f'   ============ offsetProfiles() Unhandled curve type: {curve.geometry.objectType}')
            # startPtStr = futil.format_Point3D(sketchCurve.startSketchPoint.geometry)
            # endPtStr = futil.format_Point3D(sketchCurve.endSketchPoint.geometry)
            # futil.log(f'Working on curve from {startPtStr} to {endPtStr}')
            sketchCurve.isFixed = True
            sketchCurve.isConstruction = True

            # futil.log(f'         Added Contraints {j} :: ts = {time.time()}, delta = {time.time()-startTime}')
            # if not firstStartPt :
            #     if reverses[j] :
            #         firstStartPt = sketchCurve.endSketchPoint
            #         prevEndPt = sketchCurve.startSketchPoint
            #     else:
            #         firstStartPt = sketchCurve.startSketchPoint
            #         prevEndPt = sketchCurve.endSketchPoint
            # else:
            #     if reverses[j] :
            #         startPt = sketchCurve.endSketchPoint
            #         endPt = sketchCurve.startSketchPoint
            #     else:
            #         startPt = sketchCurve.startSketchPoint
            #         endPt = sketchCurve.endSketchPoint

            #     # futil.log(f'Making coincident {futil.format_Point3D(startPt.geometry)}, {futil.format_Point3D(prevEndPt.geometry)}')
            #     # sketch.geometricConstraints.addCoincident( startPt, prevEndPt )
            #     prevEndPt = endPt

            loop.append( sketchCurve )
            j += 1

        # futil.log(f'Done projecting curves :: ts = {time.time()}, delta = {time.time()-startTime}')
        # sketch.geometricConstraints.addCoincident( firstStartPt, prevEndPt )
        offset = adsk.core.ValueInput.createByReal( 0.125 * 2.54 )
        offsetInput = sketch.geometricConstraints.createOffsetInput( loop, offset )
        offsetInput.isTopologyMatched = False
        # futil.log(f'Before Offset {i} :: ts = {time.time()}, delta = {time.time()-startTime}')
        offsetConstr = sketch.geometricConstraints.addOffset2( offsetInput )
        # futil.log(f'After Offset {i} :: ts = {time.time()}, delta = {time.time()-startTime}')
        offsetLoop = sketch.findConnectedCurves( offsetConstr.childCurves[0] )
        futil.log(f'Found {len(offsetLoop)} Offset curves')
        newLoops.append( offsetLoop )
        i += 1

    loopRadii = []
    for loop in newLoops:
        loopRadii.append( findCurvesMaximumRadius( loop ) )
    for loop in newLoops:
        filletConnectedCurve( loop, loopRadii, radius )
    
    futil.log(f'Done :: filleting time = {(time.time()-startTime):.5}s')

    return

def offsetProfile( sketch: adsk.fusion.Sketch, profile: LightenProfile ) -> adsk.fusion.Profile :

    curves = profile.outerLoop.profileCurves
    loop = []
    # futil.log(f'Working of profile {i}, {len(curves)} curves :: ts = {time.time()}, delta = {time.time()-startTime}')
    startTime = time.time()
    for curve in curves :
        # futil.log(f'         Projected sketchEntity {j} :: ts = {time.time()}, delta = {time.time()-startTime}')
        # futil.log(f'Offsetting curve :: ts = {time.time()}')
        # futil.print_Curve3D(curve.geometry)
        if curve.geometry.objectType == adsk.core.Line3D.classType() :
            line: adsk.core.Line3D = curve.geometry
            sketchCurve = sketch.sketchCurves.sketchLines.addByTwoPoints( line.startPoint, line.endPoint )
            # sketch.geometricConstraints.addCollinear( sketchCurve, projCurve )
        elif curve.geometry.objectType == adsk.core.Arc3D.classType() :
            arc: adsk.core.Arc3D = curve.geometry
            sketchCurve = sketch.sketchCurves.sketchArcs.addByCenterStartEnd( arc.center, arc.startPoint, arc.endPoint )
            # sketch.geometricConstraints.addCoincident( sketchCurve.startSketchPoint, projCurve )
            # sketch.geometricConstraints.addCoincident( sketchCurve.endSketchPoint, projCurve )
            # sketch.geometricConstraints.addConcentric( sketchCurve, projCurve )
        else :
            futil.log(f'   ============ offsetProfiles() Unhandled curve type: {curve.geometry.objectType}')
        # startPtStr = futil.format_Point3D(sketchCurve.startSketchPoint.geometry)
        # endPtStr = futil.format_Point3D(sketchCurve.endSketchPoint.geometry)
        # futil.log(f'Working on curve from {startPtStr} to {endPtStr}')
        sketchCurve.isFixed = True
        sketchCurve.isConstruction = True

        loop.append( sketchCurve )

    # futil.log(f'Done projecting curves :: ts = {time.time()}, delta = {time.time()-startTime}')
    # sketch.geometricConstraints.addCoincident( firstStartPt, prevEndPt )
    offset = adsk.core.ValueInput.createByReal( 0.125 * 2.54 )
    offsetInput = sketch.geometricConstraints.createOffsetInput( loop, offset )
    offsetInput.isTopologyMatched = False
    # futil.log(f'Before Offset {i} :: ts = {time.time()}, delta = {time.time()-startTime}')
    offsetConstr = sketch.geometricConstraints.addOffset2( offsetInput )
    # futil.log(f'After Offset {i} :: ts = {time.time()}, delta = {time.time()-startTime}')
    offsetLoop = sketch.findConnectedCurves( offsetConstr.childCurves[0] )
    futil.log(f'Found {len(offsetLoop)} Offset curves')

    loopRadii = findCurvesMaximumRadii( profile, offsetLoop )
    filletConnectedCurve( offsetLoop, loopRadii, profile.filletRadius )
    
    futil.log(f'Done :: filleting time = {(time.time()-startTime):.5}s')

    return

def extrudeProfile( solid: adsk.fusion.BRepBody, tools: adsk.fusion.Profile ) :

    return

def findReverses( face: adsk.fusion.BRepFace, curves: adsk.fusion.ProfileCurves ) -> list[bool] :
    # Determine if the start point and end points need to be reversed for 
    # each curve in the list of ProfileCurves
    reverses: list[bool] = []
    for curve in curves :
        if curve.geometry.objectType == adsk.core.Line3D.classType() :
            reverses.append( False )
        elif curve.geometry.objectType == adsk.core.Arc3D.classType() :
            arc: adsk.core.Arc3D = curve.geometry
            if face.isPointOnFace( arc.center ) :
                # futil.log(f'Arc center on face.  Not reversing')
                reverses.append( False )
            else:
                # futil.log(f'Arc center not on face.  Reversing')
                reverses.append( True )
        else :
            futil.log(f'   ============ findReverses() Unhandled curve type: {curve.geometry.objectType}')
            reverses.append( False )

    return reverses

def constrainOffsetEntity( proj: adsk.fusion.SketchCurve, offset: adsk.fusion.SketchCurve, reverse: bool ) :
    sketch = proj.parentSketch

    if proj.objectType == adsk.fusion.SketchLine.classType() :
        proj: adsk.fusion.SketchLine = proj

        sketch.geometricConstraints.addParallel( proj, offset )

        midpt = futil.make_Midpt( proj )
        offsetDim = sketch.sketchDimensions.addOffsetDimension( proj, offset, midpt )
        offsetDim.value = 0.125 * 2.54
    elif proj.objectType == adsk.fusion.SketchArc.classType() :
        proj: adsk.fusion.SketchArc = proj

        sketch.geometricConstraints.addCoincident( proj.centerSketchPoint, offset.centerSketchPoint )
        sketch.geometricConstraints.addCollinear( proj.centerSketchPoint, offset.centerSketchPoint )

    else :
        futil.log(f'   ============ constrainOffsetEntity() Unhandled curve type: {proj.objectType}')


def filletConnectedCurve( rawloop: adsk.core.ObjectCollection, loopRadii: list[float], radius: float ) :

    # Trim off all curve segments that are too short for the fillet radius
    loop = []
    i = 0
    while i < len(rawloop):
        if loopRadii[i] > radius :
            loop.append( rawloop[i] )
        i += 1

    i = 0
    while i < len(loop) - 1:
        filletBetweenTwoCurves( loop[i], loop[i+1], radius )
        i += 1

    filletBetweenTwoCurves( loop[ len(loop)-1 ], loop[0], radius )


def filletBetweenTwoCurves( curve1: adsk.fusion.SketchCurve, curve2: adsk.fusion.SketchCurve, radius: float ) :
    sketch = curve1.parentSketch

    futil.log(f'Filleting between :::')
    futil.print_SketchCurve( curve1 )
    futil.print_SketchCurve( curve2 )
    if curve1.startSketchPoint == curve2.endSketchPoint :
        startPt = curve1.startSketchPoint.geometry
        endPt = curve2.endSketchPoint.geometry
    elif curve1.endSketchPoint == curve2.endSketchPoint :
        startPt = curve1.endSketchPoint.geometry
        endPt = curve2.endSketchPoint.geometry
    elif curve1.endSketchPoint == curve2.startSketchPoint :
        startPt = curve1.endSketchPoint.geometry
        endPt = curve2.startSketchPoint.geometry
    else :
        startPt = curve1.startSketchPoint.geometry
        endPt = curve2.startSketchPoint.geometry

    futil.log(f'Filleting with input pts {futil.format_Point3D(startPt)} and {futil.format_Point3D(endPt)}')
    try :
        sketch.sketchCurves.sketchArcs.addFillet( curve1, startPt, curve2, endPt, radius )
        None
    except Exception as e:
        futil.handle_error( e )

def trimShortSegments( loop: adsk.core.ObjectCollection, radius: float ) -> list[adsk.fusion.SketchCurve] :
    trimLoop = []

    i = 0
    while i < len(loop)-1 :
        maxRadius = findMaxRadius( loop[i], loop[i+1] )
        if maxRadius > radius:
            trimLoop.append( loop[i] )
        else:
            loop[i].deleteMe()
        i += 1

    maxRadius = findMaxRadius( loop[ len(loop)-1 ], trimLoop[0] )
    if maxRadius > radius:
        trimLoop.append( loop[len(loop)-1] )
    else:
        loop[len(loop)-1].deleteMe()        

    return trimLoop

def findMaxRadius( c1: adsk.fusion.SketchCurve, c2: adsk.fusion.SketchCurve ) -> float :

    futil.log(f' ==========   findMaxRadius()  ==========')
    futil.log(f'=========== Starting with Curves ===========')
    futil.print_Curve3D( c1.geometry )
    futil.print_Curve3D( c2.geometry )

    # Get correctly oreinted Curve3D objects
    [orientedC1, orientedC2] = orientAndLinearizeCurves( c1, c2 )
    futil.log(f'=========== Oriented Curves ===========')
    futil.print_Curve3D( orientedC1 )
    futil.print_Curve3D( orientedC2 )

    # Find the largest fillet radius that can be used between c1 and c2
    try:
        eval1: adsk.core.CurveEvaluator3D = orientedC1.evaluator
        eval2: adsk.core.CurveEvaluator3D = orientedC2.evaluator
    except Exception as e:
        futil.handle_error( e )
        eval1 = None

    if not eval1:
        return 10000

    [success, c1p0, c1p1] = eval1.getParameterExtents()
    [success, c2p0, c2p1] = eval2.getParameterExtents()

    # Get the midpoint
    [success, midPt1] = eval1.getPointAtParameter( (c1p0 + c1p1) / 2)    
    [success, midPt2] = eval2.getPointAtParameter( (c2p0 + c2p1) / 2)    
    if not success :
        return 10000

    # Get the tangent at the midpoint
    [success, tangent1] = eval1.getTangent( (c1p0 + c1p1) / 2)    
    [success, tangent2] = eval2.getTangent( (c2p0 + c2p1) / 2)    
    if not success :
        return 10000

    tangentLine1 = adsk.core.InfiniteLine3D.create( midPt1, tangent1 )
    tangentLine2 = adsk.core.InfiniteLine3D.create( midPt2, tangent2 )
    intersections = tangentLine1.intersectWithCurve( tangentLine2 )
    if len(intersections) == 0:
        futil.log(f'   *********  Cannot find intersection of tangent with c2  ********** ')
        return 10000

    intersecPt = intersections[0]
    x_dist = midPt1.distanceTo( intersecPt )
    two_beta = math.pi - tangent1.angleTo( tangent2 )

    futil.log(f'    tangent1 ={futil.format_Vector3D(tangent1)}, tangent2 = {futil.format_Vector3D(tangent2)}')
    futil.log(f'    midpt ={futil.format_Point3D(midPt1)}, intersectPt = {futil.format_Point3D(intersecPt)}')
    futil.log(f'    x_dist ={x_dist}, two_beta = {two_beta}, Max fillet radius = {x_dist * math.tan( two_beta / 2 )}')

    return x_dist * math.tan( two_beta / 2 )


def orientAndLinearizeCurves( c1: adsk.fusion.SketchCurve, c2: adsk.fusion.SketchCurve ) -> tuple[adsk.core.Curve3D, adsk.core.Curve3D] :
    c1StartPt: adsk.core.Point3D = c1.startSketchPoint.geometry
    c1EndPt: adsk.core.Point3D = c1.endSketchPoint.geometry
    c2StartPt: adsk.core.Point3D = c2.startSketchPoint.geometry
    c2EndPt: adsk.core.Point3D = c2.endSketchPoint.geometry
    if c1EndPt.isEqualTo( c2StartPt ):
        return [ LinearizeCurve3D(c1.geometry), LinearizeCurve3D(c2.geometry) ]
    elif c1EndPt.isEqualTo( c2EndPt ) :
        return [ LinearizeCurve3D(c1.geometry), LinearizeCurve3D(c2.geometry, True) ]
    elif c1StartPt.isEqualTo( c2StartPt ):
        return [ LinearizeCurve3D(c1.geometry, True), LinearizeCurve3D(c2.geometry) ]
    elif c1StartPt.isEqualTo( c2EndPt ):
        return [ LinearizeCurve3D(c1.geometry, True), LinearizeCurve3D(c2.geometry, True) ]
    else:
        futil.log(f' *****************  CANNOT FIND COMMON End Point!!!! ************* ')

def LinearizeCurve3D( curve: adsk.core.Curve3D, reverse: bool = False ) -> adsk.core.Curve3D :
    if curve.objectType == adsk.core.Line3D.classType() :
        curve: adsk.core.Line3D = curve
        if reverse :
            futil.log(f'Reversing Line3D....')
            return adsk.core.Line3D.create( curve.endPoint, curve.startPoint )
        else :
            return curve
    elif curve.objectType == adsk.core.Arc3D.classType() :
        curve: adsk.core.Arc3D = curve
        eval = curve.evaluator
        [success, p0, p1] = eval.getParameterExtents()
        [success, midPt] = eval.getPointAtParameter((p0 + p1) / 2)
        [success, tangent] = eval.getTangent( (p0 + p1) / 2)
        length = abs(curve.endAngle - curve.startAngle) * curve.radius
        startOffset = tangent.copy()
        startOffset.normalize()
        startOffset.scaleBy( -length/1.5 )
        startPt = midPt.copy()
        startPt.translateBy( startOffset )
        endOffset = tangent.copy()
        endOffset.normalize()
        endOffset.scaleBy( length/1.5 )
        endPt = midPt.copy()
        endPt.translateBy( endOffset )
        futil.log(f' ============= Linearize ARC3D ==========')
        futil.log(f'   center = {futil.format_Point3D(curve.center)}')
        futil.log(f'   length = {length}, tangent={futil.format_Vector3D(tangent)}, midpt={futil.format_Point3D(midPt)}')
        futil.log(f'   startOffset={futil.format_Vector3D(startOffset)}, endOffset={futil.format_Vector3D(endOffset)}')
        futil.log(f'   startPt={futil.format_Point3D(startPt)}, endPt={futil.format_Point3D(endPt)}')
        futil.log(f'   OrigStartPt={futil.format_Point3D(curve.startPoint)}, OrigEndPt={futil.format_Point3D(curve.endPoint)}')
        if reverse:
            futil.log(f'Reversing Arc3D....')
            return adsk.core.Line3D.create( endPt, startPt )
        else:
            return adsk.core.Line3D.create( startPt, endPt )
        


def findCurvesMaximumRadii( profile: LightenProfile, loop: adsk.core.ObjectCollection ) -> list[float] :

    sketch: adsk.fusion.Sketch = loop[0].parentSketch

    maxRadii = []
    i = 0
    while i < len(loop) :
        prev = i - 1
        if prev < 0 :
            prev = len(loop) - 1
        next = i + 1
        if next == len(loop):
            next = 0

        prevCurve: adsk.fusion.SketchCurve = loop[prev]
        curve: adsk.fusion.SketchCurve = loop[i]
        nextCurve: adsk.fusion.SketchCurve = loop[next]

        # Construct a circle tangent to all three curves
        circ = sketch.sketchCurves.sketchCircles.addByCenterRadius( profile.centroid, profile.filletRadius )
        try:
            sketch.geometricConstraints.addTangent( curve, circ )
            sketch.geometricConstraints.addTangent( prevCurve, circ )
            sketch.geometricConstraints.addTangent( nextCurve, circ )
        except Exception as e:
            futil.handle_error( e )

        if not circ.isFullyConstrained:
            maxRadii.append( 1000000 )
        else:
            maxRadii.append( circ.radius )

        try:
            circ.deleteMe()
        except:
            None

        i += 1

    return maxRadii