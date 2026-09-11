import importlib.util
import io
import json
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


class Routes:
    def get(self, _path):
        return lambda function: function

    def post(self, _path):
        return lambda function: function

    def patch(self, _path):
        return lambda function: function

    def delete(self, _path):
        return lambda function: function


def load_prompts():
    server = types.SimpleNamespace(PromptServer=type("PromptServer", (), {"instance": types.SimpleNamespace(routes=Routes())}))
    folder_paths = types.SimpleNamespace(
        get_user_directory=lambda: "/tmp/comfy-user",
        get_input_directory=lambda: "/tmp/comfy-input",
    )
    sys.modules["server"] = server
    sys.modules["folder_paths"] = folder_paths
    spec = importlib.util.spec_from_file_location("skills_package_test", ROOT / "nodes" / "prompts.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def package_bytes(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class SkillsPackageTests(unittest.TestCase):
    def test_user_directory_and_round_trip_preserve_name_and_cover(self):
        module = load_prompts()
        self.assertEqual(module.SKILLS_LIBRARY_DIR, Path("/tmp/comfy-user/kktools/skills-templates").resolve())
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as target:
            module.SKILLS_LIBRARY_DIR = Path(source)
            module.SKILLS_INDEX_PATH = Path(source) / "index.json"
            record = module._save_skill(
                {"filename": "skill.md", "content": "# Skill"},
                np.ones((8, 8, 3), dtype=np.float32),
            )
            module._rename_skill(record["id"], "保留名称")
            data = module._export_skill_package()

            module.SKILLS_LIBRARY_DIR = Path(target)
            module.SKILLS_INDEX_PATH = Path(target) / "index.json"
            self.assertEqual(module._import_skill_package(data), 1)
            restored = module._read_skills_index()["skills"][0]
            self.assertEqual(restored["name"], "保留名称")
            self.assertTrue(restored["hasCover"])
            self.assertTrue(module._skill_cover_path(restored["id"]).is_file())

    def test_import_rejects_empty_and_unsafe_packages(self):
        module = load_prompts()
        with tempfile.TemporaryDirectory() as target:
            module.SKILLS_LIBRARY_DIR = Path(target)
            module.SKILLS_INDEX_PATH = Path(target) / "index.json"
            with self.assertRaisesRegex(RuntimeError, "没有 Markdown"):
                module._import_skill_package(package_bytes({"readme.txt": b"empty"}))
            with self.assertRaisesRegex(RuntimeError, "无效路径"):
                module._import_skill_package(package_bytes({"../bad.md": b"# bad"}))

    def test_import_rejects_oversized_markdown(self):
        module = load_prompts()
        with tempfile.TemporaryDirectory() as target:
            module.SKILLS_LIBRARY_DIR = Path(target)
            module.SKILLS_INDEX_PATH = Path(target) / "index.json"
            data = package_bytes({"large.md": b"x" * (module.MAX_MARKDOWN_FILE_BYTES + 1)})
            with self.assertRaisesRegex(RuntimeError, "不能超过 5 MB"):
                module._import_skill_package(data)


if __name__ == "__main__":
    unittest.main()
