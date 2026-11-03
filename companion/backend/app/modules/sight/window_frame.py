"""Capture the selected HWND, not the pixels of whatever covers its rectangle."""
from __future__ import annotations

import os


def capture(hwnd: int):
    if os.name != "nt" or not hwnd:
        return None
    import ctypes
    from ctypes import wintypes
    from PIL import Image, ImageGrab

    user = ctypes.windll.user32
    gdi = ctypes.windll.gdi32
    user.GetForegroundWindow.restype = wintypes.HWND
    user.GetDC.restype = wintypes.HDC
    user.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi.CreateCompatibleDC.restype = wintypes.HDC
    gdi.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi.SelectObject.restype = wintypes.HGDIOBJ
    gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi.DeleteDC.argtypes = [wintypes.HDC]
    gdi.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                            ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
    if not user.IsWindow(hwnd) or not user.IsWindowVisible(hwnd) or user.IsIconic(hwnd):
        return None
    rect = wintypes.RECT()
    if not user.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if not (80 <= width <= 8192 and 80 <= height <= 8192):
        return None
    screen = user.GetDC(0)
    dc = gdi.CreateCompatibleDC(screen)
    bitmap = gdi.CreateCompatibleBitmap(screen, width, height)
    old = gdi.SelectObject(dc, bitmap)
    try:
        if user.PrintWindow(hwnd, dc, 2):
            class Header(ctypes.Structure):
                _fields_ = [("size", wintypes.DWORD), ("width", wintypes.LONG), ("height", wintypes.LONG),
                            ("planes", wintypes.WORD), ("bits", wintypes.WORD), ("compression", wintypes.DWORD),
                            ("image_size", wintypes.DWORD), ("xppm", wintypes.LONG), ("yppm", wintypes.LONG),
                            ("used", wintypes.DWORD), ("important", wintypes.DWORD)]
            header = Header(size=40, width=width, height=-height, planes=1, bits=32)
            pixels = ctypes.create_string_buffer(width * height * 4)
            if gdi.GetDIBits(dc, bitmap, 0, height, pixels, ctypes.byref(header), 0):
                image = Image.frombuffer("RGB", (width, height), pixels.raw, "raw", "BGRX", 0, 1)
                if max(image.convert("L").getextrema()) > 8:
                    return image.copy()
    finally:
        gdi.SelectObject(dc, old)
        gdi.DeleteObject(bitmap)
        gdi.DeleteDC(dc)
        user.ReleaseDC(0, screen)
    # Some DirectX windows cannot PrintWindow. Screen fallback is safe only
    # while that exact target is foreground, never when another app covers it.
    if int(user.GetForegroundWindow() or 0) == hwnd:
        image = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True)
        if int(user.GetForegroundWindow() or 0) == hwnd:
            return image
    return None
