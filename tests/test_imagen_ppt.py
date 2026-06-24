import contextlib
import importlib.util
import io
import sys
import unittest
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class ImagenPPTTests(unittest.TestCase):
    def load_ppt(self):
        return load_module("imagen_ppt_test", ROOT / "nodes" / "imagen_ppt.py")

    def test_parse_markdown_outline_blocks(self):
        ppt = self.load_ppt()
        outline = """# 年度复盘

## 增长概览

### 核心数据
| 指标 | 数值 |
| --- | --- |
| 收入增长 | 35% |
"""
        blocks = ppt.parse_outline_blocks(outline)
        self.assertEqual([item["role"] for item in blocks], ["cover", "section", "data"])
        self.assertEqual(blocks[0]["title"], "年度复盘")
        self.assertIn("收入增长", blocks[2]["text"])

    def test_outline_plan_matches_template_page_styles(self):
        ppt = self.load_ppt()
        template_pipe = {
            "template_id": "tpl-ppt",
            "template_name": "蓝色路演",
            "template": {
                "id": "tpl-ppt",
                "name": "蓝色路演",
                "category": "ppt",
                "pageStyles": [
                    {"id": "cover-style", "name": "封面", "role": "cover", "layoutDescription": "大标题居中"},
                    {"id": "data-style", "name": "数据页", "role": "data", "layoutDescription": "表格居中"},
                ],
            },
        }
        result = ppt.run_ppt_outline_plan(
            "# 发布会\n\n### 关键数据\n| 指标 | 数值 |\n| --- | --- |\n| 转化 | 28% |",
            "产品发布",
            template_pipe,
            "16:9",
            "中文",
            "generic-comfyui",
        )
        pages = result["pipe"]["pages"]
        self.assertEqual(pages[0]["pageStyleId"], "cover-style")
        self.assertEqual(pages[1]["role"], "data")
        self.assertEqual(pages[1]["pageStyleId"], "data-style")

    def test_ppt_pipe_rejects_secret_fields(self):
        ppt = self.load_ppt()
        pipe = ppt.make_ppt_pipe(title="安全 PPT", pages=[])
        self.assertFalse(ppt.pipe_contains_secret(pipe))
        with self.assertRaises(Exception):
            ppt.make_ppt_pipe(template={"name": "bad", "apiKey": "secret"})

    def test_runninghub_batch_passes_quality(self):
        ppt = self.load_ppt()
        old = ppt.studio.run_runninghub_rhart_g2
        calls = []

        def fake_runninghub(**kwargs):
            calls.append(kwargs)
            idx = len(calls)
            return {
                "image": np.zeros((1, 8, 8, 3), dtype=np.float32),
                "output_url": f"https://example.com/{idx}.png",
                "task_id": f"task-{idx}",
                "result_json": "{}",
            }

        ppt.studio.run_runninghub_rhart_g2 = fake_runninghub
        try:
            pipe = ppt.make_ppt_pipe(
                title="批量生图",
                aspect_ratio="16:9",
                pages=[
                    {"pageNo": 1, "title": "A", "prompt": "prompt a"},
                    {"pageNo": 2, "title": "B", "prompt": "prompt b"},
                ],
            )
            result = ppt.run_ppt_runninghub_batch(pipe, "官方渠道", "1k", "high", "", timeout_minutes=45, poll_interval_seconds=7)
        finally:
            ppt.studio.run_runninghub_rhart_g2 = old
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["quality"], "high")
        self.assertEqual(calls[0]["channel"], "官方渠道")
        self.assertEqual(calls[0]["timeout_seconds"], 2700.0)
        self.assertEqual(calls[0]["poll_interval"], 7.0)
        self.assertEqual(result["image"].shape[0], 2)
        self.assertEqual(result["pipe"]["pages"][1]["taskId"], "task-2")

    def test_build_image_deck_pptx(self):
        ppt = self.load_ppt()
        image = Image.fromarray(np.full((12, 16, 3), 220, dtype=np.uint8))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        data = ppt.build_image_deck_pptx(
            "测试 PPT",
            "16:9",
            [{"pageNo": 1, "title": "封面"}, {"pageNo": 2, "title": "正文"}],
            [buffer.getvalue(), buffer.getvalue()],
        )
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            names = set(zf.namelist())
        self.assertIn("ppt/slides/slide1.xml", names)
        self.assertIn("ppt/slides/slide2.xml", names)
        self.assertIn("ppt/media/image1.png", names)
        self.assertIn("ppt/media/image2.png", names)
        self.assertIn("ppt/notesSlides/notesSlide1.xml", names)
        self.assertIn("ppt/notesSlides/notesSlide2.xml", names)

    def test_kktools_loader_registers_ppt_nodes(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            module = load_module("kktools_ppt_integrated_test", ROOT / "__init__.py")
        self.assertIn("ImagenStudioPPTOutlinePlan", module.NODE_CLASS_MAPPINGS)
        self.assertIn("ImagenStudioPPTExport", module.NODE_CLASS_MAPPINGS)
        self.assertTrue(module.NODE_CLASS_MAPPINGS["ImagenStudioPPTExport"].OUTPUT_NODE)
        self.assertEqual(
            module.NODE_DISPLAY_NAME_MAPPINGS["ImagenStudioPPTOutlinePlan"],
            "Imagen Studio PPT 大纲规划",
        )


if __name__ == "__main__":
    unittest.main()
