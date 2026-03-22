import Foundation
import AVFoundation
import Vision
import CoreGraphics

struct OCRLine: Codable {
    let time: Double
    let text: String
    let minX: Double
    let minY: Double
    let maxX: Double
    let maxY: Double
    let confidence: Double
}

func usage() -> Never {
    fputs("usage: video_ocr_interval <video_path> <interval_seconds> <output_json>\n", stderr)
    exit(2)
}

let args = CommandLine.arguments
guard args.count == 4 else { usage() }

let videoPath = args[1]
guard let interval = Double(args[2]), interval > 0 else { usage() }
let outputPath = args[3]

let asset = AVURLAsset(url: URL(fileURLWithPath: videoPath))
let duration = CMTimeGetSeconds(asset.duration)
let times = stride(from: 0.0, through: max(0.0, duration - 0.1), by: interval).map { $0 }

let generator = AVAssetImageGenerator(asset: asset)
generator.appliesPreferredTrackTransform = true
generator.requestedTimeToleranceAfter = .zero
generator.requestedTimeToleranceBefore = .zero

func ocrLines(from image: CGImage, time: Double) throws -> [OCRLine] {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    request.recognitionLanguages = ["zh-Hans", "en-US"]

    let handler = VNImageRequestHandler(cgImage: image, options: [:])
    try handler.perform([request])

    guard let results = request.results else { return [] }
    return results.compactMap { obs in
        guard let candidate = obs.topCandidates(1).first else { return nil }
        let box = obs.boundingBox
        return OCRLine(
            time: time,
            text: candidate.string,
            minX: Double(box.minX),
            minY: Double(box.minY),
            maxX: Double(box.maxX),
            maxY: Double(box.maxY),
            confidence: Double(candidate.confidence)
        )
    }
}

var output: [OCRLine] = []
for (index, sec) in times.enumerated() {
    autoreleasepool {
        let cmTime = CMTime(seconds: sec, preferredTimescale: 600)
        do {
            let image = try generator.copyCGImage(at: cmTime, actualTime: nil)
            output.append(contentsOf: try ocrLines(from: image, time: sec))
        } catch {
            fputs("frame/OCR failed at \(sec): \(error)\n", stderr)
        }
    }

    if index == 0 || (index + 1).isMultiple(of: 100) || index == times.count - 1 {
        let progress = Double(index + 1) / Double(times.count) * 100.0
        fputs(String(format: "progress %.1f%% (%d/%d frames)\n", progress, index + 1, times.count), stderr)
        do {
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            let data = try encoder.encode(output)
            try data.write(to: URL(fileURLWithPath: outputPath))
        } catch {
            fputs("checkpoint write failed: \(error)\n", stderr)
        }
    }
}

let encoder = JSONEncoder()
encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
let data = try encoder.encode(output)
try data.write(to: URL(fileURLWithPath: outputPath))
