"""Native material matching design/surface-study.png."""
from AppKit import NSBezierPath, NSColor, NSGradient, NSMakeRect, NSView
from theme import SURFACE_TOP, SURFACE_BOTTOM, BORDER_RGBA, PANEL_TOP, PANEL_BOTTOM, PANEL_BORDER


def color(rgba):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(*(value / 255 for value in rgba))


def paint_glass(bounds, radius=18, flipped=False, opaque=False, outline=None,
                top=SURFACE_TOP, bottom=SURFACE_BOTTOM, border=BORDER_RGBA):
    rect = NSMakeRect(bounds.origin.x + 1, bounds.origin.y + 1, bounds.size.width - 2, bounds.size.height - 2)
    path = outline if outline is not None else NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, radius, radius)
    bottom = (*bottom[:3], 255) if opaque else bottom
    top = (*top[:3], 255) if opaque else top
    gradient = NSGradient.alloc().initWithStartingColor_endingColor_(color(bottom), color(top))
    gradient.drawInBezierPath_angle_(path, 270 if flipped else 90)
    color(border).setStroke()
    path.setLineWidth_(0.8)
    path.stroke()


class GlassView(NSView):
    def isFlipped(self):
        return True

    def drawRect_(self, _rect):
        paint_glass(self.bounds(), flipped=True, opaque=True,
                    top=PANEL_TOP, bottom=PANEL_BOTTOM, border=PANEL_BORDER)
