import Cocoa

// Usage: swift make_icon.swift <output.iconset directory>
// Draws the app icon at every size an .icns needs: a near-black squircle (the same tile as the
// logo in the app's sidebar) with a white download arrow over a tray that is partly filled green,
// echoing the progress bar.
let outDir = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
try FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)

func render(pixels: Int) -> Data {
    let rep = NSBitmapImageRep(
        bitmapDataPlanes: nil, pixelsWide: pixels, pixelsHigh: pixels, bitsPerSample: 8,
        samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
        bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    defer { NSGraphicsContext.restoreGraphicsState() }
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    let s = CGFloat(pixels)

    // macOS icon grid: the body fills ~80% of the canvas, leaving room for the shadow.
    let inset = s * 0.098
    let body = NSRect(x: inset, y: inset, width: s - inset * 2, height: s - inset * 2)
    let radius = body.width * 0.2237
    let shape = NSBezierPath(roundedRect: body, xRadius: radius, yRadius: radius)

    // Soft drop shadow under the tile.
    NSGraphicsContext.saveGraphicsState()
    let shadow = NSShadow()
    shadow.shadowColor = NSColor.black.withAlphaComponent(0.38)
    shadow.shadowBlurRadius = s * 0.022
    shadow.shadowOffset = NSSize(width: 0, height: -s * 0.012)
    shadow.set()
    NSColor(white: 0.1, alpha: 1).setFill()
    shape.fill()
    NSGraphicsContext.restoreGraphicsState()

    // Body: subtle vertical gradient, near-black.
    NSGradient(colors: [NSColor(white: 0.19, alpha: 1), NSColor(white: 0.07, alpha: 1)])!.draw(in: shape, angle: -90)

    // Light catching the top edge, plus a hairline rim.
    NSGraphicsContext.saveGraphicsState()
    shape.addClip()
    NSGradient(colors: [NSColor.white.withAlphaComponent(0.14), NSColor.white.withAlphaComponent(0)])!
        .draw(in: NSRect(x: body.minX, y: body.midY, width: body.width, height: body.height / 2), angle: -90)
    NSGraphicsContext.restoreGraphicsState()
    NSColor.white.withAlphaComponent(0.10).setStroke()
    shape.lineWidth = max(1, s * 0.002)
    shape.stroke()

    // Everything below is drawn in the body's own 0...1 space.
    func p(_ x: CGFloat, _ y: CGFloat) -> NSPoint {
        NSPoint(x: body.minX + body.width * x, y: body.minY + body.height * y)
    }
    let stroke = body.width * 0.075

    // Arrow.
    let arrow = NSBezierPath()
    arrow.lineWidth = stroke
    arrow.lineCapStyle = .round
    arrow.lineJoinStyle = .round
    arrow.move(to: p(0.5, 0.76))
    arrow.line(to: p(0.5, 0.41))
    arrow.move(to: p(0.355, 0.555))
    arrow.line(to: p(0.5, 0.41))
    arrow.line(to: p(0.645, 0.555))
    NSColor.white.setStroke()
    arrow.stroke()

    // Tray: a muted track with a green "progress" portion.
    let track = NSBezierPath()
    track.lineWidth = stroke
    track.lineCapStyle = .round
    track.move(to: p(0.27, 0.255))
    track.line(to: p(0.73, 0.255))
    NSColor.white.withAlphaComponent(0.22).setStroke()
    track.stroke()

    let fill = NSBezierPath()
    fill.lineWidth = stroke
    fill.lineCapStyle = .round
    fill.move(to: p(0.27, 0.255))
    fill.line(to: p(0.56, 0.255))
    NSColor(red: 0.20, green: 0.78, blue: 0.42, alpha: 1).setStroke()
    fill.stroke()

    return rep.representation(using: .png, properties: [:])!
}

for base in [16, 32, 128, 256, 512] {
    try render(pixels: base).write(to: outDir.appendingPathComponent("icon_\(base)x\(base).png"))
    try render(pixels: base * 2).write(to: outDir.appendingPathComponent("icon_\(base)x\(base)@2x.png"))
}
