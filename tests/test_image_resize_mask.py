import importlib.util
import unittest
from pathlib import Path

import torch


spec = importlib.util.spec_from_file_location(
    "kktools_image_for_resize_test", Path(__file__).resolve().parents[1] / "nodes" / "image.py"
)
image_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(image_module)


class ResizeMaskTests(unittest.TestCase):
    def setUp(self):
        self.node = image_module.kkResize()

    def test_standard_comfy_mask_batch_is_resized_and_preserves_values(self):
        image = torch.zeros((2, 32, 48, 3))
        mask = torch.zeros((2, 32, 48))
        mask[1, :, :] = 1

        result_image, result_mask = self.node.resize_both(
            image, 96, 64, "stretch", "nearest", mask
        )

        self.assertEqual(tuple(result_image.shape), (2, 64, 96, 3))
        self.assertEqual(tuple(result_mask.shape), (2, 64, 96))
        self.assertEqual(result_mask[0].max().item(), 0)
        self.assertEqual(result_mask[1].min().item(), 1)

    def test_legacy_mask_shapes_and_no_mask_use_standard_output_shape(self):
        image = torch.zeros((1, 32, 48, 3))
        for mask in (torch.ones((32, 48)), torch.ones((1, 32, 48, 1)),
                     torch.ones((1, 1, 32, 48)), None):
            with self.subTest(shape=None if mask is None else tuple(mask.shape)):
                result_image, result_mask = self.node.resize_both(
                    image, 96, 64, "scale_height", "nearest", mask
                )
                self.assertEqual(tuple(result_mask.shape), tuple(result_image.shape[:3]))
                self.assertEqual(result_mask.max().item(), 0 if mask is None else 1)


if __name__ == "__main__":
    unittest.main()
