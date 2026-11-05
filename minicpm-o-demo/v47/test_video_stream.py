import threading
import time
import unittest

from video_stream import LiveVideo


class FakeScreen:
    def __init__(self):
        self.closed = False

    def open(self):
        return "fake"

    def grab(self):
        return object()

    def close(self):
        self.closed = True


class LiveVideoTests(unittest.TestCase):
    def test_capture_continues_and_old_frames_are_bounded(self):
        screen = FakeScreen()
        ready = threading.Event()
        live = LiveVideo(lambda: screen, lambda image: (ready.set(), image)[1], fps=40, seconds=.1).start()
        try:
            self.assertTrue(ready.wait(2))
            first_count = live.count
            # Simulate generation blocking the consumer while capture continues.
            time.sleep(.4)
            self.assertGreater(live.count, first_count+5)
            self.assertLessEqual(len(live.frames), 6)
            clip = live.latest()
            self.assertGreaterEqual(len(clip), 2)
            self.assertLessEqual(len(clip), 4)
            self.assertEqual(clip[-1][2], live.count)
            self.assertLess(time.monotonic()-clip[-1][0], .2)
            self.assertGreater(clip[0][2], first_count)
        finally:
            live.close()
        self.assertTrue(screen.closed)
        self.assertFalse(live.thread.is_alive())

    def test_capture_error_is_visible_and_screen_is_closed(self):
        screen = FakeScreen()

        def fail(image):
            raise ValueError("capture failed")

        live = LiveVideo(lambda: screen, fail).start()
        live.thread.join(timeout=2)
        live.close()
        self.assertIsInstance(live.error, ValueError)
        self.assertTrue(screen.closed)

    def test_close_allows_abandoning_a_stuck_capture(self):
        class StuckScreen(FakeScreen):
            def __init__(self):
                super().__init__()
                self.started = threading.Event()
                self.release = threading.Event()

            def grab(self):
                self.started.set()
                self.release.wait(10)
                return None

        screen = StuckScreen()
        live = LiveVideo(lambda: screen, lambda image: image).start()
        self.assertTrue(screen.started.wait(2))
        try:
            self.assertFalse(live.close())
            self.assertTrue(live.stop.is_set())
        finally:
            screen.release.set()
            live.thread.join(timeout=2)
        self.assertFalse(live.thread.is_alive())
        self.assertTrue(screen.closed)


if __name__ == "__main__":
    unittest.main()
