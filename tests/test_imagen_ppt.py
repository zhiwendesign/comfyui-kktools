import contextlib
import importlib.util
import io
import sys
import threading
import time
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

    def test_imagen_and_ppt_pipe_types_are_unified(self):
        ppt = self.load_ppt()
        self.assertEqual(ppt.IMAGEN_PPT_PIPE_TYPE, ppt.studio.IMAGEN_STUDIO_PIPE_TYPE)
        self.assertEqual(
            ppt.studio.ImagenStudioTemplateSelector.RETURN_TYPES[0],
            ppt.ImagenStudioPPTOutlinePlan.INPUT_TYPES()["optional"]["模板束"][0],
        )
        self.assertEqual(
            ppt.ImagenStudioPPTOutlinePlan.RETURN_TYPES[0],
            ppt.ImagenStudioPPTDesignBrief.INPUT_TYPES()["required"]["PPT束"][0],
        )

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
        self.assertEqual(result["pipe"]["pipe_type"], ppt.studio.IMAGEN_STUDIO_PIPE_TYPE)
        self.assertEqual(result["pipe"]["template_id"], "tpl-ppt")
        resolved = ppt.studio.resolve_template_pipe(result["pipe"], "")
        self.assertIn('"pageStyles"', resolved["template_json"])

    def test_ppt_pipe_rejects_secret_fields(self):
        ppt = self.load_ppt()
        pipe = ppt.make_ppt_pipe(title="安全 PPT", pages=[])
        self.assertFalse(ppt.pipe_contains_secret(pipe))
        with self.assertRaises(Exception):
            ppt.make_ppt_pipe(template={"name": "bad", "apiKey": "secret"})

    def test_ppt_design_requires_pages(self):
        ppt = self.load_ppt()
        pipe = ppt.make_ppt_pipe(title="空页面", pages=[])
        with self.assertRaises(Exception) as cm:
            ppt.run_ppt_design_brief(pipe, None, "")
        self.assertIn("没有页面", str(cm.exception))

    def test_page_compose_status_timeout_and_fallback(self):
        ppt = self.load_ppt()
        old_load_config = ppt.studio.load_config
        old_resolve = ppt.studio.resolve_task_config
        old_call_agent = ppt.studio.call_agent
        old_create_bar = ppt.studio.create_comfy_progress_bar
        old_update_bar = ppt.studio.update_comfy_progress_bar
        old_emit = ppt.emit_ppt_status
        events = []
        progress = []
        calls = []

        def fake_call_agent(*args, **kwargs):
            calls.append(kwargs)
            raise RuntimeError("LLM timeout")

        ppt.studio.load_config = lambda config_path: {}
        ppt.studio.resolve_task_config = lambda config, task: object()
        ppt.studio.call_agent = fake_call_agent
        ppt.studio.create_comfy_progress_bar = lambda total: {"total": total}
        ppt.studio.update_comfy_progress_bar = lambda bar, current, total=None: progress.append((current, total))
        ppt.emit_ppt_status = lambda *args, **kwargs: events.append({"args": args, "kwargs": kwargs})
        try:
            pipe = ppt.make_ppt_pipe(
                title="状态 PPT",
                pages=[{"pageNo": 1, "title": "状态页", "outlineText": "FULL_PROMPT_SHOULD_NOT_APPEAR"}],
            )
            result = ppt.run_ppt_page_compose(pipe, "", page_timeout_seconds=123, node_id="node-5")
        finally:
            ppt.studio.load_config = old_load_config
            ppt.studio.resolve_task_config = old_resolve
            ppt.studio.call_agent = old_call_agent
            ppt.studio.create_comfy_progress_bar = old_create_bar
            ppt.studio.update_comfy_progress_bar = old_update_bar
            ppt.emit_ppt_status = old_emit
        self.assertEqual(calls[0]["timeout"], 123)
        self.assertEqual(progress, [(1, 1)])
        self.assertTrue(result["pipe"]["pages"][0]["fallbackUsed"])
        self.assertIn("prompt", result["pipe"]["pages"][0])
        event_text = "\n".join(str(event) for event in events)
        self.assertIn("fallback", event_text)
        self.assertIn("node-5", event_text)
        self.assertNotIn("FULL_PROMPT_SHOULD_NOT_APPEAR", event_text)

    def test_page_composer_input_types_expose_timeout_and_hidden_id(self):
        ppt = self.load_ppt()
        input_types = ppt.ImagenStudioPPTPageComposer.INPUT_TYPES()
        self.assertEqual(input_types["required"]["单页超时秒"][1]["default"], 180)
        self.assertEqual(input_types["required"]["并发数"][1]["default"], 20)
        self.assertEqual(input_types["required"]["并发数"][1]["max"], 50)
        self.assertEqual(input_types["hidden"]["unique_id"], "UNIQUE_ID")

    def test_page_compose_runs_concurrently_and_keeps_order(self):
        ppt = self.load_ppt()
        old_load_config = ppt.studio.load_config
        old_resolve = ppt.studio.resolve_task_config
        old_call_agent = ppt.studio.call_agent
        old_emit = ppt.emit_ppt_status
        old_create_bar = ppt.studio.create_comfy_progress_bar
        old_update_bar = ppt.studio.update_comfy_progress_bar
        lock = threading.Lock()
        active = 0
        max_active = 0
        finish_order = []
        progress = []

        def fake_call_agent(*args, **kwargs):
            nonlocal active, max_active
            payload = ppt.studio.try_json(args[2])
            page_idx = int(payload["page_position"]["current"])
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.04 / page_idx)
            with lock:
                active -= 1
                finish_order.append(page_idx)
            return {
                "prompt": f"prompt-{page_idx}",
                "negative": f"negative-{page_idx}",
                "notes": "ok",
            }

        ppt.studio.load_config = lambda config_path: {}
        ppt.studio.resolve_task_config = lambda config, task: object()
        ppt.studio.call_agent = fake_call_agent
        ppt.emit_ppt_status = lambda *args, **kwargs: None
        ppt.studio.create_comfy_progress_bar = lambda total: {"total": total}
        ppt.studio.update_comfy_progress_bar = lambda bar, current, total=None: progress.append((current, total))
        try:
            pipe = ppt.make_ppt_pipe(
                title="并发拼装",
                pages=[
                    {"pageNo": 1, "title": "A", "outlineText": "A"},
                    {"pageNo": 2, "title": "B", "outlineText": "B"},
                    {"pageNo": 3, "title": "C", "outlineText": "C"},
                    {"pageNo": 4, "title": "D", "outlineText": "D"},
                ],
            )
            result = ppt.run_ppt_page_compose(pipe, "", page_timeout_seconds=180, concurrency=4)
        finally:
            ppt.studio.load_config = old_load_config
            ppt.studio.resolve_task_config = old_resolve
            ppt.studio.call_agent = old_call_agent
            ppt.emit_ppt_status = old_emit
            ppt.studio.create_comfy_progress_bar = old_create_bar
            ppt.studio.update_comfy_progress_bar = old_update_bar
        self.assertGreater(max_active, 1)
        self.assertNotEqual(finish_order, [1, 2, 3, 4])
        self.assertEqual([page["prompt"] for page in result["pipe"]["pages"]], ["prompt-1", "prompt-2", "prompt-3", "prompt-4"])
        rows = ppt.studio.try_json(result["prompt_list_json"])
        self.assertEqual([row["prompt"] for row in rows], ["prompt-1", "prompt-2", "prompt-3", "prompt-4"])
        self.assertEqual(progress[-1], (4, 4))

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
            result = ppt.run_ppt_runninghub_batch(pipe, "官方渠道", "1k", "high", "", timeout_minutes=45, poll_interval_seconds=7, concurrency=2)
        finally:
            ppt.studio.run_runninghub_rhart_g2 = old
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["quality"], "high")
        self.assertEqual(calls[0]["channel"], "官方渠道")
        self.assertEqual(calls[0]["timeout_seconds"], 2700.0)
        self.assertEqual(calls[0]["poll_interval"], 7.0)
        self.assertEqual(result["image"].shape[0], 2)
        self.assertEqual(result["pipe"]["pages"][1]["taskId"], "task-2")
        self.assertEqual(result["pipe"]["runninghub"]["concurrency"], 2)
        self.assertEqual(result["pipe"]["runninghub"]["completed"], 2)
        self.assertEqual(result["pipe"]["runninghub"]["failed"], 0)

    def test_runninghub_batch_concurrency_defaults_and_order(self):
        ppt = self.load_ppt()
        input_types = ppt.ImagenStudioPPTRunningHubBatch.INPUT_TYPES()["required"]
        self.assertEqual(input_types["并发数"][1]["default"], 50)
        self.assertEqual(input_types["并发数"][1]["max"], 100)
        old = ppt.studio.run_runninghub_rhart_g2
        lock = threading.Lock()
        active = 0
        max_active = 0
        order = []

        def fake_runninghub(**kwargs):
            nonlocal active, max_active
            page_idx = int(kwargs["prompt"].split()[-1])
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.04 / page_idx)
            with lock:
                active -= 1
                order.append(page_idx)
            image = np.full((1, 8, 8, 3), page_idx / 10, dtype=np.float32)
            return {
                "image": image,
                "output_url": f"https://example.com/{page_idx}.png",
                "task_id": f"task-{page_idx}",
                "result_json": "{}",
            }

        ppt.studio.run_runninghub_rhart_g2 = fake_runninghub
        try:
            pipe = ppt.make_ppt_pipe(
                title="并发生图",
                aspect_ratio="16:9",
                pages=[
                    {"pageNo": 1, "title": "A", "prompt": "prompt 1"},
                    {"pageNo": 2, "title": "B", "prompt": "prompt 2"},
                    {"pageNo": 3, "title": "C", "prompt": "prompt 3"},
                    {"pageNo": 4, "title": "D", "prompt": "prompt 4"},
                ],
            )
            result = ppt.run_ppt_runninghub_batch(pipe, "第三方低价渠道", "1k", "medium", "", concurrency=4)
        finally:
            ppt.studio.run_runninghub_rhart_g2 = old
        self.assertGreater(max_active, 1)
        self.assertNotEqual(order, [1, 2, 3, 4])
        self.assertEqual([page["taskId"] for page in result["pipe"]["pages"]], ["task-1", "task-2", "task-3", "task-4"])
        self.assertEqual([row["taskId"] for row in result["pipe"]["runninghub"]["results"]], ["task-1", "task-2", "task-3", "task-4"])
        self.assertEqual(result["image"].shape[0], 4)
        self.assertEqual(result["pipe"]["runninghub"]["concurrency"], 4)

    def test_runninghub_batch_failure_mentions_page(self):
        ppt = self.load_ppt()
        old = ppt.studio.run_runninghub_rhart_g2
        old_emit = ppt.emit_ppt_status
        events = []

        def fake_runninghub(**kwargs):
            raise RuntimeError("boom")

        ppt.studio.run_runninghub_rhart_g2 = fake_runninghub
        ppt.emit_ppt_status = lambda *args, **kwargs: events.append({"args": args, "kwargs": kwargs})
        try:
            pipe = ppt.make_ppt_pipe(
                title="失败生图",
                pages=[{"pageNo": 3, "title": "失败页", "prompt": "prompt"}],
            )
            with self.assertRaises(Exception) as cm:
                ppt.run_ppt_runninghub_batch(pipe, "第三方低价渠道", "1k", "medium", "", concurrency=1, node_id="node-6")
        finally:
            ppt.studio.run_runninghub_rhart_g2 = old
            ppt.emit_ppt_status = old_emit
        self.assertIn("第 3 页", str(cm.exception))
        self.assertIn("失败页", str(cm.exception))
        event_text = "\n".join(str(event) for event in events)
        self.assertIn("error", event_text)
        self.assertIn("node-6", event_text)

    def test_ppt_pipe_unpack_current_page_and_all_pages(self):
        ppt = self.load_ppt()
        pipe = ppt.make_ppt_pipe(
            title="拆包 PPT",
            pages=[
                {"pageNo": 1, "title": "封面", "prompt": "prompt cover", "negative": "neg cover"},
                {"pageNo": 2, "title": "正文", "prompt": "prompt body", "negative": "neg body"},
            ],
        )
        current = ppt.run_ppt_pipe_unpack(pipe, 2, "当前页")
        self.assertEqual(current["prompt"], "prompt body")
        self.assertEqual(current["negative"], "neg body")
        self.assertEqual(current["title"], "正文")
        self.assertEqual(current["page_count"], 2)
        self.assertEqual(current["current_page_no"], 2)
        self.assertIn('"pageNo": 2', current["page_json"])

        merged = ppt.run_ppt_pipe_unpack(pipe, 1, "全部合并")
        self.assertIn("第 1 页：封面", merged["prompt"])
        self.assertIn("prompt body", merged["prompt"])
        self.assertIn("neg cover", merged["negative"])
        self.assertEqual(merged["current_page_no"], 1)

        self.assertEqual(
            ppt.ImagenStudioPPTPipeUnpack.RETURN_NAMES,
            ("PPT束", "正向提示词", "负面提示词", "页面标题", "页面JSON", "页数", "当前页码"),
        )

        with self.assertRaises(Exception) as cm:
            ppt.run_ppt_pipe_unpack(pipe, 3, "当前页")
        self.assertIn("页码超出范围", str(cm.exception))

    def test_ppt_pipe_unpack_page_number_can_drive_writeback(self):
        ppt = self.load_ppt()
        old_output_dir = ppt.output_export_dir
        temp_dir = ROOT / ".tmp_ppt_page_sync_test"
        temp_dir.mkdir(exist_ok=True)
        ppt.output_export_dir = lambda: temp_dir
        try:
            pipe = ppt.make_ppt_pipe(
                title="页码同步 PPT",
                pages=[
                    {"pageNo": 1, "title": "封面", "prompt": "prompt cover"},
                    {"pageNo": 2, "title": "正文", "prompt": "prompt body"},
                ],
            )
            unpacked = ppt.run_ppt_pipe_unpack(pipe, 2, "当前页")
            image = np.full((1, 12, 16, 3), 0.5, dtype=np.float32)
            result = ppt.run_ppt_image_writeback(unpacked["pipe"], image, unpacked["current_page_no"])
            self.assertNotIn("imagePath", result["pipe"]["pages"][0])
            self.assertIn("imagePath", result["pipe"]["pages"][1])
            self.assertTrue(Path(result["pipe"]["pages"][1]["imagePath"]).exists())
        finally:
            ppt.output_export_dir = old_output_dir
            for path in sorted(temp_dir.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            if temp_dir.exists():
                temp_dir.rmdir()

    def test_ppt_image_writeback_and_export_from_image_path(self):
        ppt = self.load_ppt()
        old_output_dir = ppt.output_export_dir
        temp_dir = ROOT / ".tmp_ppt_writeback_test"
        temp_dir.mkdir(exist_ok=True)
        ppt.output_export_dir = lambda: temp_dir
        try:
            pipe = ppt.make_ppt_pipe(
                title="写回 PPT",
                pages=[{"pageNo": 1, "title": "封面", "prompt": "prompt"}],
            )
            image = np.full((1, 12, 16, 3), 0.5, dtype=np.float32)
            result = ppt.run_ppt_image_writeback(pipe, image, 1)
            image_path = Path(result["pipe"]["pages"][0]["imagePath"])
            self.assertTrue(image_path.exists())
            self.assertIn('"imagePath"', result["writeback_json"])
            export = ppt.run_ppt_export(result["pipe"], None, "writeback-test")
            self.assertTrue(Path(export["path"]).exists())
            self.assertIn("writeback-test", export["path"])
        finally:
            ppt.output_export_dir = old_output_dir
            for path in sorted(temp_dir.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            if temp_dir.exists():
                temp_dir.rmdir()

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
        self.assertIn("ImagenStudioPPTPipeUnpack", module.NODE_CLASS_MAPPINGS)
        self.assertIn("ImagenStudioPPTImageWriteback", module.NODE_CLASS_MAPPINGS)
        self.assertIn("ImagenStudioPPTExport", module.NODE_CLASS_MAPPINGS)
        self.assertTrue(module.NODE_CLASS_MAPPINGS["ImagenStudioPPTExport"].OUTPUT_NODE)
        self.assertEqual(
            module.NODE_DISPLAY_NAME_MAPPINGS["ImagenStudioPPTOutlinePlan"],
            "Imagen Studio PPT 大纲规划",
        )


if __name__ == "__main__":
    unittest.main()
