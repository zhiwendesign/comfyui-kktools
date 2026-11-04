import base64
import importlib.util
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import torch
from PIL import Image


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
    def test_input_types_pair_images_and_masks_by_index(self):
        module = load_kcanvas()
        optional_names = list(module.kcanvas.INPUT_TYPES()["optional"])
        expected = [name for index in range(1, 10) for name in (f"image{index}", f"mask{index}")]
        self.assertEqual(optional_names, expected)

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

    def test_mask_adds_alpha_to_image1_data_url(self):
        module = load_kcanvas()
        image = torch.ones((1, 2, 2, 3), dtype=torch.float32)
        mask = torch.tensor([[[0.0, 1.0], [0.5, 0.0]]], dtype=torch.float32)
        data_url = module.image_to_data_url(image, mask=mask)
        png = base64.b64decode(data_url.split(",", 1)[1])
        with Image.open(io.BytesIO(png)) as rendered:
            alpha = np.asarray(rendered.convert("RGBA"))[:, :, 3]
        np.testing.assert_array_equal(alpha, np.array([[0, 255], [128, 0]], dtype=np.uint8))

    def test_rgba_image_keeps_embedded_alpha_when_mask_is_also_connected(self):
        module = load_kcanvas()
        image = torch.ones((1, 1, 3, 4), dtype=torch.float32)
        image[:, :, :, 3] = torch.tensor([0.0, 0.5, 1.0])
        duplicate_mask = torch.tensor([[[0.0, 0.5, 1.0]]], dtype=torch.float32)
        data_url = module.image_to_data_url(image, mask=duplicate_mask)
        png = base64.b64decode(data_url.split(",", 1)[1])
        with Image.open(io.BytesIO(png)) as rendered:
            alpha = np.asarray(rendered.convert("RGBA"))[:, :, 3]
        np.testing.assert_array_equal(alpha, np.array([[0, 128, 255]], dtype=np.uint8))

    def test_each_mask_applies_to_the_image_with_the_same_index(self):
        module = load_kcanvas()
        image1 = torch.ones((1, 1, 2, 3), dtype=torch.float32)
        image2 = torch.ones((1, 1, 2, 3), dtype=torch.float32)
        mask1 = torch.tensor([[[0.0, 1.0]]], dtype=torch.float32)
        mask2 = torch.tensor([[[1.0, 0.0]]], dtype=torch.float32)
        values = module.template_values(
            "",
            [image1, image2, *([None] * 7)],
            0,
            masks=[mask1, mask2],
        )

        def alpha(data_url):
            png = base64.b64decode(data_url.split(",", 1)[1])
            with Image.open(io.BytesIO(png)) as rendered:
                return np.asarray(rendered.convert("RGBA"))[:, :, 3]

        np.testing.assert_array_equal(alpha(values["image1"]), np.array([[0, 255]], dtype=np.uint8))
        np.testing.assert_array_equal(alpha(values["image2"]), np.array([[255, 0]], dtype=np.uint8))

    def test_mask_batch_controls_render_batch_size(self):
        module = load_kcanvas()
        image = torch.ones((1, 2, 2, 3), dtype=torch.float32)
        mask = torch.stack((torch.zeros((2, 2)), torch.ones((2, 2))))
        fake_output = torch.zeros((1, 2, 2, 3), dtype=torch.float32)
        with mock.patch.object(module, "render_document", return_value=fake_output) as render_document:
            output = module.kcanvas().render("<div>${image1}</div>", image1=image, mask=mask)[0]
        self.assertEqual(render_document.call_count, 2)
        self.assertEqual(tuple(output.shape), (2, 2, 2, 3))

    def test_mask2_batch_controls_render_batch_size_for_image2(self):
        module = load_kcanvas()
        image2 = torch.ones((1, 2, 2, 3), dtype=torch.float32)
        mask2 = torch.stack((torch.zeros((2, 2)), torch.ones((2, 2))))
        fake_output = torch.zeros((1, 2, 2, 3), dtype=torch.float32)
        with mock.patch.object(module, "render_document", return_value=fake_output) as render_document:
            output = module.kcanvas().render("<div></div>", image2=image2, mask2=mask2)[0]
        self.assertEqual(render_document.call_count, 2)
        self.assertEqual(tuple(output.shape), (2, 2, 2, 3))

    def test_mask_without_matching_image_does_not_expand_batch(self):
        module = load_kcanvas()
        mask2 = torch.stack((torch.zeros((2, 2)), torch.ones((2, 2))))
        fake_output = torch.zeros((1, 2, 2, 3), dtype=torch.float32)
        with mock.patch.object(module, "render_document", return_value=fake_output) as render_document:
            output = module.kcanvas().render("<div></div>", mask2=mask2)[0]
        self.assertEqual(render_document.call_count, 1)
        self.assertEqual(tuple(output.shape), (1, 2, 2, 3))

    def test_render_document_with_local_browser(self):
        module = load_kcanvas()
        if not module.find_browser():
            self.skipTest("Chrome or Edge is not installed")
        document, width, height = module.prepare_document('<div style="width:48px;height:32px;background:#ff0000"></div>')
        image = module.render_document(document, width, height)
        self.assertEqual(tuple(image.shape), (1, 32, 48, 3))
        self.assertGreater(float(image[0, 0, 0, 0]), 0.9)

    def test_mask_renders_image1_as_transparent_layer(self):
        module = load_kcanvas()
        if not module.find_browser():
            self.skipTest("Chrome or Edge is not installed")
        image = torch.zeros((1, 10, 20, 3), dtype=torch.float32)
        image[:, :, :, 0] = 1.0
        mask = torch.ones((1, 10, 20), dtype=torch.float32)
        mask[:, :, 10:] = 0.0
        html = (
            '<div style="width:20px;height:10px;background:#00ff00">'
            '<img src="${image1}" style="display:block;width:20px;height:10px">'
            "</div>"
        )
        values = module.template_values(html, [image, *([None] * 8)], 0, mask)
        document, width, height = module.prepare_document(module.replace_placeholders(html, values))
        rendered = module.render_document(document, width, height)
        self.assertGreater(float(rendered[0, 5, 5, 0]), 0.9)
        self.assertGreater(float(rendered[0, 5, 15, 1]), 0.9)


if __name__ == "__main__":
    unittest.main()
