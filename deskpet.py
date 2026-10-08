# -*- coding: utf-8 -*-
"""
铃鹿御前 · 桌面宠物 v7
================================
Q 版的铃鹿御前站在桌面上：会呼吸式起伏、会坐下发呆、
偶尔冒出气泡说话，右键能逗她（摸头 / 投喂 / 念记忆 / 做表情）。

v7 的改动：
- 形象以用户选定的标准图为蓝本（sprites/v7_ref/）；
- 走路动作撤销（太别扭），只留站 / 坐 / 吃 + 六张表情差分；
- 精灵图换成高清版（基准高度 480），idle 为重绘高清图；
- 新增缩放：鼠标滚轮直接调大小（0.5x - 2.5x），
  右键菜单也有 放大 / 缩小 / 恢复，缩放倍率会记住。

技术要点：
- Win32 分层窗口（UpdateLayeredWindow）做逐像素透明，透明处自动穿透点击；
- 精灵图在 sprites/final/，台词在 lines.json，表情表在 expressions.json。
"""

import os
import sys
import json
import time
import math
import random
import glob
import shutil
import ctypes
from ctypes import wintypes

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import compose  # noqa: E402

SPRITE_DIR = os.path.join(HERE, "sprites", "final")
LINES_FILE = os.path.join(HERE, "lines.json")
STATE_FILE = os.path.join(HERE, "pet_state.json")
EXPR_FILE = os.path.join(HERE, "expressions.json")
TRIGGER_FILE = os.path.join(HERE, "expr_trigger.json")
MEM_DIR = r"D:\1\Claw\.workbuddy\memory"

# ---------------------------------------------------------------- Win32 接口
user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t

WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000
WS_POPUP = 0x80000000
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010

WM_DESTROY = 0x0002
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_MOUSEMOVE = 0x0200
WM_RBUTTONUP = 0x0205
WM_LBUTTONDBLCLK = 0x0203
WM_MOUSEWHEEL = 0x020A
SWP_NOMOVE = 0x0002

MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
MF_CHECKED = 0x00000008
MF_GRAYED = 0x00000001
MF_POPUP = 0x00000010
TPM_RETURNCMD = 0x0100
TPM_RIGHTBUTTON = 0x0002
CS_DBLCLKS = 0x0008
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT), ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
    ]


WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, WPARAM, LPARAM)

user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]
user32.RegisterClassW.restype = wintypes.ATOM
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.LoadCursorW.restype = wintypes.HANDLE
user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
user32.UpdateLayeredWindow.restype = wintypes.BOOL
user32.UpdateLayeredWindow.argtypes = [
    wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
    ctypes.POINTER(wintypes.SIZE), wintypes.HDC, ctypes.POINTER(wintypes.POINT),
    wintypes.DWORD, ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD,
]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateDIBSection.argtypes = [
    wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
    ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD,
]
user32.SetWindowPos.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, wintypes.UINT,
]
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.GetDC.restype = wintypes.HDC
user32.GetDC.argtypes = [wintypes.HWND]
user32.ReleaseDC.restype = ctypes.c_int
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.SetCapture.argtypes = [wintypes.HWND]
user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                wintypes.UINT, wintypes.UINT, wintypes.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
user32.TrackPopupMenu.restype = ctypes.c_int
user32.TrackPopupMenu.argtypes = [
    wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, wintypes.HWND, ctypes.POINTER(wintypes.RECT),
]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = [wintypes.HDC]


