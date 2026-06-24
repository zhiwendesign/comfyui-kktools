import importlib.util
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class ImagenStudioIntegrationTests(unittest.TestCase):
    def test_runtime_paths_are_inside_kktools(self):
        nodes = load_module("imagen_studio", ROOT / "nodes" / "imagen_studio.py")
        self.assertEqual(nodes.imagen_studio_data_dir(), ROOT / "imagen-studio")
        self.assertEqual(nodes.template_library_dir(), ROOT / "imagen-studio" / "templates")
        self.assertEqual(
            nodes.local_node_config_candidates(ROOT / "nodes" / "imagen_studio.py"),
            [ROOT / "imagen-studio" / "config.json", ROOT / "imagen-studio" / "data" / "config.json"],
        )

    def test_runninghub_payload_always_includes_quality(self):
        nodes = load_module("imagen_studio", ROOT / "nodes" / "imagen_studio.py")
        submit_path, payload, meta = nodes.build_runninghub_submit_request(
            prompt="prompt",
            aspect_ratio="16:9",
            resolution="1k",
            channel="官方渠道",
            quality="",
        )
        self.assertEqual(submit_path, "/rhart-image-g-2-official/text-to-image")
        self.assertEqual(payload["quality"], "medium")
        self.assertEqual(meta["quality"], "medium")

    def test_runninghub_node_allows_manual_prompt_without_pipe(self):
        nodes = load_module("imagen_studio", ROOT / "nodes" / "imagen_studio.py")
        input_types = nodes.ImagenStudioRunningHubRHArtG2.INPUT_TYPES()
        self.assertNotIn("模板束", input_types["required"])
        self.assertIn("模板束", input_types["optional"])
        self.assertIn("正向提示词", input_types["optional"])

        old_run = nodes.run_runninghub_rhart_g2
        calls = []

        def fake_run(**kwargs):
            calls.append(kwargs)
            return {
                "image": "IMAGE",
                "output_url": "https://example.com/out.png",
                "task_id": "task-1",
                "result_json": json.dumps({
                    "channel": kwargs["channel"],
                    "mode": "text-to-image",
                    "submit_path": "/rhart-image-g-2/text-to-image",
                    "quality": kwargs["quality"],
                }),
            }

        nodes.run_runninghub_rhart_g2 = fake_run
        try:
            result = nodes.run_runninghub_pipe(
                template_pipe=None,
                prompt_override="manual prompt",
                aspect_ratio="16:9",
                resolution="1k",
                channel="第三方低价渠道",
                quality="high",
            )
        finally:
            nodes.run_runninghub_rhart_g2 = old_run

        self.assertEqual(calls[0]["prompt"], "manual prompt")
        self.assertEqual(result["pipe"]["prompt"], "manual prompt")
        self.assertEqual(result["pipe"]["task_id"], "task-1")
        self.assertEqual(result["output_url"], "https://example.com/out.png")

    def test_runninghub_pipe_uses_pipe_prompt_and_manual_override(self):
        nodes = load_module("imagen_studio", ROOT / "nodes" / "imagen_studio.py")
        old_run = nodes.run_runninghub_rhart_g2
        calls = []

        def fake_run(**kwargs):
            calls.append(kwargs)
            return {
                "image": "IMAGE",
                "output_url": "https://example.com/out.png",
                "task_id": "task-1",
                "result_json": "{}",
            }

        nodes.run_runninghub_rhart_g2 = fake_run
        try:
            pipe = {"pipe_type": "IMAGEN_STUDIO_PIPE", "template_name": "T", "prompt": "pipe prompt"}
            nodes.run_runninghub_pipe(template_pipe=pipe, prompt_override="", quality="medium")
            nodes.run_runninghub_pipe(template_pipe=pipe, prompt_override="override prompt", quality="medium")
        finally:
            nodes.run_runninghub_rhart_g2 = old_run

        self.assertEqual(calls[0]["prompt"], "pipe prompt")
        self.assertEqual(calls[1]["prompt"], "override prompt")

    def test_runninghub_pipe_requires_some_prompt(self):
        nodes = load_module("imagen_studio", ROOT / "nodes" / "imagen_studio.py")
        with self.assertRaises(Exception) as cm:
            nodes.run_runninghub_pipe(template_pipe=None, prompt_override="")
        self.assertIn("请输入正向提示词", str(cm.exception))

    def test_frontend_selector_keeps_dynamic_layout(self):
        text = (ROOT / "web" / "template_selector.js").read_text(encoding="utf-8")
        self.assertIn('new Set(["ImagenStudioTemplateSelector"])', text)
        self.assertNotIn("max-height: 340px", text)
        self.assertNotIn("getMaxHeight: () => 420", text)
        self.assertIn("function syncLayout()", text)
        self.assertIn("ResizeObserver", text)

    def test_imagen_theme_registers_pipe_colors_and_node_themes(self):
        text = (ROOT / "web" / "imagen_theme.js").read_text(encoding="utf-8")
        self.assertIn("IMAGEN_STUDIO_PIPE", text)
        self.assertIn("IMAGEN_PPT_PIPE", text)
        self.assertIn("#7737AA", text)
        self.assertIn("default_connection_color_byType", text)
        self.assertIn("link_type_colors", text)
        self.assertIn("ImagenStudioPPT", text)
        self.assertIn("kkimage2_灵思API", text)

    def test_kktools_loader_registers_imagen_studio_nodes(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            module = load_module("kktools_integrated_test", ROOT / "__init__.py")
        self.assertIn("ImagenStudioTemplateSelector", module.NODE_CLASS_MAPPINGS)
        self.assertIn("ImagenStudioRunningHubRHArtG2", module.NODE_CLASS_MAPPINGS)
        self.assertEqual(
            module.NODE_DISPLAY_NAME_MAPPINGS["ImagenStudioTemplateSelector"],
            "Imagen Studio 模板选择器",
        )


if __name__ == "__main__":
    unittest.main()
