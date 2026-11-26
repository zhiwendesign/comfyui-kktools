import runpy
import unittest
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "nodes" / "RandomSelector.py"
Selector = runpy.run_path(str(MODULE))["kkRandomSelector"]


class RandomSelectorTests(unittest.TestCase):
    def test_sparse_inputs_keep_their_types_and_use_only_the_selected_source(self):
        node = Selector()
        value = object()
        inputs = {"input_3": value, "input_1": False}
        for seed, expected in [(0, "input_3"), (1, "input_1")]:
            with self.subTest(seed=seed):
                pending = dict.fromkeys([*inputs, "Markdown文件"])
                self.assertEqual(node.check_lazy_status(seed, **pending), [expected])
                selected, name, candidates, _ = node.random_select(
                    "unused", seed=seed, Markdown文件={"content": "unused"}, **inputs
                )
                self.assertIs(selected, inputs[expected])
                self.assertEqual(name, expected)
                self.assertEqual(candidates, "input_1,input_3")

    def test_existing_json_and_markdown_workflows(self):
        node = Selector()
        config = '[{"groupName":"冷色","list":["0089FF","35B7A3"]}]'
        self.assertEqual(node.check_lazy_status(0, json_config=config), [])
        self.assertEqual(node.random_select(config, "冷色", 0)[:3], ("35B7A3", "冷色", "冷色"))
        self.assertEqual(node.check_lazy_status(0, Markdown文件=None), ["Markdown文件"])
        file = {"filename": "模板.md", "content": "模板正文"}
        selected, group, names, markdown = node.random_select("", seed=0, Markdown文件=file)
        self.assertEqual((selected, group, names), ("模板正文", "Markdown", "模板.md"))
        self.assertEqual(markdown["items"], [file])
