// Local macOS Vision OCR. Input images should contain only the game region.
import Foundation
import Vision
import ImageIO

struct TextLine: Codable {
    let text: String
    let confidence: Float
    let box: [Double] // normalized x, y from top, width, height
}
struct ImageResult: Codable {
    let path: String
    let lines: [TextLine]
}

do {
    var output: [ImageResult] = []
    let englishOnly = CommandLine.arguments.contains("--english")
    for path in CommandLine.arguments.dropFirst().filter({ $0 != "--english" }) {
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        let supported = try request.supportedRecognitionLanguages()
        request.recognitionLanguages = (englishOnly ? ["en-US"] : ["ko-KR", "en-US"]).filter { supported.contains($0) }
        let handler = VNImageRequestHandler(url: URL(fileURLWithPath: path), options: [:])
        try handler.perform([request])
        let lines = (request.results ?? []).compactMap { observation -> TextLine? in
            guard let candidate = observation.topCandidates(1).first else { return nil }
            let r = observation.boundingBox
            return TextLine(text: candidate.string, confidence: candidate.confidence,
                            box: [r.minX, 1 - r.maxY, r.width, r.height])
        }
        output.append(ImageResult(path: path, lines: lines))
    }
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    FileHandle.standardOutput.write(try encoder.encode(output))
    FileHandle.standardOutput.write(Data("\n".utf8))
} catch {
    FileHandle.standardError.write(Data("OCR failed: \(error)\n".utf8))
    exit(1)
}
