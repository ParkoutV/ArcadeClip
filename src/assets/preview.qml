import QtQuick
import QtMultimedia

Rectangle {
    color: "#10141b"
    clip: true
    property alias videoSink: output.videoSink
    property real videoX: 0
    property real videoY: 0
    property real videoWidth: width
    property real videoHeight: height
    VideoOutput {
        id: output
        x: videoX
        y: videoY
        width: videoWidth
        height: videoHeight
        // The canvas computes the oriented source-pixel rectangle, shared with
        // normalized OCR regions. Do not apply a second aspect-ratio transform.
        fillMode: VideoOutput.Stretch
        endOfStreamPolicy: VideoOutput.KeepLastFrame
    }
}
