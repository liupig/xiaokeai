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


if __name__ == '__main__':
    unittest.main()
