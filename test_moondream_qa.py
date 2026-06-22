import base64, json, urllib.request
from pathlib import Path

img = Path(r"C:\Users\user\Desktop\Output file\image\girl_in_rain_aligned.png").read_bytes()
img_b64 = base64.b64encode(img).decode("utf-8")

generation_prompt = "Pixar 3D animated cute girl with umbrella walking in rain toward river bank"

qa_prompt = (
    f"The image was generated from: '{generation_prompt}'. "
    "Does it match? Is the subject a girl (not a man)? "
    "Is it outdoors in rain? Any broken face or watermarks? "
    'Reply with ONLY JSON: {"status":"PASS","reason":null,"defect_type":null,"bounding_box":null} '
    'or {"status":"FAIL","reason":"what is wrong","defect_type":"wrong_subject","bounding_box":null}'
)

payload = {
    "model": "moondream",
    "prompt": qa_prompt,
    "images": [img_b64],
    "stream": False
}

req = urllib.request.Request(
    "http://localhost:11434/api/generate",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
    method="POST"
)

print("Sending image to Moondream for QA check...")
with urllib.request.urlopen(req, timeout=60) as r:
    resp = json.loads(r.read())
    print("Moondream QA response:")
    print(resp.get("response", ""))
