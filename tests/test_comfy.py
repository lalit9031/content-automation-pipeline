import json
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from content_pipeline.config import Settings
from content_pipeline.bots.comfy_client import (
    ComfyUIClient,
    load_workflow_json,
    customize_txt2img_workflow
)
from content_pipeline.bots.image import ComfyUIImageProvider, ImageVariant


class TestComfyUIIntegration(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(
            output_dir=Path("./output"),
            comfyui_url="http://127.0.0.1:8188",
            comfyui_image_workflow="test_workflow.json",
            comfyui_model_name="test_model.safetensors",
            comfyui_timeout_seconds=10
        )

    def test_workflow_customization(self):
        # A mock ComfyUI workflow JSON
        mock_wf = {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": 12345,
                    "steps": 20
                }
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": 512,
                    "height": 512
                }
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": "old prompt"
                }
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": "negative prompt low quality"
                }
            },
            "8": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": "old_model.safetensors"
                }
            }
        }

        customized = customize_txt2img_workflow(
            workflow=mock_wf,
            prompt="A majestic blue dragon in the sky",
            width=1024,
            height=768,
            seed=99999,
            model_name="flux_dev.safetensors"
        )

        # Assertions
        self.assertEqual(customized["5"]["inputs"]["width"], 1024)
        self.assertEqual(customized["5"]["inputs"]["height"], 768)
        self.assertEqual(customized["6"]["inputs"]["text"], "A majestic blue dragon in the sky")
        # Negative prompt should remain unchanged
        self.assertEqual(customized["7"]["inputs"]["text"], "negative prompt low quality")
        self.assertEqual(customized["3"]["inputs"]["seed"], 99999)
        self.assertEqual(customized["8"]["inputs"]["ckpt_name"], "flux_dev.safetensors")

    @patch("urllib.request.urlopen")
    def test_client_generate(self, mock_urlopen):
        # Setup mocks for prompt POST and history GET
        mock_response_post = MagicMock()
        mock_response_post.__enter__.return_value = mock_response_post
        mock_response_post.read.return_value = json.dumps({"prompt_id": "job_12345"}).encode("utf-8")
        mock_response_post.headers = {"Content-Type": "application/json"}

        mock_response_history = MagicMock()
        mock_response_history.__enter__.return_value = mock_response_history
        mock_history_data = {
            "job_12345": {
                "outputs": {
                    "9": {
                        "images": [
                            {"filename": "out_0001.png", "subfolder": "", "type": "output"}
                        ]
                    }
                }
            }
        }
        mock_response_history.read.return_value = json.dumps(mock_history_data).encode("utf-8")
        mock_response_history.headers = {"Content-Type": "application/json"}

        mock_response_view = MagicMock()
        mock_response_view.__enter__.return_value = mock_response_view
        mock_response_view.read.return_value = b"fake_png_bytes"
        mock_response_view.headers = {"Content-Type": "image/png"}

        mock_urlopen.side_effect = [mock_response_post, mock_response_history, mock_response_view]

        client = ComfyUIClient(base_url="http://localhost:8188", timeout_seconds=5)
        results = client.generate({"test": "graph"})

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], b"fake_png_bytes")

    @patch("content_pipeline.bots.qa_auditor.QAVisualAuditor.audit_image")
    @patch("content_pipeline.bots.inpainting_editor.InpaintingEditor.repair_image")
    def test_multi_agent_qa_loop(self, mock_repair, mock_audit):
        from content_pipeline.bots.agent_orchestrator import AgentOrchestrator
        
        # Iteration 1: Audit fails with eye_damage defect
        # Iteration 2: Audit passes
        mock_audit.side_effect = [
            {"status": "FAIL", "reason": "damaged eye", "defect_type": "eye_damage", "bounding_box": [100, 100, 200, 200]},
            {"status": "PASS", "reason": "Fixed!", "defect_type": None, "bounding_box": None}
        ]
        
        mock_repair.return_value = b"repaired_image_bytes"
        
        orchestrator = AgentOrchestrator(self.settings, max_attempts=3)
        final_image = orchestrator.run_image_audit_repair_loop(b"initial_image_bytes", "some prompt")
        
        self.assertEqual(final_image, b"repaired_image_bytes")
        self.assertEqual(mock_audit.call_count, 2)
        mock_repair.assert_called_once_with(
            image_bytes=b"initial_image_bytes",
            bounding_box=[100, 100, 200, 200],
            defect_type="eye_damage",
            original_prompt="some prompt"
        )


if __name__ == "__main__":
    unittest.main()