# ---------------------------------------------------------------- 资源
def find_font(size):
    for name in ("msyh.ttc", "msyhbd.ttc", "simhei.ttf", "simsun.ttc"):
        p = os.path.join(r"C:\Windows\Fonts", name)
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def load_lines():
    if os.path.exists(LINES_FILE):
        try:
            with open(LINES_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                return d
        except Exception:
            pass
    return {"idle": ["……"], "pet": ["……"], "feed": ["……"], "talk": ["……"]}


def load_expr_defs():
    """表情表：key / 菜单名 / 关键词匹配 / 说的话 / 展示秒数。"""
    try:
        with open(EXPR_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        out = [e for e in d.get("expressions", []) if e.get("key")]
        for e in out:
            e.setdefault("name", e["key"])
            e.setdefault("secs", 4.5)
            e.setdefault("say", ["……"])
        return out
    except Exception:
        return []


def memory_lines():
    """从记忆文件里捡句子——桌宠和本体共用一份记忆。"""
    try:
        files = sorted(glob.glob(os.path.join(MEM_DIR, "20*.md")))
        out = []
        for f in files[-3:]:
            with open(f, "r", encoding="utf-8") as fh:
                for ln in fh:
                    ln = ln.strip()
                    if ln.startswith("- ") and len(ln) > 8:
                        out.append(ln[2:])
        return out
    except Exception:
        return []


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(st):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ---------------------------------------------------------------- 桌宠
class Pet:
    CMD_PET, CMD_FEED, CMD_TALK, CMD_MEM = 1, 2, 3, 4
    CMD_ZOOM_IN, CMD_ZOOM_OUT, CMD_ZOOM_RESET = 5, 6, 7
    CMD_BUBBLE, CMD_QUIT = 8, 9
    CMD_AUTOSTART = 10
    CMD_DECOR_BASE = 100          # 装饰开关的编号从这里开始往后排
    CMD_EXPR_BASE = 200           # 表情的编号从这里开始往后排
    ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 0.3, 2.5, 0.125
    SLEEP_AFTER = 300             # 多久没人搭理就打瞌睡（秒）
    # 贴边：每个边用哪张图、要不要镜像、气泡放哪边（上边框动作已按需求撤销）
    PEEK_SIDE = {
        "left":   ("peek_left", False),
        "right":  ("peek_left", True),
        "bottom": ("peek_bottom", False),
    }
    PEEK_BUBBLE = {"left": "bottom", "right": "bottom", "bottom": "top"}

    def __init__(self):
        try:
            ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
        except Exception:
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass
        try:
            dpi = user32.GetDpiForSystem()
        except Exception:
            dpi = 96
        self.base_scale = max(1.0, dpi / 96.0) * 0.85
        self.state_flags = load_state()
        self.zoom = float(self.state_flags.get("zoom", 1.0))
        self.peek = None            # None / left / right / bottom：贴边收起状态
        self.sleeping = False       # 久无人理 → 打瞌睡（sleepy 差分贴在坐姿上）
        self.expr_pose = "idle"     # 表情贴在哪张姿势上
        self.last_touch = time.time()
        self._peek_return = None    # 做表情临时出边后，要躲回的那条边

        self._apply_scale(reload=False)
        self.lines = load_lines()
        self.mem_lines = memory_lines()
        self.frame_cache = {}
        self.screen_w = user32.GetSystemMetrics(0)
        self.screen_h = user32.GetSystemMetrics(1)
        # 上次关在哪儿，这次就放回哪儿（没记录或位置已失效 → 默认右下角）
        self.x, self.y = self._restore_pos()

        self.pose = "idle"
        self.flip = False
        self.pose_until = time.time() + 8
        self.dir = 1
        self.bob_t = 0.0
        self.bubble = None
        self.bubble_until = 0.0
        self.next_talk = time.time() + random.uniform(90, 240)
        self.dragging = False
        self.moved = False
        self.drag_dx = self.drag_dy = 0
        self.running = True
        self._bubble_buf = None
        self.expr_defs = load_expr_defs()
        self.expr = None
        self.expr_until = 0.0
        self._trigger_stamp = None

        self._proc_ref = WNDPROC(self._wndproc)
        self._register_window()
        self.render()

    # ------------------------------------------------------------ 缩放
    def _decide_bubble(self):
        """气泡放头顶还是脚下：贴边时按边定，平时按缩放/用户锁定。"""
        if self.peek:
            self.bubble_at_bottom = (self.PEEK_BUBBLE[self.peek] == "bottom")
            return
        mode = self.state_flags.get("bubble_pos", "auto")
        self.bubble_at_bottom = (mode == "bottom" or
                                  (mode == "auto" and self.zoom < 0.85))

    def _apply_scale(self, reload=True):
        """按 base_scale × zoom 重载精灵与窗口尺寸。"""
        self.scale = self.base_scale * self.zoom
        self._decide_bubble()
        # 字号与缩放脱钩：越缩越小的时候，字号反而要往上抬（最小字号放大），
        # 免得缩到 30% 时气泡糊成一团看不清。
        gap = max(0.0, 0.85 - self.zoom)
        min_font = int(14 + gap * 16)          # 0.85→14，0.3→约 22
        self._font = find_font(max(min_font, min(28, int(15 * self.scale / 0.85))))
        # 气泡在脚下时，角色画布不再需要头顶留白——窗口紧贴她
        self.assets = compose.load_assets(
            scale=self.scale, pad_top=(0 if self.bubble_at_bottom else None))
        if not self.assets["poses"]:
            raise SystemExit("找不到精灵图，先跑 make_sprites.py")
        # 表情贴片必须跟着 assets 一起重载：load_assets 每次都会生成全新
        # assets（没有 expr 表），漏了这步的话，任何一次缩放/换气泡位置/
        # 贴边都会让表情菜单静默失效。
        compose.load_expressions(self.assets)
        self._layout()
        if reload and getattr(self, "frame_cache", None):
            self.frame_cache.clear()

    def _layout(self):
        """窗口尺寸 = 角色 + 可选气泡区；贴边时窗口收缩成角色实际大小。"""
        self._decide_bubble()
        self.zone = int(self._font.size * 1.4 * 3 + 24)
        if self.peek:
            base = self.assets["poses"].get(self.PEEK_SIDE[self.peek][0])
            if base is not None:
                self.cw = max(base.width, int(self._font.size * 6) + 30)
                self.ch = base.height + self.zone
                return
        aw, ah = self.assets["canvas_w"], self.assets["canvas_h"]
        if self.bubble_at_bottom:
            self.cw = max(aw, int(self._font.size * 8) + 44)
            self.ch = ah + self.zone
        else:
            self.cw, self.ch = aw, ah
            self.zone = 0

    def _relayout_window(self, reload=False):
        """气泡模式变化后重设窗口：锚住角色底部中心，不跳位。"""
        anchor = self.y + (self.ch - self.zone)
        cx = self.x + self.cw / 2
        if reload:
            self._apply_scale(reload=True)
        else:
            self._layout()
        self.x = cx - self.cw / 2
        self.y = anchor - (self.ch - self.zone)
        self._clamp()
        user32.SetWindowPos(self.hwnd, -1, int(self.x), int(self.y),
                            int(self.cw), int(self.ch), SWP_NOACTIVATE)

    def _snap_peek(self):
        """贴边时把窗口拉到屏幕边上（略微吃进去 2px，看起来是抓紧了）。"""
        inset = int(2 * self.base_scale)
        if self.peek == "left":
            self.x = -inset
        elif self.peek == "right":
            self.x = self.screen_w - self.cw + inset
        elif self.peek == "bottom":
            self.y = self.screen_h - self.ch + inset
        self._clamp()
        user32.SetWindowPos(self.hwnd, -1, int(self.x), int(self.y),
                            int(self.cw), int(self.ch), SWP_NOACTIVATE)

    def set_zoom(self, d):
        """调大小：锚住脚底中心，缩放时不跳位；倍率写进 pet_state.json。"""
        z = min(self.ZOOM_MAX, max(self.ZOOM_MIN, self.zoom + d))
        if abs(z - self.zoom) < 1e-6:
            return
        anchor = self.y + (self.ch - self.zone)
        cx = self.x + self.cw / 2
        self.zoom = z
        self._apply_scale(reload=True)
        self.state_flags["zoom"] = round(self.zoom, 3)
        save_state(self.state_flags)
        if self.peek:
            self._snap_peek()
        else:
            self.x = cx - self.cw / 2
            self.y = anchor - (self.ch - self.zone)
            self._clamp()
            user32.SetWindowPos(self.hwnd, -1, int(self.x), int(self.y),
                                int(self.cw), int(self.ch), SWP_NOACTIVATE)
        self._touch()
        self.say(f"大小 {int(self.zoom * 100)}%", 1.2)

    # ------------------------------------------------------------ 窗口
    def _register_window(self):
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.style = CS_DBLCLKS
        wc.lpfnWndProc = ctypes.cast(self._proc_ref, ctypes.c_void_p)
        wc.hInstance = hinst
        wc.hCursor = user32.LoadCursorW(None, ctypes.c_wchar_p(32512))
        wc.lpszClassName = "SuzukaGozenDeskPet"
        user32.RegisterClassW(ctypes.byref(wc))
        self.hwnd = user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_NOACTIVATE,
            "SuzukaGozenDeskPet", "铃鹿御前", WS_POPUP,
            self.x, self.y, self.cw, self.ch, None, None, hinst, None,
        )
        user32.ShowWindow(self.hwnd, 4)
        user32.SetWindowPos(self.hwnd, -1, self.x, self.y, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE)

    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_LBUTTONDOWN:
                self._peek_return = None      # 用户自己动手了，就别自作主张躲回去
                if self.peek:
                    self._unpeek()
                self.dragging = True
                self.moved = False
                pt = self._cursor()
                self.drag_dx, self.drag_dy = pt[0] - self.x, pt[1] - self.y
                user32.SetCapture(hwnd)
                return 0
            if msg == WM_LBUTTONDBLCLK:
                # 双击 = 摸头摸到高兴（单击那下已经打过招呼了）
                self.dragging = False
                user32.ReleaseCapture()
                self._touch()
                e = next((x for x in self.expr_defs if x["key"] == "happy"), None)
                if e:
                    self.play_expression(e, line=random.choice(
                        ["……又戳。", "摸头要收费的。", "行了，去忙你的吧。"]), secs=2.5)
                return 0
            if msg == WM_MOUSEMOVE and self.dragging:
                pt = self._cursor()
                nx, ny = pt[0] - self.drag_dx, pt[1] - self.drag_dy
                if abs(nx - self.x) + abs(ny - self.y) > 3:
                    self.moved = True
                self.x, self.y = nx, ny
                self._clamp()
                user32.SetWindowPos(hwnd, -1, int(self.x), int(self.y), 0, 0,
                                    SWP_NOSIZE | SWP_NOACTIVATE)
                return 0
            if msg == WM_LBUTTONUP:
                if self.dragging:
                    self.dragging = False
                    user32.ReleaseCapture()
                    if not self.moved:
                        self._touch()
                        self.say(self.pick("pet"), 3.0)
                        self.set_pose("idle", 2.0)
                    else:
                        self._save_pos()
                        self._maybe_peek()
                return 0
            if msg == WM_RBUTTONUP:
                self._touch()
                self.show_menu(hwnd)
                return 0
            if msg == WM_MOUSEWHEEL:
                delta = ctypes.c_short(wparam >> 16).value
                if delta:
                    self.set_zoom(self.ZOOM_STEP if delta > 0 else -self.ZOOM_STEP)
                return 0
            if msg == WM_DESTROY:
                self.running = False
                user32.PostQuitMessage(0)
                return 0
        except Exception:
            pass
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _cursor(self):
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y

    def _clamp(self):
        self.x = max(-40, min(self.x, self.screen_w - self.cw + 40))
        self.y = max(-20, min(self.y, self.screen_h - self.ch + 40))

    # ------------------------------------------------------------ 位置记忆 / 互动
    def _restore_pos(self):
        """上次待的位置；没有记录、或者那块屏幕已经不在了，就回默认右下角。"""
        dx = self.screen_w - self.cw - 60
        dy = self.screen_h - self.ch - 70
        try:
            sx, sy = self.state_flags.get("x"), self.state_flags.get("y")
            if sx is not None and sy is not None:
                sx, sy = int(sx), int(sy)
                if -self.cw + 40 < sx < self.screen_w - 40 and -20 < sy < self.screen_h - 40:
                    return sx, sy
        except Exception:
            pass
        return dx, dy

    def _save_pos(self):
        """记住位置（贴边的时候不记——那是临时姿势，不是她的家）。"""
        if self.peek or self.dragging:
            return
        self.state_flags["x"] = int(self.x)
        self.state_flags["y"] = int(self.y)
        save_state(self.state_flags)

    def _touch(self):
        """任何互动都算"搭理了她"：记时间，顺手叫醒。"""
        self.last_touch = time.time()
        if self.sleeping:
            self.sleeping = False
            self.expr = None
            self.expr_pose = "idle"
            self.say(random.choice(["……嗯？", "醒了醒了。", "谁叫我。"]), 2.0)

    # ------------------------------------------------------------ 开机自启
    def _startup_dir(self):
        return os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                            "Start Menu", "Programs", "Startup")

    def _autostart_link(self):
        return os.path.join(self._startup_dir(), "桌面宠物.lnk")

    def _autostart_on(self):
        return os.path.exists(self._autostart_link())

    def _toggle_autostart(self):
        """开/关开机自启：往启动文件夹里放（或删）一个快捷方式。"""
        link = self._autostart_link()
        try:
            if os.path.exists(link):
                os.remove(link)
                return False
            desk = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop", "桌面宠物.lnk")
            if os.path.exists(desk):
                shutil.copyfile(desk, link)      # 桌面那个快捷方式连图标一起搬
            else:
                import win32com.client
                ws = win32com.client.Dispatch("WScript.Shell")
                sc = ws.CreateShortcut(link)
                sc.TargetPath = os.path.join(HERE, "启动桌宠.bat")
                sc.WorkingDirectory = HERE
                sc.IconLocation = os.path.join(HERE, "deskpet.ico") + ",0"
                sc.Save()
            return True
        except Exception:
            return self._autostart_on()

    def show_menu(self, hwnd):
        menu = user32.CreatePopupMenu()
        items = [
            (self.CMD_PET, "摸摸头", False),
            (self.CMD_FEED, "投喂小鱼干", False),
            (self.CMD_TALK, "陪我说句话", False),
            (self.CMD_MEM, "念段记忆", False),
            (0, None, False),
        ]
        # 装饰开关：配置里有几个就列几个，没有就说明一下
        comps = self.assets["cfg"].get("components", [])
        if comps:
            for i, c in enumerate(comps):
                items.append((self.CMD_DECOR_BASE + i, c.get("name", c["key"]),
                              bool(self.state_flags.get(c["key"], True))))
        else:
            items.append((0, "装饰：暂未开放", False))
        if self.expr_defs:
            sub = user32.CreatePopupMenu()
            for i, e in enumerate(self.expr_defs):
                user32.AppendMenuW(sub, MF_STRING, self.CMD_EXPR_BASE + i, e["name"])
            items.append((-1, "做个表情", ctypes.cast(sub, ctypes.c_void_p).value))
        items += [
            (0, None, False),
            (self.CMD_ZOOM_IN, "放大一点", False),
            (self.CMD_ZOOM_OUT, "缩小一点", False),
            (self.CMD_ZOOM_RESET, "恢复大小", False),
            (self.CMD_BUBBLE, "气泡位置：" + {
                "auto": "自动", "top": "头顶", "bottom": "脚下"}.get(
                    self.state_flags.get("bubble_pos", "auto"), "自动"), False),
            (self.CMD_AUTOSTART, "开机自动启动", self._autostart_on()),
            (0, None, False),
            (self.CMD_QUIT, "退下吧", False),
        ]
        for cid, label, extra in items:
            if label is None:
                user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            elif isinstance(extra, bool):
                flags = MF_STRING | (MF_CHECKED if extra else 0)
                if cid == 0:
                    flags |= MF_GRAYED
                user32.AppendMenuW(menu, flags, cid, label)
            else:                                   # 子菜单（做个表情）
                user32.AppendMenuW(menu, MF_STRING | MF_POPUP, extra, label)
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        cmd = user32.TrackPopupMenu(menu, TPM_RETURNCMD | TPM_RIGHTBUTTON,
                                    pt.x, pt.y, 0, hwnd, None)
        user32.DestroyMenu(menu)
        self.do_cmd(cmd)

    def do_cmd(self, cmd):
        if cmd:
            self._touch()          # 点菜单也算搭理她（打瞌睡时会被叫醒）
        if cmd == self.CMD_PET:
            self.say(self.pick("pet"), 3.0)
        elif cmd == self.CMD_FEED:
            self.set_pose("eat", 3.5)
            self.say(self.pick("feed"), 3.5)
        elif cmd == self.CMD_TALK:
            self.say(self.pick("talk"), 5.0)
        elif cmd == self.CMD_MEM:
            if self.mem_lines:
                self.say("记着呢——" + random.choice(self.mem_lines), 7.0)
            else:
                self.say("账本还空着。", 4.0)
        elif cmd == self.CMD_ZOOM_IN:
            self.set_zoom(self.ZOOM_STEP)
        elif cmd == self.CMD_ZOOM_OUT:
            self.set_zoom(-self.ZOOM_STEP)
        elif cmd == self.CMD_ZOOM_RESET:
            self.set_zoom(1.0 - self.zoom)
        elif cmd == self.CMD_BUBBLE:
            cur = self.state_flags.get("bubble_pos", "auto")
            nxt = {"auto": "top", "top": "bottom", "bottom": "auto"}[cur]
            self.state_flags["bubble_pos"] = nxt
            save_state(self.state_flags)
            self._relayout_window(reload=True)
            self.say("气泡挪到" + {"auto": "自动（缩小时去脚下）",
                                  "top": "头顶", "bottom": "脚下"}[nxt], 2.5)
        elif cmd >= self.CMD_EXPR_BASE:      # 表情(200+) 必须排在装饰(100+)前面，否则会被装饰分支吃掉
            i = cmd - self.CMD_EXPR_BASE
            if 0 <= i < len(self.expr_defs):
                self.play_expression(self.expr_defs[i])
        elif cmd >= self.CMD_DECOR_BASE:
            comps = self.assets["cfg"].get("components", [])
            i = cmd - self.CMD_DECOR_BASE
            if 0 <= i < len(comps):
                k = comps[i]["key"]
                self.state_flags[k] = not self.state_flags.get(k, True)
                save_state(self.state_flags)
                name = comps[i].get("name", k)
                self.say(f"{name}{'戴好了' if self.state_flags[k] else '收起来了'}。", 3.0)
        elif cmd == self.CMD_AUTOSTART:
            on = self._toggle_autostart()
            self.say("记下了，开机我自己过来。" if on else "好，开机不打扰你。", 3.0)
        elif cmd == self.CMD_QUIT:
            self._save_pos()
            self.running = False

    # ------------------------------------------------------------ 贴边收起
    def _maybe_peek(self):
        """拖到屏幕边上，缩进侧边，只露头和扒边的手。
        上边框的动作已撤销：拖到屏幕顶端不再贴边。"""
        m = 34
        side = None
        if self.y >= self.screen_h - self.ch - m:
            side = "bottom"
        elif self.x <= m:
            side = "left"
        elif self.x >= self.screen_w - self.cw - m:
            side = "right"
        if side is None:
            return
        self._peek_to(side)

    def _peek_to(self, side, line=None):
        """贴到指定边去（拖过去判定到的边，或者做完表情自己躲回去）。"""
        self.peek = side
        self.pose = self.PEEK_SIDE[side][0]
        self.expr = None
        self.expr_pose = "idle"
        self.sleeping = False
        self.last_touch = time.time()
        self._apply_scale(reload=True)     # 换成紧贴窗口（头顶留白也要收掉）
        self._snap_peek()
        self.pose_until = time.time() + 1e9
        self.say(line or random.choice(["边上风大。", "……找到我了？", "这样看着你。",
                                        "暂时躲一会儿。", "就露个头。"]), 4.0)

    def _unpeek(self, step_out=False):
        """离开贴边状态。step_out=True 时顺便往屏幕里挪一点——用来做表情，
        不然她半个身子还在屏幕外，脸看不清。"""
        side = self.peek
        self.peek = None
        self._relayout_window(reload=True)
        if step_out and side:
            margin = 18
            if side == "left":
                self.x = margin
            elif side == "right":
                self.x = self.screen_w - self.cw - margin
            elif side == "bottom":
                self.y = self.screen_h - self.ch - margin
            self._clamp()
            user32.SetWindowPos(self.hwnd, -1, int(self.x), int(self.y),
                                int(self.cw), int(self.ch), SWP_NOACTIVATE)
        self.set_pose("idle", 3.0)

    # ------------------------------------------------------------ 表情
    def expr_active(self):
        return bool(self.expr) and time.time() < self.expr_until

    def resolve_expr(self, s):
        """按 key / 中文名 / 表情包文件名关键词找一条表情定义。"""
        s = (s or "").strip()
        if not s:
            return None
        for e in self.expr_defs:
            if s == e["key"] or s == e.get("name"):
                return e
        for e in self.expr_defs:
            for m in e.get("match", []) or []:
                if m and m in s:
                    return e
        return None

    def play_expression(self, e, line=None, secs=None):
        if isinstance(e, str):
            e = self.resolve_expr(e)
        if not e:
            return
        self._touch()
        self.expr_pose = "idle"
        if self.peek:
            # 贴边躲着时做表情：peek 图的脸是另一种画法，没法直接贴差分，
            # 所以先从边上缩回来露个脸，做完了自己躲回原来那条边。
            self._peek_return = self.peek
            self._unpeek(step_out=True)
        if e["key"] not in self.assets.get("expr", {}):
            return
        self.expr = e["key"]
        self.expr_until = time.time() + float(secs or e.get("secs", 4.5))
        self.bubble = line or random.choice(e.get("say") or ["……"])
        self.bubble_until = self.expr_until

    def poll_trigger(self):
        """看一眼 expr_trigger.json——我从聊天侧发表情时往这里写一条。"""
        if not os.path.exists(TRIGGER_FILE):
            self._trigger_stamp = None
            return
        try:
            stamp = os.path.getmtime(TRIGGER_FILE)
        except OSError:
            return
        if stamp == self._trigger_stamp:
            return
        self._trigger_stamp = stamp
        try:
            with open(TRIGGER_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            d = {}
        try:
            os.remove(TRIGGER_FILE)
        except OSError:
            pass
        if not isinstance(d, dict):
            return
        target = d.get("expr") or d.get("sticker") or ""
        e = self.resolve_expr(target)
        if e:
            self.play_expression(e, d.get("line"), d.get("secs"))

    # ------------------------------------------------------------ 行为
    def pick(self, key):
        return random.choice(self.lines.get(key) or ["……"])

    def say(self, text, secs=4.0):
        self.bubble = text
        self.bubble_until = time.time() + secs

    def set_pose(self, pose, dur):
        self.pose = pose
        self.pose_until = time.time() + dur

    def think(self, dt):
        now = time.time()
        self.poll_trigger()
        if self.expr and now > self.expr_until:
            self.expr = None
            self.sleeping = False
        # 表情做完了，自己躲回刚才那条边（用户自己动手就先取消，别把人拖回去）
        if (self._peek_return and not self.peek and not self.expr_active()
                and not self.dragging):
            side = self._peek_return
            self._peek_return = None
            self._peek_to(side, line=random.choice(["……说完了，我回去了。",
                                                    "没事，继续躲着。"]))
        if self.peek:
            self.pose = self.PEEK_SIDE[self.peek][0]
            self.pose_until = now + 3600.0
        elif self.sleeping:
            self.pose = self.expr_pose          # 坐着打盹，别站起来
            self.pose_until = now + 3600.0
            if random.random() < 0.02:
                self.say(random.choice(["……呼。", "zZZ", "别吵……"]), 3.0)
        elif self.expr_active():
            # 做表情的时候站定，别边做鬼脸边溜达
            self.pose = "idle"
            self.pose_until = max(self.pose_until, self.expr_until + 0.6)
        elif now > self.pose_until:
            r = random.random()
            if r < 0.22:
                self.set_pose("sit", random.uniform(8, 20))
            else:
                self.set_pose("idle", random.uniform(8, 20))

        # 久无人理 → 打个瞌睡（sleepy 差分贴在坐姿上，看着是真睡过去了）
        if (not self.peek and not self.sleeping and not self.dragging
                and not self.bubble and not self.expr_active()
                and now - self.last_touch > self.SLEEP_AFTER):
            self.sleeping = True
            self.expr_pose = "sit"
            self.expr = "sleepy" if "sleepy" in self.assets.get("expr", {}) else None
            self.expr_until = now + 1e9
            self.pose = "sit"
            self.pose_until = now + 1e9
            self.say(random.choice(["……呼。", "就眯一会儿。", "谁在叫我……"]), 3.0)

        if now > self.next_talk and not self.sleeping:
            self.next_talk = now + random.uniform(120, 300)
            if random.random() < 0.5:
                if self.mem_lines and random.random() < 0.4:
                    self.say("忽然想起来——" + random.choice(self.mem_lines), 6.0)
                else:
                    self.say(self.pick("idle"), 5.0)

        if self.bubble and now > self.bubble_until:
            self.bubble = None

    # ------------------------------------------------------------ 渲染
    def frame(self):
        if self.expr_active() and not self.peek:
            key = ("expr", self.expr, self.expr_pose)
            if key not in self.frame_cache:
                im = compose.expression_frame(self.assets, self.expr,
                                              pose=self.expr_pose)
                if len(self.frame_cache) > 24:
                    self.frame_cache.clear()
                self.frame_cache[key] = im
            im = self.frame_cache.get(key)
            if im is not None:
                return im

        flip = self.pose == "peek_left" and self.peek == "right"
        comps = self.assets["cfg"].get("components", [])
        decor = {c["key"]: self.state_flags.get(c["key"], True) for c in comps}
        key = (self.pose, flip, tuple(sorted(decor.items())))
        if key not in self.frame_cache:
            im = compose.compose(self.assets, self.pose, flip=flip, decor=decor)
            if len(self.frame_cache) > 24:
                self.frame_cache.clear()
            self.frame_cache[key] = im
        return self.frame_cache[key]

    def compose_canvas(self):
        base = self.frame()
        canvas = Image.new("RGBA", (self.cw, self.ch), (0, 0, 0, 0))
        if self.peek:
            # 贴边：角色紧贴所扒的那条边
            x0 = 0 if self.peek != "right" else self.cw - base.width
            y0 = 0 if self.bubble_at_bottom else self.ch - base.height
            canvas.alpha_composite(base, (x0, y0))
        else:
            bob = math.sin(self.bob_t * 2.0) * 2.2 if self.pose != "eat" else 0
            top = 0 if self.bubble_at_bottom else self.ch - base.height
            canvas.alpha_composite(base, ((self.cw - base.width) // 2, top + int(bob)))
        if self.bubble:
            self.draw_bubble(canvas)
        return canvas

    def draw_bubble(self, canvas):
        text = self.bubble
        font = self._font
        max_w = self.cw - 24
        lines, cur = [], ""
        for ch in text:
            if ch == "\n":
                lines.append(cur)
                cur = ""
                continue
            if font.getlength(cur + ch) > max_w - 24:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        if cur:
            lines.append(cur)
        lines = lines[:3]

        lh = int(font.size * 1.4)
        bw = int(max(font.getlength(l) for l in lines)) + 26
        bh = lh * len(lines) + 16
        bx = (self.cw - bw) // 2
        d = ImageDraw.Draw(canvas)
        tip_x = self.cw // 2

        if self.bubble_at_bottom:
            # 脚下模式：气泡贴底，小三角朝上指向角色
            by = self.ch - bh - 4
            d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=10,
                                 fill=(252, 250, 246, 238), outline=(122, 92, 70, 230), width=1)
            d.polygon([(tip_x - 6, by + 1), (tip_x + 6, by + 1), (tip_x, by - 7)],
                      fill=(252, 250, 246, 238), outline=(122, 92, 70, 230))
        else:
            by = 8
            d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=10,
                                 fill=(252, 250, 246, 238), outline=(122, 92, 70, 230), width=1)
            d.polygon([(tip_x - 6, by + bh - 1), (tip_x + 6, by + bh - 1), (tip_x, by + bh + 8)],
                      fill=(252, 250, 246, 238), outline=(122, 92, 70, 230))
        for i, ln in enumerate(lines):
            d.text((bx + 13, by + 8 + i * lh), ln, font=font, fill=(58, 46, 40, 255))

    def render(self):
        im = self.compose_canvas()
        w, h = im.size
        data = im.tobytes("raw", "BGRA")

        hdc_screen = user32.GetDC(None)
        memdc = gdi32.CreateCompatibleDC(hdc_screen)
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0

        ppv = ctypes.c_void_p()
        hbmp = gdi32.CreateDIBSection(hdc_screen, ctypes.byref(bmi), 0,
                                      ctypes.byref(ppv), None, 0)
        old = gdi32.SelectObject(memdc, hbmp)
        ctypes.memmove(ppv, data, len(data))

        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        size = wintypes.SIZE(w, h)
        src = wintypes.POINT(0, 0)
        user32.UpdateLayeredWindow(self.hwnd, hdc_screen, None, ctypes.byref(size),
                                   memdc, ctypes.byref(src), 0, ctypes.byref(blend), 2)

        gdi32.SelectObject(memdc, old)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(memdc)
        user32.ReleaseDC(None, hdc_screen)

    # ------------------------------------------------------------ 主循环
    def run(self):
        msg = wintypes.MSG()
        last = time.time()
        while self.running:
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                if msg.message == 0x0012:
                    self.running = False
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

            now = time.time()
            dt = now - last
            last = now
            self.bob_t += dt
            self.think(dt)
            self.render()
            # 静止时降帧：分层窗口每帧都是整幅重绘，闲着不必跑满 30fps
            busy = bool(self.bubble) or self.expr_active() or self.dragging
            time.sleep(1 / (30.0 if busy else 15.0))
        self._save_pos()


if __name__ == "__main__":
    Pet().run()
