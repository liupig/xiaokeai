import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
import companion_video as video


class VideoIntegrationTests(unittest.TestCase):
    def test_native_video_preserves_timestamps_and_fact_contract(self):
        calls = {}
        class Capture:
            error = None
            thread = SimpleNamespace(is_alive=lambda: True)
            def __init__(self):
                self.clip = [(time.monotonic() + i * .5, Image.new('RGB', (16, 8)), i, '') for i in range(8)]
            def latest(self):
                return self.clip
            def close(self): pass
        class Engine:
            SCENE_PROMPTS = {'game': '游戏事实'}
            def load(self): pass
            def describe(self, image, prompt, **kwargs):
                calls.update(kwargs, prompt=prompt)
                return '画面：直播间内正在对局'
        body = SimpleNamespace(scene='game', before='虎牙直播间', prompt='', ask='', crop=[])
        capture = Capture()
        with patch.object(video, '_source', ('game', 0, ())), patch.object(video, '_live', capture), patch('observations.save_model_frames', return_value=[]), patch('observations.record'):
            result = video.observe(Engine(), body)
        self.assertEqual(calls['video_timestamps'], [row[0] for row in capture.clip])
        self.assertEqual(len(calls['frames']), 8)
        self.assertIn('经过：', calls['prompt'])
        self.assertTrue(result['ok'])
        self.assertEqual(result['input_mode'], 'live_video')

    def test_stale_capture_is_replaced_within_the_same_observation(self):
        class Capture:
            error = None
            thread = SimpleNamespace(is_alive=lambda: True)

            def __init__(self, stale=False):
                stamp = time.monotonic() - (10 if stale else 0)
                self.clip = [(stamp + i * .5, Image.new('RGB', (16, 8)), i, '') for i in range(8)]
                self.closed = False

            def latest(self):
                return self.clip

            def start(self):
                return self

            def close(self):
                self.closed = True
                return True

        class Engine:
            SCENE_PROMPTS = {'game': '游戏事实'}

            def load(self):
                pass

            def describe(self, image, prompt, **kwargs):
                return '画面：新采集已经恢复'

        old = Capture(stale=True)
        new = Capture()
        body = SimpleNamespace(scene='game', before='', prompt='', ask='', crop=[])
        with patch.object(video, '_source', ('game', 0, ())), \
                patch.object(video, '_live', old), \
                patch.object(video, 'LiveVideo', return_value=new) as live_factory, \
                patch('observations.save_model_frames', return_value=[]), \
                patch('observations.record'):
            result = video.observe(Engine(), body)
        self.assertTrue(old.closed)
        self.assertEqual(live_factory.call_args.kwargs['fps'], 1)
        self.assertEqual(live_factory.call_args.kwargs['seconds'], 4)
        self.assertTrue(result['ok'])
        self.assertEqual(result['text'], '画面：新采集已经恢复')


class TextReactionTests(unittest.TestCase):
    def test_react_uses_text_only_model_input(self):
        calls = {}

        class Engine:
            def load(self):
                calls['loaded'] = True

            def describe(self, image, prompt, **kwargs):
                calls.update(kwargs, image=image, prompt=prompt)
                return '情绪：平静\n值不值得说：不说\n台词：'

        body = SimpleNamespace(prompt='刚刚片子里说：船要开了')
        result = video.react(Engine(), body)
        self.assertTrue(calls['loaded'])
        self.assertIsNone(calls['image'])
        self.assertEqual(calls['prompt'], body.prompt)
        self.assertFalse(calls['do_sample'])
        self.assertEqual(result['input_mode'], 'text')
        self.assertIn('值不值得说', result['text'])

    def test_visual_reaction_returns_three_line_result_without_a_second_observation(self):
        calls = {}

        class Capture:
            error = None
            thread = SimpleNamespace(is_alive=lambda: True)
            def latest(self):
                return [(time.monotonic() + i * .2, Image.new('RGB', (16, 8)), i, '') for i in range(4)]
            def close(self):
                pass

        class Engine:
            SCENE_PROMPTS = {'movie': '电影'}
            def load(self):
                pass
            def describe(self, image, prompt, **kwargs):
                calls.update(kwargs, prompt=prompt)
                return '变化：舱门打开\n情绪：紧张\n台词：门突然开了'

        body = SimpleNamespace(scene='movie', before='精简人设', prompt='变化情绪台词', ask='', crop=[], reaction=True)
        with patch.object(video, '_source', ('movie', 0, ())), patch.object(video, '_live', Capture()), \
                patch('observations.save_model_frames', return_value=[]), patch('observations.record'):
            result = video.observe(Engine(), body)
        self.assertIn('精简人设\n变化情绪台词', calls['prompt'])
        self.assertEqual(calls['max_new_tokens'], 80)
        self.assertEqual(result['direct_raw'], '变化：舱门打开\n情绪：紧张\n台词：门突然开了')
        self.assertEqual(result['text'], '')


if __name__ == '__main__':
    unittest.main()
