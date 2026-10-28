"""前台窗口。字从系统里读，截图只用来判断这块画面动没动。

不点、不敲、不改焦点。读不到就空着，不编。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field

_CODE = {
    "cursor.exe", "code.exe", "devenv.exe", "pycharm64.exe", "idea64.exe",
    "windowsterminal.exe", "cmd.exe", "powershell.exe", "pwsh.exe", "rider64.exe",
}
_SLIDES = {"powerpnt.exe", "wpp.exe"}
_DOCUMENT = {"winword.exe", "excel.exe", "notepad.exe", "et.exe", "wps.exe"}
_MUSIC = {"cloudmusic.exe", "spotify.exe", "qqmusic.exe", "kwmusic.exe", "kugou.exe"}
_MOVIE = {"potplayer.exe", "potplayermini64.exe", "potplayermini.exe", "vlc.exe", "mpc-hc64.exe", "mpv.exe"}
_BROWSER = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe"}
_SHELL = {
    "explorer.exe", "searchhost.exe", "startmenuexperiencehost.exe",
    "shellexperiencehost.exe", "textinputhost.exe", "applicationframehost.exe",
}
_APP = {
    "cursor.exe": "Cursor",
    "code.exe": "VS Code",
    "chrome.exe": "Chrome",
    "msedge.exe": "Edge",
    "firefox.exe": "Firefox",
    "cloudmusic.exe": "网易云音乐",
    "spotify.exe": "Spotify",
    "qqmusic.exe": "QQ音乐",
    "potplayer.exe": "PotPlayer",
    "potplayermini64.exe": "PotPlayer",
    "vlc.exe": "VLC",
}
_VIDEO_WORD = ("youtube", "youtu.be", "bilibili", "哔哩", "b站", "抖音", "douyin")
_MUSIC_WORD = ("网易云", "qq音乐", "spotify", "酷狗", "酷我", "歌词")
_TEXT_KIND = {"code", "slides", "document", "browser"}


@dataclass
class Desk:
    ok: bool = False
    app: str = ""
    process: str = ""
    window: str = ""
    title: str = ""
    kind: str = "unknown"
    texts: list[str] = field(default_factory=list)
    hwnd: int = 0

    @property
    def body(self) -> bool:
        return bool(self.texts)

    @property
    def named(self) -> bool:
        return bool(self.title)


def classify(process: str, title: str) -> str:
    """进程和窗口标题能确定的场景。确定不了就是 unknown，留给画面。"""
    name = (process or "").lower()
    blob = f"{name} {title or ''}".lower()
    if any(word in blob for word in _VIDEO_WORD):
        return "video"
    if name in _MUSIC or any(word in blob for word in _MUSIC_WORD):
        return "music"
    if name in _MOVIE:
        return "movie"
    if name in _CODE:
        return "code"
    if name in _SLIDES:
        return "slides"
    if name in _DOCUMENT:
        return "document"
    if name in _BROWSER:
        return "browser"
    return "unknown"


def short_title(window: str, app: str = "") -> str:
    raw = " ".join((window or "").split())
    if " - " not in raw:
        return raw
    left, right = raw.rsplit(" - ", 1)
    left, right = left.strip(), right.strip()
    if not left:
        return raw
    if app and app.lower() in right.lower():
        return left
    return left


def differ(previous: int | None, current: int | None) -> bool | None:
    """8×8 感知哈希。差得不多算没动；这一眼没截到就返回 None。"""
    if current is None:
        return None
    if previous is None:
        return True
    bits = bin(previous ^ current).count("1")
    return bits > 8


def read_foreground() -> Desk:
    if sys.platform != "win32":
        return Desk()
    try:
        return _read_win32()
    except Exception:
        return Desk()


class Motion:
    """前台窗口动没动。同一块几乎没变就别再送模型。"""

    def __init__(self) -> None:
        self._hash: int | None = None
        self._hwnd = 0

    def see(self, hwnd: int) -> str:
        """none 没有窗口，unseen 没截到，same 没动，moved 画面动了，switched 换了窗口。"""
        if not hwnd:
            return "none"
        digest = _hash_window(hwnd)
        switched = hwnd != self._hwnd
        self._hwnd = hwnd
        if digest is None:
            self._hash = None
            return "switched" if switched else "unseen"
        moved = differ(self._hash, digest)
        self._hash = digest
        if switched:
            return "switched"
        return "moved" if moved else "same"

    def reset(self) -> None:
        self._hash = None
        self._hwnd = 0


def window_box(hwnd: int) -> tuple[int, int, int, int] | None:
    """前台窗口在屏幕上的矩形。给眼睛裁画面用，失败就没有。"""
    if sys.platform != "win32" or not hwnd:
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass
    rect = wintypes.RECT()
    if not user32.GetWindowRect(int(hwnd), ctypes.byref(rect)):
        return None
    width, height = int(rect.right - rect.left), int(rect.bottom - rect.top)
    if width < 80 or height < 80:
        return None
    return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))


def grab_png(hwnd: int, edge: int = 768) -> bytes | None:
    """前台窗口压成一张 PNG。失败就没有图，不拿整屏顶上。"""
    frame = _grab(hwnd, edge)
    if frame is None:
        return None
    array, _digest = frame
    try:
        return _png(array)
    except Exception:
        return None


def _ime(window: str, process: str = "") -> bool:
    title = (window or "").strip()
    if title in _CHROME:
        return True
    return (process or "").lower() in {"ctfmon.exe"}


def _real_window(user32, hwnd: int) -> int:
    """桌宠在前台时，紧挨着的常是输入法空窗。跳过它，才看得到片子。"""
    for _ in range(24):
        hwnd = int(user32.GetWindow(hwnd, 2) or 0)
        if not hwnd:
            return 0
        if not user32.IsWindowVisible(hwnd):
            continue
        window = _window_text(hwnd)
        process = _process_name(hwnd)
        if _ours(window) or _ime(window, process):
            continue
        if (process or "").lower() in _SHELL and not window:
            continue
        box = window_box(hwnd)
        if box is None:
            continue
        width, height = box[2] - box[0], box[3] - box[1]
        if width < 200 or height < 200:
            continue
        return hwnd
    return 0


def _read_win32() -> Desk:
    import ctypes

    user32 = ctypes.windll.user32
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass
    hwnd = int(user32.GetForegroundWindow() or 0)
    if not hwnd:
        return Desk()
    process = _process_name(hwnd)
    window = _window_text(hwnd)
    if _ours(window) or _ime(window, process):
        nxt = _real_window(user32, hwnd)
        if not nxt:
            return Desk()
        hwnd = nxt
    return _desk_of(hwnd)


def _desk_of(hwnd: int) -> Desk:
    process = _process_name(hwnd)
    window = _window_text(hwnd)
    if (process or "").lower() in _SHELL and not window:
        return Desk(ok=True, process=process, kind="unknown", hwnd=hwnd)
    kind = classify(process, window)
    app = _APP.get((process or "").lower(), _stem(process))
    title = short_title(window, app)
    texts: list[str] = []
    if kind in _TEXT_KIND:
        texts = _body_texts(hwnd, title)
    return Desk(
        ok=True,
        app=app,
        process=process,
        window=window,
        title=title,
        kind=kind,
        texts=texts,
        hwnd=hwnd,
    )


def _ours(title: str) -> bool:
    blob = (title or "").lower()
    return "小可爱" in (title or "") or "xiaoke" in blob or "陪看记录" in (title or "")


def read_hwnd(hwnd: int) -> Desk:
    """读指定窗口，不改焦点。窗口没了就空。"""
    if sys.platform != "win32" or not hwnd:
        return Desk()
    try:
        import ctypes

        user32 = ctypes.windll.user32
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass
        if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
            return Desk()
        return _desk_of(int(hwnd))
    except Exception:
        return Desk()


def find_media_hwnd() -> int:
    """一起看时前台若是陪看页或编辑器，仍去找正在播的那一窗。"""
    if sys.platform != "win32":
        return 0
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        best = 0
        best_area = 0

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _each(hwnd, _lparam):
            nonlocal best, best_area
            hwnd = int(hwnd)
            if not user32.IsWindowVisible(hwnd):
                return True
            title = _window_text(hwnd)
            if not title or _ours(title):
                return True
            if not any(word in title.lower() for word in _VIDEO_WORD):
                return True
            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return True
            area = max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
            if area > best_area and area > 200 * 200:
                best = hwnd
                best_area = area
            return True

        user32.EnumWindows(_each, 0)
        return best
    except Exception:
        return 0


def _stem(process: str) -> str:
    name = (process or "").rsplit("\\", 1)[-1]
    if name.lower().endswith(".exe"):
        name = name[:-4]
    return name


def _process_name(hwnd: int) -> str:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    handle = kernel32.OpenProcess(0x1000, False, pid.value)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(520)
        size = wintypes.DWORD(520)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        return buf.value.rsplit("\\", 1)[-1]
    finally:
        kernel32.CloseHandle(handle)


def _window_text(hwnd: int) -> str:
    import ctypes

    user32 = ctypes.windll.user32
    buf = ctypes.create_unicode_buffer(300)
    user32.GetWindowTextW(hwnd, buf, 300)
    return " ".join(buf.value.split())


def _control_text(hwnd: int) -> str:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    buf = ctypes.create_unicode_buffer(200)
    got = wintypes.DWORD()
    user32.SendMessageTimeoutW(hwnd, 13, 200, buf, 2, 80, ctypes.byref(got))
    return " ".join(buf.value.split())[:180]


_CHROME = {"Chrome Legacy Window", "Default IME", "MSCTFIME UI", "CAscension"}


def _usable_text(text: str, title: str, window: str) -> bool:
    raw = (text or "").strip()
    if len(raw) < 2 or raw in _CHROME:
        return False
    if raw in {title, window}:
        return False
    if window and (raw == window or raw in window or window in raw):
        return False
    if title and (raw == title or raw.startswith(title)):
        return False
    return True


def _body_texts(hwnd: int, title: str) -> list[str]:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    window = _window_text(hwnd)
    found: list[str] = []

    def keep(text: str) -> None:
        if _usable_text(text, title, window) and text not in found and len(found) < 4:
            found.append(text)

    focus = _focused(hwnd)
    if focus:
        keep(_control_text(focus))

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _each(child, _lparam):
        if len(found) >= 4:
            return False
        keep(_control_text(int(child)))
        return True

    user32.EnumChildWindows(hwnd, _each, 0)
    return found


def _focused(hwnd: int) -> int:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32

    class GUITHREADINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("hwndActive", wintypes.HWND),
            ("hwndFocus", wintypes.HWND),
            ("hwndCapture", wintypes.HWND),
            ("hwndMenuOwner", wintypes.HWND),
            ("hwndMoveSize", wintypes.HWND),
            ("hwndCaret", wintypes.HWND),
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    info = GUITHREADINFO()
    info.cbSize = ctypes.sizeof(info)
    tid = user32.GetWindowThreadProcessId(hwnd, None)
    if not user32.GetGUIThreadInfo(tid, ctypes.byref(info)):
        return 0
    return int(info.hwndFocus or 0)


def _hash_window(hwnd: int) -> int | None:
    frame = _grab(hwnd, 32)
    if frame is None:
        return None
    _array, digest = frame
    return digest


def _grab(hwnd: int, edge: int):
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    width = int(rect.right - rect.left)
    height = int(rect.bottom - rect.top)
    if width < 80 or height < 80:
        return None
    step = max(1, int(max(width, height) / max(8, edge)))
    out_w = max(8, width // step)
    out_h = max(8, height // step)
    screen = user32.GetDC(0)
    if not screen:
        return None
    mem = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateCompatibleBitmap(screen, out_w, out_h)
    if not mem or not bitmap:
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if mem:
            gdi32.DeleteDC(mem)
        user32.ReleaseDC(0, screen)
        return None
    old = gdi32.SelectObject(mem, bitmap)
    try:
        gdi32.SetStretchBltMode(mem, 4)
        if not gdi32.StretchBlt(mem, 0, 0, out_w, out_h, screen, rect.left, rect.top, width, height, 0x00CC0020):
            return None
        return _bits(gdi32, mem, bitmap, out_w, out_h)
    finally:
        gdi32.SelectObject(mem, old)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(0, screen)


def _bits(gdi32, mem, bitmap, width: int, height: int):
    import ctypes
    from ctypes import wintypes

    class HEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    header = HEADER()
    header.biSize = ctypes.sizeof(HEADER)
    header.biWidth = width
    header.biHeight = -height
    header.biPlanes = 1
    header.biBitCount = 24
    header.biCompression = 0
    stride = ((width * 3 + 3) // 4) * 4
    buf = ctypes.create_string_buffer(stride * height)
    lines = gdi32.GetDIBits(mem, bitmap, 0, height, buf, ctypes.byref(header), 0)
    if not lines:
        return None
    import numpy as np

    raw = np.frombuffer(buf, dtype=np.uint8).reshape(height, stride)
    bgr = raw[:, : width * 3].reshape(height, width, 3)
    rgb = bgr[:, :, ::-1].copy()
    return rgb, _ahash(rgb)


def _ahash(rgb) -> int:
    import numpy as np

    gray = rgb.mean(axis=2)
    h, w = gray.shape
    ys = np.linspace(0, h, 9).astype(int)
    xs = np.linspace(0, w, 9).astype(int)
    value = 0
    cells = []
    for i in range(8):
        y0, y1 = int(ys[i]), max(int(ys[i + 1]), int(ys[i]) + 1)
        for j in range(8):
            x0, x1 = int(xs[j]), max(int(xs[j + 1]), int(xs[j]) + 1)
            cells.append(float(gray[y0:y1, x0:x1].mean()))
    mid = float(np.mean(cells))
    for cell in cells:
        value = (value << 1) | int(cell > mid)
    return value


def _png(rgb) -> bytes:
    import struct
    import zlib

    height, width = rgb.shape[:2]
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 3)) + chunk(b"IEND", b"")
