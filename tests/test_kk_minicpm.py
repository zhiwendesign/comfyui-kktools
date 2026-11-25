import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import torch


path = Path(__file__).resolve().parents[1] / 'nodes' / 'kk_minicpm.py'
spec = importlib.util.spec_from_file_location('kk_minicpm_test', path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class MiniCPMTests(unittest.TestCase):
    def setUp(self):
        self.connection = m.kkMiniCPMLoader().load(m._VIDEO_MODEL, 'http://127.0.0.1:11434', 0, 4096, 128, 0.2, 42, 60)[0]

    def test_registers_nodes(self):
        self.assertEqual(len(m.NODE_CLASS_MAPPINGS), 12)
        for node in m.NODE_CLASS_MAPPINGS.values():
            self.assertTrue(callable(getattr(node, node.FUNCTION)))
            self.assertTrue(node.INPUT_TYPES()['required'])

    def test_loader_validates_url_and_accepts_model_names(self):
        for url in ('ftp://localhost:11434', 'http://user@localhost:11434', 'http://localhost:11434/?x=1', 'http://localhost:bad'):
            with self.assertRaises(ValueError):
                m._local_url(url)
        conn, name = m.kkMiniCPMLoader().load('a-different-model', 'https://example.com/v1/', 0, 4096, 128, 0.2, 42, 60, backend='llama.app')
        self.assertEqual((name, conn['url'], conn['backend']), ('a-different-model', 'https://example.com/v1', 'llama.app'))
        with self.assertRaises(ValueError):
            m.kkMiniCPMLoader().load('', 'http://localhost:11434', 0, 4096, 128, 0.2, 42, 60)
        self.assertEqual(m._local_url('http://[::1]:11434/'), 'http://[::1]:11434')

    def test_llama_chat_multimodal_json_and_unload(self):
        conn, _ = m.kkMiniCPMLoader().load('arbitrary-model', 'http://localhost:9931/v1', 0, 4096, 128, 0.2, 42, 60, backend='llama.app')
        with patch.object(m, '_request', return_value={'choices': [{'message': {'content': '{"ok":true}'}}]}) as request:
            self.assertEqual(m._chat(conn, 'inspect', ['abcd', 'efgh'], json_mode=True), '{"ok":true}')
        _, endpoint, payload = request.call_args.args
        self.assertEqual(endpoint, '/chat/completions')
        self.assertEqual(payload['model'], 'arbitrary-model')
        self.assertEqual(payload['response_format'], {'type': 'json_object'})
        self.assertEqual([x['image_url']['url'] for x in payload['messages'][-1]['content'][1:]], ['data:image/png;base64,abcd', 'data:image/png;base64,efgh'])
        with patch.object(m, '_request', side_effect=AssertionError('unexpected unload request')):
            self.assertFalse(m._unload(conn))

    def test_legacy_loader_maps_to_ollama(self):
        for old, expected in [('MiniCPM-V 4.7', m._VISION_MODEL), ('MiniCPM-V 4.5', m._VIDEO_MODEL), ('MiniCPM5 2B', m._TEXT_MODEL)]:
            conn, name = m.kkMiniCPMLocalLoader().load(old, 4096, 128, 0.1, 42, 60)
            self.assertEqual((name, conn['url'], conn['model']), (expected, 'http://127.0.0.1:11434', expected))
        with self.assertRaisesRegex(ValueError, 'Ollama'):
            m.kkMiniCPMLocalLoader().load('自定义 GGUF', 4096, 128, 0.1, 42, 60)

    def test_json_parses_fenced_content_and_traverses(self):
        normalized, value, ok, error = m.kkMiniCPMJSON().parse('结果：```json\n{"a":[{"b":"是"}]}\n```', 'a.0.b')
        self.assertEqual((value, ok, error), ('是', True, ''))
        self.assertEqual(json.loads(normalized), {'a': [{'b': '是'}]})
        self.assertEqual(m.kkMiniCPMJSON().parse('{"a":1}', '/missing')[2], False)
        self.assertEqual(m.kkMiniCPMJSON().parse('no json', '')[2], False)
        self.assertEqual(m.kkMiniCPMJSON().parse('{"bad": invalid, "nested": [1]}', '')[2], False)
        self.assertEqual(m._get_path({'a/b': [7]}, '/a~1b/0'), 7)

    def test_router_routes_real_inputs_and_rejects_missing(self):
        image = torch.zeros((1, 4, 4, 3))
        result = m.kkMiniCPMRouter().route('auto', '请提取文字', image=image)
        self.assertEqual(result[0], 'ocr')
        self.assertEqual(result[-2], True)
        self.assertEqual(m.kkMiniCPMRouter().route('auto', '优化提示词')[0], 'prompt')
        self.assertEqual(m.kkMiniCPMRouter().route('auto', '', video=object())[0], 'video')
        with patch.object(m, '_chat', return_value='{"route":"prompt"}'):
            routed = m.kkMiniCPMRouter().route('auto', '让画面描写更丰富', classifier=self.connection)
            self.assertEqual((routed[0], json.loads(routed[1])['method']), ('prompt', 'model'))
        with patch.object(m, '_chat', return_value='{"route":"ocr"}'):
            with self.assertRaises(ValueError):
                m.kkMiniCPMRouter().route('auto', '文本', classifier=self.connection)
        with self.assertRaises(ValueError):
            m.kkMiniCPMRouter().route('qa', '检查')

    def test_caption_preserves_order_and_unloads_on_failure(self):
        images = torch.stack([torch.zeros((4, 4, 3)), torch.ones((4, 4, 3))])
        with patch.object(m, '_chat', side_effect=['黑', '白']) as chat:
            result, _, count, saved = m.kkMiniCPMCaption().caption(self.connection, images, '描述', 256, 'a.png\nb.png')
        self.assertEqual(count, 2)
        self.assertEqual(json.loads(saved), [])
        self.assertEqual([x['filename'] for x in json.loads(result)], ['a.png', 'b.png'])
        self.assertEqual(chat.call_args_list[0].kwargs['keep_alive'], '5m')
        self.assertEqual(chat.call_args_list[1].kwargs['keep_alive'], 0)
        with patch.object(m, '_chat', side_effect=['黑', RuntimeError('failed')]), patch.object(m, '_unload') as unload:
            with self.assertRaises(RuntimeError):
                m.kkMiniCPMCaption().caption(self.connection, images, '描述', 256)
            unload.assert_called_once()
        with self.assertRaises(ValueError):
            m.kkMiniCPMCaption().caption(self.connection, images, '描述', 256, 'one')

    def test_caption_saves_without_overwriting(self):
        images = torch.zeros((2, 4, 4, 3))
        temp_base = path.parents[3] / 'temp'
        temp_base.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_base) as td:
            self.assertTrue(Path(td).resolve().is_relative_to(temp_base.resolve()))
            folder_paths = types.SimpleNamespace(get_output_directory=lambda: td)
            with patch.dict(sys.modules, {'folder_paths': folder_paths}), patch.object(m, '_chat', side_effect=['甲', '乙']):
                _, _, count, saved = m.kkMiniCPMCaption().caption(self.connection, images, '描述', 256, 'a.png\nb.jpg', True, 'test')
            self.assertEqual(count, 2)
            self.assertEqual([Path(x).name for x in json.loads(saved)], ['a.txt', 'b.txt'])
            self.assertEqual((Path(td)/'test/a.txt').read_text(encoding='utf-8'), '甲\n')
            with patch.dict(sys.modules, {'folder_paths': folder_paths}), patch.object(m, '_chat') as chat:
                with self.assertRaises(FileExistsError):
                    m.kkMiniCPMCaption().caption(self.connection, images, '描述', 256, 'a.png\nb.jpg', True, 'test')
                chat.assert_not_called()
                with self.assertRaises(ValueError):
                    m.kkMiniCPMCaption().caption(self.connection, images, '描述', 256, 'a.png\nb.jpg', True, '../other')

    def test_video_uniformly_samples_in_order(self):
        class Video:
            def get_components(self):
                return type('Components', (), {'images': torch.arange(10).view(10,1,1,1).expand(-1,2,2,3).float() / 10})()
        with patch.object(m, '_chat', return_value='ok') as chat:
            result, count = m.kkMiniCPMVideo().analyze(self.connection, Video(), '分析', 3, 256)
        self.assertEqual((result, count), ('ok', 3))
        self.assertEqual(len(chat.call_args.args[2]), 3)

    def test_qa_requires_valid_report(self):
        image = torch.zeros((1, 4, 4, 3))
        good = '{"passed":true,"score":75,"issues":["小问题"],"summary":"可用"}'
        with patch.object(m, '_chat', return_value=good):
            summary, report, passed, score = m.kkMiniCPMQA().evaluate(self.connection, image, '检查', 256)
        self.assertEqual((summary, passed, score), ('可用', True, 75.0))
        self.assertEqual(json.loads(report)['issues'], ['小问题'])
        with patch.object(m, '_chat', return_value='{"passed":"false","score":99,"issues":[],"summary":"x"}'):
            with self.assertRaises(ValueError):
                m.kkMiniCPMQA().evaluate(self.connection, image, '检查', 256)


if __name__ == '__main__':
    unittest.main()
