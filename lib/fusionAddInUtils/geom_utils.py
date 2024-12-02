#  

import math
import adsk.core

app = adsk.core.Application.get()
ui = app.userInterface

def toPoint2D( pt: adsk.core.Point3D ) -> adsk.core.Point2D :
    return adsk.core.Point2D.create( pt.x, pt.y )

def toPoint3D( pt: adsk.core.Point2D ) -> adsk.core.Point3D :
    return adsk.core.Point3D.create( pt.x, pt.y, 0 )

def addPoint2D( pt1: adsk.core.Point2D, pt2: adsk.core.Point2D ) -> adsk.core.Point2D :
    return adsk.core.Point2D.create( pt1.x + pt2.x, pt1.y + pt2.y )

def addPoint2D( pt1: adsk.core.Point2D, v2: adsk.core.Vector2D ) -> adsk.core.Point2D :
    return adsk.core.Point2D.create( pt1.x + v2.x, pt1.y + v2.y )

def multVector2D( v: adsk.core.Vector2D, val: float ) -> adsk.core.Vector2D :
    return adsk.core.Vector2D.create( v.x * val, v.y * val )

def lineNormal( line: adsk.core.Line2D ) -> adsk.core.Vector2D :
    # norm_x = line.endPoint.y - line.startPoint.y
    # norm_y = line.endPoint.x - line.startPoint.x
    # mag = math.hypot( norm_x, norm_y )

#    return adsk.core.Vector2D.create( norm_x / mag, norm_y / mag )
    return lineNormal( line.startPoint, line.endPoint )

def lineNormal( startPt: adsk.core.Point2D, endPt: adsk.core.Point2D ) -> adsk.core.Vector2D :
    norm_x = -(endPt.y - startPt.y)
    norm_y = endPt.x - startPt.x
    mag = math.hypot( norm_x, norm_y )

    return adsk.core.Vector2D.create( norm_x / mag, norm_y / mag )
