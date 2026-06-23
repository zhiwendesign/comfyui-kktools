import importlib.util
import contextlib
import io
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

    def test_frontend_selector_keeps_dynamic_layout(self):
        text = (ROOT / "web" / "template_selector.js").read_text(encoding="utf-8")
        self.assertIn('new Set(["ImagenStudioTemplateSelector"])', text)
        self.assertNotIn("max-height: 340px", text)
        self.assertNotIn("getMaxHeight: () => 420", text)
        self.assertIn("function syncLayout()", text)
        self.assertIn("ResizeObserver", text)

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
