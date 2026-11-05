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


if __name__ == '__main__':
    unittest.main()
