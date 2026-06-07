
import Vision
import Foundation
import CoreGraphics
import ImageIO

let url = URL(fileURLWithPath: "/Users/lalitprasadsingh/Desktop/Screenshot 2026-06-01 at 12.15.15 AM.png")
guard let imageSource = CGImageSourceCreateWithURL(url as CFURL, nil),
      let cgImage = CGImageSourceCreateImageAtIndex(imageSource, 0, nil) else {
    print("Failed to load image")
    exit(1)
}

let requestHandler = VNImageRequestHandler(cgImage: cgImage, options: [:])
let request = VNRecognizeTextRequest { (request, error) in
    if let error = error {
        print("Error: \(error)")
        return
    }
    guard let observations = request.results as? [VNRecognizedTextObservation] else { return }
    for observation in observations {
        if let candidate = observation.topCandidates(1).first {
            print(candidate.string)
        }
    }
}
request.recognitionLevel = .accurate
try? requestHandler.perform([request])
