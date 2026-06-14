# ZeroGPU Video Render Space

This Gradio Space is the ZeroGPU render backend for the current video studio.

What it does:
- Accepts a zipped episode package
- Reads `episode.json` plus scene stills from `clips/auto_2_5d/`
- Runs image-to-video generation inside `@spaces.GPU`
- Returns a zip containing rendered MP4 clips in the same folder layout

Deployment notes:
- Set the Space hardware to **ZeroGPU**
- Keep the API name as `/render_package`
- Point the Streamlit app to the Space with `HF_ZERO_GPU_SPACE_ID`

Expected input zip layout:
```text
episode.json
clips/auto_2_5d/scene_01.png
clips/auto_2_5d/scene_02.png
...
```

Expected output zip layout:
```text
clips/auto_2_5d/scene_01.mp4
clips/auto_2_5d/scene_02.mp4
...
```
