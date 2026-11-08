"""Native material matching design/surface-study.png."""
from AppKit import NSBezierPath, NSColor, NSGradient, NSMakeRect, NSView
from theme import SURFACE_TOP, SURFACE_BOTTOM, BORDER_RGBA


def color(rgba):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(*(value / 255 for value in rgba))


def paint_glass(bounds, radius=18, flipped=False):
    rect = NSMakeRect(bounds.origin.x + 1, bounds.origin.y + 1, bounds.size.width - 2, bounds.size.height - 2)
    path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, radius, radius)
    gradient = NSGradient.alloc().initWithStartingColor_endingColor_(color(SURFACE_BOTTOM), color(SURFACE_TOP))
    gradient.drawInBezierPath_angle_(path, 270 if flipped else 90)
    color(BORDER_RGBA).setStroke()
    path.setLineWidth_(0.8)
    path.stroke()


class GlassView(NSView):
    def isFlipped(self):
        return True

    def drawRect_(self, _rect):
        paint_glass(self.bounds(), flipped=True)
