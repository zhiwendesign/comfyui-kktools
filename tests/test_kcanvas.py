import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np
import torch


ROOT = Path(__file__).resolve().parents[1]


def load_kcanvas():
    path = ROOT / "nodes" / "kcanvas.py"
    spec = importlib.util.spec_from_file_location("kcanvas_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["kcanvas_test"] = module
    spec.loader.exec_module(module)
    return module


class KCanvasTests(unittest.TestCase):
    def test_extract_canvas_size_prefers_pixel_styles(self):
        module = load_kcanvas()
        self.assertEqual(module.extract_canvas_size('<div style="width:640px;height:360px"></div>'), (640, 360))
        self.assertEqual(module.extract_canvas_size('<canvas width="320" height="180"></canvas>'), (320, 180))

    def test_template_values_use_variables_and_image_alias(self):
        module = load_kcanvas()
        image = np.zeros((1, 2, 3, 3), dtype=np.float32)
        html = "<script>const color = '#123456'; const texttitle = 'KCanvas';</script>${color} ${texttitle} ${img} ${image2}"
        images = [torch.from_numpy(image), *([None] * 8)]
        values = module.template_values(html, images, 0)
        resolved = module.replace_placeholders(html, values)
        self.assertIn("#123456 KCanvas data:image/png;base64,", resolved)
        self.assertNotIn("${image2}", resolved)
        self.assertEqual(values["img"], values["image1"])

    def test_render_document_with_local_browser(self):
        module = load_kcanvas()
        if not module.find_browser():
            self.skipTest("Chrome or Edge is not installed")
        document, width, height = module.prepare_document('<div style="width:48px;height:32px;background:#ff0000"></div>')
        image = module.render_document(document, width, height)
        self.assertEqual(tuple(image.shape), (1, 32, 48, 3))
        self.assertGreater(float(image[0, 0, 0, 0]), 0.9)


if __name__ == "__main__":
    unittest.main()
