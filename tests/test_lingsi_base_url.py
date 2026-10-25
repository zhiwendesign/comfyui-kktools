import importlib.util
import sys
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def load_lingsi():
    path = ROOT / "nodes" / "lingsi.py"
    spec = importlib.util.spec_from_file_location("lingsi_base_url_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["lingsi_base_url_test"] = module
    spec.loader.exec_module(module)
    return module


def load_ppt():
    path = ROOT / "nodes" / "imagen_ppt.py"
    spec = importlib.util.spec_from_file_location("imagen_ppt_for_lingsi_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["imagen_ppt_for_lingsi_test"] = module
    spec.loader.exec_module(module)
    return module


class LingsiBaseUrlTests(unittest.TestCase):
    def test_generated_image_download_retries_timeout(self):
        module = load_lingsi()

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b"image-bytes"

        with mock.patch.object(module.urllib.request, "urlopen", side_effect=[TimeoutError("slow"), TimeoutError("slow"), Response()]) as urlopen:
            with mock.patch.object(module.time, "sleep"):
                result = module._image_bytes_from_url("https://example.com/image.png", "secret")
        self.assertEqual(result, b"image-bytes")
        self.assertEqual(urlopen.call_count, 3)

    def test_generated_image_is_saved_to_output_directory(self):
        module = load_lingsi()
        old_output_dir = module.lingsi_image_output_dir
        temp_dir = ROOT / ".tmp_lingsi_image_output_test"
        temp_dir.mkdir(exist_ok=True)
        module.lingsi_image_output_dir = lambda: temp_dir
        try:
            image = np.full((1, 12, 16, 3), 0.5, dtype=np.float32)
            path = Path(module.save_generated_image(image, "gpt-image-2.5-flare"))
            self.assertTrue(path.exists())
            self.assertEqual(path.parent, temp_dir)
            self.assertTrue(path.name.startswith("gpt-image-2.5-flare-"))
        finally:
            module.lingsi_image_output_dir = old_output_dir
            for path in temp_dir.iterdir():
                path.unlink()
            temp_dir.rmdir()

    def test_default_endpoints_match_mindapi(self):
        module = load_lingsi()
        endpoints = module.resolve_api_endpoints("")
        self.assertEqual(endpoints["chat"], "https://mindapi.cc/v1/chat/completions")
        self.assertEqual(endpoints["image_generations"], "https://mindapi.cc/v1/images/generations")
        self.assertEqual(endpoints["image_edits"], "https://mindapi.cc/v1/images/edits")
        self.assertEqual(endpoints["banana_generate"], "https://mindapi.cc/pt/v1/api/generate")

    def test_custom_base_url_keeps_routes(self):
        module = load_lingsi()
        endpoints = module.resolve_api_endpoints("https://third-party.example/api")
        self.assertEqual(endpoints["chat"], "https://third-party.example/api/v1/chat/completions")
        self.assertEqual(endpoints["image_generations"], "https://third-party.example/api/v1/images/generations")
        self.assertEqual(endpoints["image_edits"], "https://third-party.example/api/v1/images/edits")
        self.assertEqual(endpoints["banana_generate"], "https://third-party.example/api/pt/v1/api/generate")

    def test_base_url_with_v1_does_not_duplicate_v1(self):
        module = load_lingsi()
        endpoints = module.resolve_api_endpoints("https://third-party.example/v1/")
        self.assertEqual(endpoints["chat"], "https://third-party.example/v1/chat/completions")
        self.assertEqual(endpoints["image_generations"], "https://third-party.example/v1/images/generations")
        self.assertEqual(endpoints["image_edits"], "https://third-party.example/v1/images/edits")
        self.assertEqual(endpoints["banana_generate"], "https://third-party.example/pt/v1/api/generate")

    def test_input_types_expose_base_url_after_existing_widgets(self):
        module = load_lingsi()
        input_types = module.kkGPT_image_API.INPUT_TYPES()
        required = input_types["required"]
        optional = input_types["optional"]
        self.assertEqual(
            list(required.keys())[:7],
            ["api_key", "model", "aspect_ratio", "resolution", "quality", "count", "base_url"],
        )
        self.assertNotIn("prompt", required)
        self.assertIn("prompt", optional)
        self.assertEqual(required["base_url"][1]["default"], "https://mindapi.cc")
        self.assertEqual(required["并发数"][1]["default"], 3)
        self.assertEqual(required["并发数"][1]["max"], 20)
        self.assertEqual(required["重试次数"][1]["default"], 6)
        self.assertEqual(required["限流等待秒"][1]["default"], 15)
        self.assertEqual(required["限流等待秒"][1]["max"], 500)
        self.assertEqual(optional["PPT束"][0], "IMAGEN_STUDIO_PIPE")
        self.assertEqual(optional["ratio"][0], "STRING")
        self.assertEqual(optional["string"][0], "STRING")
        self.assertTrue(optional["string"][1]["forceInput"])
        self.assertEqual(optional["string_8"][0], "STRING")
        self.assertEqual(optional["API配置"][0], "KK_IMAGE_API_CONFIG")
        self.assertEqual(module.kkGPT_image_API.RETURN_NAMES, ("image", "raw_json", "PPT束", "日志", "Prompt"))

    def test_prompt_image_references_follow_connected_image_order(self):
        module = load_lingsi()
        prompt = "让 @Image2 采用 @Image1 的服装，@Image 保持主体；邮箱 user@image1.com 不变"
        self.assertEqual(
            module.resolve_prompt_image_references(prompt, 2),
            "让 image 2 采用 image 1 的服装，image 1 保持主体；邮箱 user@image1.com 不变",
        )

    def test_prompt_image_reference_outside_connected_range_is_preserved(self):
        module = load_lingsi()
        self.assertEqual(
            module.resolve_prompt_image_references("参考 @Image1 和 @Image3", 2),
            "参考 image 1 和 @Image3",
        )

    def test_prompt_string_references_follow_input_names(self):
        module = load_lingsi()
        prompt = "主体：@string；补充：@string_1；邮箱 user@string_1.com；未连接 @string_2"
        self.assertEqual(
            module.resolve_prompt_string_references(prompt, ["女孩", "蓝色外套", None]),
            "主体：女孩；补充：蓝色外套；邮箱 user@string_1.com；未连接 @string_2",
        )

    def test_generate_resolves_connected_strings_before_request(self):
        module = load_lingsi()
        node = module.kkGPT_image_API()
        image = np.zeros((1, 8, 8, 3), dtype=np.float32)
        node._generate_single = mock.Mock(return_value=(image, "{}"))
        outputs = node.generate(
            api_key="sk-secret-value",
            prompt="@string，@string_1，参考 @Image1",
            image=image,
            string="女孩",
            string_1="蓝色外套",
        )
        self.assertEqual(node._generate_single.call_args.kwargs["prompt"], "女孩，蓝色外套，参考 image 1")
        self.assertEqual(outputs[4], "女孩，蓝色外套，参考 image 1")

    def test_lingsi_prompt_optional_for_ppt_pipe_but_required_for_single_mode(self):
        module = load_lingsi()
        node = module.kkGPT_image_API()
        old_batch = module.generate_lingsi_ppt_batch
        calls = []

        def fake_batch(**kwargs):
            calls.append(kwargs)
            image = np.zeros((1, 8, 8, 3), dtype=np.float32)
            return image, "{}", kwargs["ppt_pipe"]

        module.generate_lingsi_ppt_batch = fake_batch
        try:
            pipe = {
                "pipe_type": "IMAGEN_STUDIO_PIPE",
                "pages": [{"pageNo": 1, "title": "A", "prompt": "prompt 1"}],
            }
            image, _raw_json, out_pipe, _log, complete_prompt = node.generate(
                api_key="sk-secret-value",
                model="gpt-image-2",
                aspect_ratio="16:9",
                resolution="1K",
                PPT束=pipe,
            )
            self.assertEqual(image.shape[0], 1)
            self.assertIs(out_pipe, pipe)
            self.assertEqual(complete_prompt, "")
            self.assertEqual(calls[0]["ppt_pipe"], pipe)
        finally:
            module.generate_lingsi_ppt_batch = old_batch

        with self.assertRaises(RuntimeError) as cm:
            node.generate(
                api_key="sk-secret-value",
                model="gpt-image-2",
                aspect_ratio="16:9",
                resolution="1K",
                prompt="",
            )
        self.assertIn("prompt is required", str(cm.exception))

    def test_rate_limit_wait_caps_at_500_seconds(self):
        module = load_lingsi()
        self.assertTrue(module.is_lingsi_rate_limit_error(RuntimeError("MindAPI HTTP 429: rate_limit_error")))
        self.assertEqual(module.lingsi_rate_limit_wait_seconds(1, 15), 15)
        self.assertEqual(module.lingsi_rate_limit_wait_seconds(2, 15), 30)
        self.assertEqual(module.lingsi_rate_limit_wait_seconds(10, 15), 500)

    def test_ppt_pipe_batch_generates_pages_and_exports(self):
        module = load_lingsi()
        ppt = load_ppt()
        old_generate = module.generate_lingsi_image
        old_output_dir = module.lingsi_ppt_output_dir
        old_ppt_output_dir = ppt.output_export_dir
        temp_dir = ROOT / ".tmp_lingsi_ppt_batch_test"
        temp_dir.mkdir(exist_ok=True)
        lock = threading.Lock()
        active = 0
        max_active = 0
        finish_order = []

        def fake_generate_lingsi_image(**kwargs):
            nonlocal active, max_active
            page_idx = int(kwargs["prompt"].split()[-1])
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.04 / page_idx)
            with lock:
                active -= 1
                finish_order.append(page_idx)
            image = np.full((1, 12, 16, 3), page_idx / 10, dtype=np.float32)
            raw = {
                "ok": True,
                "endpoint": "https://third-party.example/v1/images/generations",
                "route": "/images/generations",
                "model": kwargs["model"],
                "aspect_ratio": kwargs["aspect_ratio"],
                "requested_resolution": kwargs["resolution"],
                "effective_resolution": kwargs["resolution"],
                "generated_count": 1,
                "selected_image": {"kind": "url", "value": f"https://example.com/{page_idx}.png"},
            }
            return image, module._json_dumps(raw)

        module.generate_lingsi_image = fake_generate_lingsi_image
        module.lingsi_ppt_output_dir = lambda: temp_dir
        ppt.output_export_dir = lambda: temp_dir
        try:
            pipe = {
                "pipe_type": "IMAGEN_STUDIO_PIPE",
                "title": "kaka 批量 PPT",
                "aspect_ratio": "16:9",
                "pages": [
                    {"pageNo": 1, "title": "A", "prompt": "prompt 1"},
                    {"pageNo": 2, "title": "B", "prompt": "prompt 2"},
                    {"pageNo": 3, "title": "C", "prompt": "prompt 3"},
                ],
            }
            image, raw_json, out_pipe = module.generate_lingsi_ppt_batch(
                "sk-secret-value",
                pipe,
                "gpt-image-2",
                "1K",
                "https://third-party.example/v1",
                concurrency=3,
            )
            self.assertGreater(max_active, 1)
            self.assertNotEqual(finish_order, [1, 2, 3])
            self.assertEqual(image.shape[0], 3)
            self.assertEqual([page["imageSource"] for page in out_pipe["pages"]], ["lingsi-batch", "lingsi-batch", "lingsi-batch"])
            self.assertTrue(all(Path(page["imagePath"]).exists() for page in out_pipe["pages"]))
            self.assertEqual(out_pipe["lingsi"]["concurrency"], 3)
            self.assertNotIn("sk-secret-value", raw_json)
            self.assertNotIn("Authorization", raw_json)
            exported = ppt.run_ppt_export(out_pipe, None, "lingsi-batch-test")
            self.assertTrue(Path(exported["path"]).exists())
            with zipfile.ZipFile(exported["path"], "r") as zf:
                self.assertIn("ppt/slides/slide3.xml", set(zf.namelist()))
        finally:
            module.generate_lingsi_image = old_generate
            module.lingsi_ppt_output_dir = old_output_dir
            ppt.output_export_dir = old_ppt_output_dir
            for path in sorted(temp_dir.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            if temp_dir.exists():
                temp_dir.rmdir()

    def test_ppt_pipe_batch_failure_masks_api_key(self):
        module = load_lingsi()
        old_generate = module.generate_lingsi_image

        def fake_generate_lingsi_image(**kwargs):
            raise RuntimeError('{"error":"boom sk-secret-value","endpoint":"https://example.com/v1/images/generations"}')

        module.generate_lingsi_image = fake_generate_lingsi_image
        try:
            pipe = {
                "pipe_type": "IMAGEN_STUDIO_PIPE",
                "pages": [{"pageNo": 2, "title": "失败页", "prompt": "prompt 2"}],
            }
            with self.assertRaises(Exception) as cm:
                module.generate_lingsi_ppt_batch(
                    "sk-secret-value",
                    pipe,
                    "gpt-image-2",
                    "1K",
                    "https://third-party.example",
                )
        finally:
            module.generate_lingsi_image = old_generate
        text = str(cm.exception)
        self.assertIn("第 2 页", text)
        self.assertIn("失败页", text)
        self.assertNotIn("sk-secret-value", text)

    def test_ppt_pipe_batch_retries_429_rate_limit(self):
        module = load_lingsi()
        old_generate = module.generate_lingsi_image
        old_output_dir = module.lingsi_ppt_output_dir
        old_sleep = module.time.sleep
        temp_dir = ROOT / ".tmp_lingsi_ppt_retry_test"
        temp_dir.mkdir(exist_ok=True)
        calls = {}

        def fake_generate_lingsi_image(**kwargs):
            page_idx = int(kwargs["prompt"].split()[-1])
            calls[page_idx] = calls.get(page_idx, 0) + 1
            if page_idx == 2 and calls[page_idx] == 1:
                raise RuntimeError(module._json_dumps({
                    "error": "MindAPI HTTP 429: Upstream rate limit exceeded",
                    "response_payload": {
                        "status": 429,
                        "body": '{"error":{"message":"Upstream rate limit exceeded","type":"rate_limit_error"}}',
                    },
                    "endpoint": "https://third-party.example/v1/images/generations",
                    "route": "/images/generations",
                }))
            image = np.full((1, 12, 16, 3), page_idx / 10, dtype=np.float32)
            raw = {
                "ok": True,
                "endpoint": "https://third-party.example/v1/images/generations",
                "route": "/images/generations",
                "model": kwargs["model"],
                "aspect_ratio": kwargs["aspect_ratio"],
                "requested_resolution": kwargs["resolution"],
                "effective_resolution": kwargs["resolution"],
                "generated_count": 1,
            }
            return image, module._json_dumps(raw)

        module.generate_lingsi_image = fake_generate_lingsi_image
        module.lingsi_ppt_output_dir = lambda: temp_dir
        module.time.sleep = lambda _seconds: None
        try:
            pipe = {
                "pipe_type": "IMAGEN_STUDIO_PIPE",
                "title": "kaka 限流重试 PPT",
                "aspect_ratio": "16:9",
                "pages": [
                    {"pageNo": 1, "title": "A", "prompt": "prompt 1"},
                    {"pageNo": 2, "title": "B", "prompt": "prompt 2"},
                ],
            }
            image, raw_json, out_pipe = module.generate_lingsi_ppt_batch(
                "sk-secret-value",
                pipe,
                "gpt-image-2",
                "1K",
                "https://third-party.example/v1",
                concurrency=2,
                retry_count=2,
                retry_wait_seconds=1,
            )
            self.assertEqual(image.shape[0], 2)
            self.assertEqual(calls[2], 2)
            self.assertEqual(out_pipe["pages"][1]["lingsiDebug"]["retryCount"], 1)
            self.assertEqual(out_pipe["lingsi"]["maxRateLimitWaitSeconds"], 500)
            self.assertNotIn("sk-secret-value", raw_json)
        finally:
            module.generate_lingsi_image = old_generate
            module.lingsi_ppt_output_dir = old_output_dir
            module.time.sleep = old_sleep
            for path in sorted(temp_dir.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            if temp_dir.exists():
                temp_dir.rmdir()


if __name__ == "__main__":
    unittest.main()
