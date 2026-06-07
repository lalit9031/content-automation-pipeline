import Vision
import Foundation
import CoreGraphics
import ImageIO

let url = URL(fileURLWithPath: "/Users/lalitprasadsingh/Desktop/fresher_ai_world_folder/Test 15 images/image_768def50.png")
guard let imageSource = CGImageSourceCreateWithURL(url as CFURL, nil),
      let cgImage = CGImageSourceCreateImageAtIndex(imageSource, 0, nil) else {
    print("Failed to load image via ImageIO")
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
