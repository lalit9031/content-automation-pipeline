import glob
import subprocess
from pathlib import Path

def main():
    screenshots = sorted(glob.glob('/Users/lalitprasadsingh/Desktop/Screenshot*.png'))
    for p in screenshots:
        print(f"=== OCR for: {p} ===")
        swift_code = f"""
import Vision
import Foundation
import CoreGraphics
import ImageIO

let url = URL(fileURLWithPath: "{p}")
guard let imageSource = CGImageSourceCreateWithURL(url as CFURL, nil),
      let cgImage = CGImageSourceCreateImageAtIndex(imageSource, 0, nil) else {{
    print("Failed to load image")
    exit(1)
}}

let requestHandler = VNImageRequestHandler(cgImage: cgImage, options: [:])
let request = VNRecognizeTextRequest {{ (request, error) in
    if let error = error {{
        print("Error: \\(error)")
        return
    }}
    guard let observations = request.results as? [VNRecognizedTextObservation] else {{ return }}
    for observation in observations {{
        if let candidate = observation.topCandidates(1).first {{
            print(candidate.string)
        }}
    }}
}}
request.recognitionLevel = .accurate
try? requestHandler.perform([request])
"""
        swift_path = Path("scratch/ocr_temp.swift")
        swift_path.write_text(swift_code, encoding="utf-8")
        
        res = subprocess.run(['swift', str(swift_path)], capture_output=True, text=True)
        print(res.stdout)
        print("======================\n")

if __name__ == "__main__":
    main()
