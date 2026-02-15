import ctypes
import json
import os
import sys
import time
import threading
from dataclasses import dataclass
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox

from pythonosc.udp_client import SimpleUDPClient
from pystray import Icon, MenuItem, Menu
from PIL import Image, ImageDraw

# =====================
# App meta
# =====================
APP_TITLE = "pad2osc"
VERSION = "1.0.0"

# =====================
# Path (exe対応)
# exe化したときは exe と同じフォルダに config.json を置く
# =====================
BASE_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"

# =====================
# GUI
# =====================

BUTTON_CHOICES = [
    ("None", 0),
    ("A", 0x1000),
    ("B", 0x2000),
    ("X", 0x4000),
    ("Y", 0x8000),
    ("LB", 0x0100),
    ("RB", 0x0200),
    ("Back", 0x0020),
    ("Start", 0x0010),
    ("LS (L3)", 0x0040),
    ("RS (R3)", 0x0080),
    ("DPad Up", 0x0001),
    ("DPad Down", 0x0002),
    ("DPad Left", 0x0004),
    ("DPad Right", 0x0008),
]

DEFAULT_CONFIG = {
    "vrc_ip": "127.0.0.1",
    "vrc_port": 9000,
    "hz": 60,

    "deadzone_left": 7849,
    "deadzone_right": 8689,
    "trigger_threshold": 30,

    "move_invert_y": False,
    "look_gain": 1.0,
    "look_invert_y": False,
    "curve_gamma": 1.0,

    "failsafe_timeout_sec": 0.25,

    "jump_button": "A",
    "voice_button": "Y",
    "voice_mode": "pulse",  # "pulse" or "hold"

    "enable_grab_triggers": True,
    "grab_left_addr": "/input/GrabLeft",
    "grab_right_addr": "/input/GrabRight",

    "addr_move_x": "/input/Horizontal",
    "addr_move_y": "/input/Vertical",
    "addr_look_x": "/input/LookHorizontal",
    "addr_look_y": "/input/LookVertical",
    "addr_jump": "/input/Jump",
    "addr_voice": "/input/Voice",

    "suppress_when_vrchat_foreground": True,
    "vrchat_process_name": "VRChat.exe",
}

def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(cfg: dict):
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

class App(tk.Toplevel):
    # ★exe統合のため Tk() ではなく Toplevel で開く（UI仕様は同じ）
    def __init__(self, master: tk.Tk):
        super().__init__(master)
        self.title("pad2osc - 設定")
        self.geometry("900x540")
        self.minsize(860, 500)

        self.cfg = load_config()
        self.vars = {}
        self._build()

        # 二重起動防止（同一プロセス内で複数開いてもOKだが、見た目が嫌ならここで制御可能）
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _combo_button(self, parent, var):
        values = [n.split()[0] for n, _ in BUTTON_CHOICES]
        return ttk.Combobox(parent, textvariable=var, values=values, width=10, state="readonly")

    def _row(self, parent, r, label, widget):
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", padx=(0,10), pady=4)
        widget.grid(row=r, column=1, sticky="we", pady=4)
        parent.grid_columnconfigure(1, weight=1)

    def _build(self):
        pad = 12
        root = ttk.Frame(self, padding=pad)
        root.pack(fill="both", expand=True)

        left = ttk.Frame(root)
        right = ttk.Frame(root)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, pad))
        right.grid(row=0, column=1, sticky="nsew")
        root.grid_columnconfigure(0, weight=1)
        root.grid_columnconfigure(1, weight=1)

        # ---- Left: Connection + Tuning ----
        lf_conn = ttk.Labelframe(left, text="接続", padding=pad)
        lf_conn.pack(fill="x", pady=(0, pad))

        self.vars["vrc_ip"] = tk.StringVar(value=self.cfg.get("vrc_ip", DEFAULT_CONFIG["vrc_ip"]))
        self.vars["vrc_port"] = tk.IntVar(value=int(self.cfg.get("vrc_port", DEFAULT_CONFIG["vrc_port"])))
        self.vars["hz"] = tk.IntVar(value=int(self.cfg.get("hz", DEFAULT_CONFIG["hz"])))

        self._row(lf_conn, 0, "VRChat IP", ttk.Entry(lf_conn, textvariable=self.vars["vrc_ip"], width=18))
        self._row(lf_conn, 1, "VRChat Port", ttk.Spinbox(lf_conn, from_=1, to=65535, textvariable=self.vars["vrc_port"], width=10))
        self._row(lf_conn, 2, "送信Hz", ttk.Spinbox(lf_conn, from_=10, to=240, textvariable=self.vars["hz"], width=10))

        # ★追加：前面抑制
        self.vars["suppress_when_vrchat_foreground"] = tk.BooleanVar(
            value=bool(self.cfg.get("suppress_when_vrchat_foreground", True))
        )
        ttk.Checkbutton(
            lf_conn,
            text="VRChatがアクティブならOSC送信しない",
            variable=self.vars["suppress_when_vrchat_foreground"],
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(6,0))

        self.vars["vrchat_process_name"] = tk.StringVar(value=str(self.cfg.get("vrchat_process_name", "VRChat.exe")))
        self._row(lf_conn, 4, "VRChatプロセス名", ttk.Entry(lf_conn, textvariable=self.vars["vrchat_process_name"], width=18))

        lf_tune = ttk.Labelframe(left, text="チューニング", padding=pad)
        lf_tune.pack(fill="both", expand=True)

        self.vars["deadzone_left"] = tk.IntVar(value=int(self.cfg.get("deadzone_left", DEFAULT_CONFIG["deadzone_left"])))
        self.vars["deadzone_right"] = tk.IntVar(value=int(self.cfg.get("deadzone_right", DEFAULT_CONFIG["deadzone_right"])))
        self.vars["trigger_threshold"] = tk.IntVar(value=int(self.cfg.get("trigger_threshold", DEFAULT_CONFIG["trigger_threshold"])))

        self.vars["move_invert_y"] = tk.BooleanVar(value=bool(self.cfg.get("move_invert_y", DEFAULT_CONFIG["move_invert_y"])))
        self.vars["look_gain"] = tk.DoubleVar(value=float(self.cfg.get("look_gain", DEFAULT_CONFIG["look_gain"])))
        self.vars["look_invert_y"] = tk.BooleanVar(value=bool(self.cfg.get("look_invert_y", DEFAULT_CONFIG["look_invert_y"])))
        self.vars["curve_gamma"] = tk.DoubleVar(value=float(self.cfg.get("curve_gamma", DEFAULT_CONFIG["curve_gamma"])))
        self.vars["failsafe_timeout_sec"] = tk.DoubleVar(value=float(self.cfg.get("failsafe_timeout_sec", DEFAULT_CONFIG["failsafe_timeout_sec"])))

        self._row(lf_tune, 0, "左デッドゾーン", ttk.Spinbox(lf_tune, from_=0, to=20000, textvariable=self.vars["deadzone_left"], width=10))
        self._row(lf_tune, 1, "右デッドゾーン", ttk.Spinbox(lf_tune, from_=0, to=20000, textvariable=self.vars["deadzone_right"], width=10))
        self._row(lf_tune, 2, "トリガ閾値", ttk.Spinbox(lf_tune, from_=0, to=255, textvariable=self.vars["trigger_threshold"], width=10))

        ttk.Checkbutton(lf_tune, text="移動Y反転", variable=self.vars["move_invert_y"]).grid(row=3, column=0, columnspan=2, sticky="w", pady=(6,0))
        ttk.Checkbutton(lf_tune, text="視点Y反転", variable=self.vars["look_invert_y"]).grid(row=4, column=0, columnspan=2, sticky="w")

        self._row(lf_tune, 5, "視点感度", ttk.Scale(lf_tune, from_=0.1, to=3.0, variable=self.vars["look_gain"], orient="horizontal"))
        self._row(lf_tune, 6, "カーブ γ（1.0=線形）", ttk.Scale(lf_tune, from_=1.0, to=2.4, variable=self.vars["curve_gamma"], orient="horizontal"))
        self._row(lf_tune, 7, "フェイルセーフ秒", ttk.Scale(lf_tune, from_=0.05, to=1.0, variable=self.vars["failsafe_timeout_sec"], orient="horizontal"))

        # ---- Right: Buttons + Addresses ----
        lf_btn = ttk.Labelframe(right, text="ボタン割り当て", padding=pad)
        lf_btn.pack(fill="x", pady=(0, pad))

        self.vars["jump_button"] = tk.StringVar(value=str(self.cfg.get("jump_button", DEFAULT_CONFIG["jump_button"])))
        self.vars["voice_button"] = tk.StringVar(value=str(self.cfg.get("voice_button", DEFAULT_CONFIG["voice_button"])))
        self.vars["voice_mode"] = tk.StringVar(value=str(self.cfg.get("voice_mode", DEFAULT_CONFIG["voice_mode"])))

        self._row(lf_btn, 0, "Jump", self._combo_button(lf_btn, self.vars["jump_button"]))
        self._row(lf_btn, 1, "Voice (Mic)", self._combo_button(lf_btn, self.vars["voice_button"]))

        voice_mode = ttk.Combobox(lf_btn, textvariable=self.vars["voice_mode"], values=["pulse", "hold"], width=10, state="readonly")
        self._row(lf_btn, 2, "Voice mode", voice_mode)
        ttk.Label(lf_btn, text='pulse=0→1→0（Toggle Voice向け） / hold=押してる間1（PTT向け）').grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(0,6)
        )

        self.vars["enable_grab_triggers"] = tk.BooleanVar(value=bool(self.cfg.get("enable_grab_triggers", True)))
        ttk.Checkbutton(lf_btn, text="トリガーでGrab（LT=Left / RT=Right）", variable=self.vars["enable_grab_triggers"]).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(6,0)
        )

        lf_addr = ttk.Labelframe(right, text="OSCアドレス", padding=pad)
        lf_addr.pack(fill="both", expand=True)

        for k, label, r in [
            ("addr_move_x", "Horizontal", 0),
            ("addr_move_y", "Vertical", 1),
            ("addr_look_x", "LookHorizontal", 2),
            ("addr_look_y", "LookVertical", 3),
            ("addr_jump", "Jump", 4),
            ("addr_voice", "Voice", 5),
        ]:
            self.vars[k] = tk.StringVar(value=str(self.cfg.get(k, DEFAULT_CONFIG[k])))
            self._row(lf_addr, r, label, ttk.Entry(lf_addr, textvariable=self.vars[k], width=36))

        bottom = ttk.Frame(root)
        bottom.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(pad,0))

        ttk.Button(bottom, text="読み込み", command=self.on_load).pack(side="left")
        ttk.Button(bottom, text="保存", command=self.on_save).pack(side="left", padx=(8,0))
        ttk.Button(bottom, text="デフォルト", command=self.on_default).pack(side="left", padx=(8,0))
        ttk.Label(bottom, text=f"保存先: {CONFIG_PATH.name}").pack(side="right")

    def gather(self) -> dict:
        cfg = {k: v.get() for k, v in self.vars.items()}

        for k in ["vrc_port", "hz", "deadzone_left", "deadzone_right", "trigger_threshold"]:
            cfg[k] = int(float(cfg[k]))
        for k in ["look_gain", "curve_gamma", "failsafe_timeout_sec"]:
            cfg[k] = float(cfg[k])
        for k in ["move_invert_y", "look_invert_y", "enable_grab_triggers", "suppress_when_vrchat_foreground"]:
            cfg[k] = bool(cfg[k])

        cfg["voice_mode"] = str(cfg.get("voice_mode", "pulse")).lower()
        if cfg["voice_mode"] not in ("pulse", "hold"):
            cfg["voice_mode"] = "pulse"

        cfg["grab_left_addr"] = DEFAULT_CONFIG["grab_left_addr"]
        cfg["grab_right_addr"] = DEFAULT_CONFIG["grab_right_addr"]
        return cfg

    def apply_cfg(self, cfg: dict):
        self.cfg = cfg
        for k, var in self.vars.items():
            if k in cfg:
                var.set(cfg[k])

    def on_load(self):
        self.apply_cfg(load_config())
        messagebox.showinfo("読み込み", "config.json を読み込みました。")

    def on_save(self):
        save_config(self.gather())
        messagebox.showinfo("保存", "config.json に保存しました。\n実行中なら自動で反映されます。")

    def on_default(self):
        self.apply_cfg(DEFAULT_CONFIG.copy())
        messagebox.showinfo("デフォルト", "デフォルト設定を読み込みました（未保存）。")

# =====================
# Engine (run.py の中身相当：前面抑制＋zero_all＋failsafe＋auto reload)
# =====================

def clamp(v: float, lo=-1.0, hi=1.0) -> float:
    return max(lo, min(hi, v))

def norm_thumb(v: int, deadzone: int) -> float:
    if abs(v) <= deadzone:
        return 0.0
    sign = 1.0 if v >= 0 else -1.0
    mag = (abs(v) - deadzone) / (32767 - deadzone)
    return clamp(sign * mag)

def norm_trigger(v: int, threshold: int) -> float:
    if v <= threshold:
        return 0.0
    return clamp((v - threshold) / (255 - threshold), 0.0, 1.0)

def apply_curve(v: float, gamma: float) -> float:
    s = 1.0 if v >= 0 else -1.0
    return s * (abs(v) ** gamma)

# Foreground process name (robust: QueryFullProcessImageNameW)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

GetForegroundWindow = user32.GetForegroundWindow
GetWindowThreadProcessId = user32.GetWindowThreadProcessId
OpenProcess = kernel32.OpenProcess
CloseHandle = kernel32.CloseHandle
QueryFullProcessImageNameW = kernel32.QueryFullProcessImageNameW

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

GetForegroundWindow.restype = ctypes.c_void_p
GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
GetWindowThreadProcessId.restype = ctypes.c_uint
OpenProcess.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_uint]
OpenProcess.restype = ctypes.c_void_p
CloseHandle.argtypes = [ctypes.c_void_p]
CloseHandle.restype = ctypes.c_int
QueryFullProcessImageNameW.argtypes = [
    ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint)
]
QueryFullProcessImageNameW.restype = ctypes.c_int

def foreground_process_name() -> str:
    hwnd = GetForegroundWindow()
    if not hwnd:
        return ""
    pid = ctypes.c_uint(0)
    GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == 0:
        return ""
    hproc = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid.value)
    if not hproc:
        return ""
    try:
        size = ctypes.c_uint(4096)
        buf = ctypes.create_unicode_buffer(size.value)
        ok = QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(size))
        if not ok:
            return ""
        path = buf.value
        return os.path.basename(path) if path else ""
    finally:
        CloseHandle(hproc)

# XInput
class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons", ctypes.c_ushort),
        ("bLeftTrigger", ctypes.c_ubyte),
        ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX", ctypes.c_short),
        ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short),
        ("sThumbRY", ctypes.c_short),
    ]

class XINPUT_STATE(ctypes.Structure):
    _fields_ = [("dwPacketNumber", ctypes.c_ulong), ("Gamepad", XINPUT_GAMEPAD)]

ERROR_SUCCESS = 0

def load_xinput():
    for name in ("xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"):
        try:
            return ctypes.WinDLL(name)
        except OSError:
            pass
    raise RuntimeError("XInput DLL not found")

XInput = load_xinput()
XInputGetState = XInput.XInputGetState
XInputGetState.argtypes = [ctypes.c_uint, ctypes.POINTER(XINPUT_STATE)]
XInputGetState.restype = ctypes.c_uint

def get_state(user_index: int):
    st = XINPUT_STATE()
    res = XInputGetState(user_index, ctypes.byref(st))
    return st if res == ERROR_SUCCESS else None

def find_first_controller():
    for i in range(4):
        if get_state(i) is not None:
            return i
    return None

BUTTON_MASKS = {
    "None": 0,
    "A": 0x1000, "B": 0x2000, "X": 0x4000, "Y": 0x8000,
    "LB": 0x0100, "RB": 0x0200,
    "Back": 0x0020, "Start": 0x0010,
    "LS": 0x0040, "RS": 0x0080,
    "Up": 0x0001, "Down": 0x0002, "Left": 0x0004, "Right": 0x0008,
}

def is_pressed(wButtons: int, name: str) -> int:
    mask = BUTTON_MASKS.get(name, 0)
    return 1 if (mask and (wButtons & mask)) else 0

@dataclass
class Mapped:
    move_x: float
    move_y: float
    look_x: float
    look_y: float
    jump: int
    voice_down: int
    grab_l: float
    grab_r: float

def map_state(st: XINPUT_STATE, cfg: dict) -> Mapped:
    gp = st.Gamepad

    lx = norm_thumb(gp.sThumbLX, cfg["deadzone_left"])
    ly = norm_thumb(gp.sThumbLY, cfg["deadzone_left"])
    rx = norm_thumb(gp.sThumbRX, cfg["deadzone_right"])
    ry = norm_thumb(gp.sThumbRY, cfg["deadzone_right"])

    move_x = lx
    move_y = -ly if cfg["move_invert_y"] else ly

    look_x = apply_curve(rx, cfg["curve_gamma"]) * cfg["look_gain"]
    look_y = apply_curve(ry, cfg["curve_gamma"]) * cfg["look_gain"]
    if cfg["look_invert_y"]:
        look_y *= -1.0

    jump = is_pressed(gp.wButtons, cfg["jump_button"])
    voice_down = is_pressed(gp.wButtons, cfg["voice_button"])

    if cfg["enable_grab_triggers"]:
        grab_l = norm_trigger(gp.bLeftTrigger, cfg["trigger_threshold"])
        grab_r = norm_trigger(gp.bRightTrigger, cfg["trigger_threshold"])
    else:
        grab_l = 0.0
        grab_r = 0.0

    return Mapped(move_x, move_y, look_x, look_y, jump, voice_down, grab_l, grab_r)

stop_event = threading.Event()

def engine_loop():
    cfg = load_config()
    mtime = CONFIG_PATH.stat().st_mtime if CONFIG_PATH.exists() else 0.0
    client = SimpleUDPClient(cfg["vrc_ip"], cfg["vrc_port"])
    idx = find_first_controller()

    prev_voice = 0
    voice_pulse_until = 0.0
    suppressed_prev = False
    last_ok = time.time()

    def osc_f(addr, val: float): client.send_message(addr, float(val))
    def osc_i(addr, val: int): client.send_message(addr, int(val))

    def zero_all():
        osc_f(cfg["addr_move_x"], 0.0)
        osc_f(cfg["addr_move_y"], 0.0)
        osc_f(cfg["addr_look_x"], 0.0)
        osc_f(cfg["addr_look_y"], 0.0)
        osc_i(cfg["addr_jump"], 0)
        osc_i(cfg["addr_voice"], 0)
        if cfg["enable_grab_triggers"]:
            osc_f(cfg["grab_left_addr"], 0.0)
            osc_f(cfg["grab_right_addr"], 0.0)

    while not stop_event.is_set():
        # auto reload config
        try:
            if CONFIG_PATH.exists():
                new_mtime = CONFIG_PATH.stat().st_mtime
                if new_mtime != mtime:
                    cfg = load_config()
                    client = SimpleUDPClient(cfg["vrc_ip"], cfg["vrc_port"])
                    mtime = new_mtime
        except Exception:
            pass

        # suppress when VRChat foreground
        if cfg.get("suppress_when_vrchat_foreground", True):
            fg = foreground_process_name()
            if fg.lower() == str(cfg.get("vrchat_process_name", "VRChat.exe")).lower():
                if not suppressed_prev:
                    zero_all()
                    prev_voice = 0
                    voice_pulse_until = 0.0
                suppressed_prev = True
                time.sleep(0.02)
                continue
            suppressed_prev = False

        if idx is None:
            idx = find_first_controller()
            time.sleep(0.2)
            continue

        st = get_state(idx)
        now = time.time()

        if st is None:
            if now - last_ok > float(cfg.get("failsafe_timeout_sec", 0.25)):
                zero_all()
            idx = find_first_controller()
            time.sleep(0.1)
            continue

        last_ok = now
        m = map_state(st, cfg)

        osc_f(cfg["addr_move_x"], m.move_x)
        osc_f(cfg["addr_move_y"], m.move_y)
        osc_f(cfg["addr_look_x"], m.look_x)
        osc_f(cfg["addr_look_y"], m.look_y)
        osc_i(cfg["addr_jump"], m.jump)

        # voice pulse/hold
        mode = str(cfg.get("voice_mode", "pulse")).lower()
        if mode == "hold":
            osc_i(cfg["addr_voice"], m.voice_down)
        else:
            if m.voice_down == 1 and prev_voice == 0:
                voice_pulse_until = now + 0.06
            osc_i(cfg["addr_voice"], 1 if now < voice_pulse_until else 0)
            prev_voice = m.voice_down

        if cfg.get("enable_grab_triggers", True):
            osc_f(cfg["grab_left_addr"], m.grab_l)
            osc_f(cfg["grab_right_addr"], m.grab_r)

        hz = int(cfg.get("hz", 60))
        time.sleep(max(0.001, 1.0 / hz))

# =====================
# Tray
# =====================

def create_tray_image():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((6, 6, 58, 58), radius=14, fill=(30, 30, 30, 255))
    d.ellipse((18, 18, 46, 46), fill=(0, 200, 255, 255))
    return img

def main():
    # Tk はメインスレッドに置く（Aboutが押せない問題の根治）
    root = tk.Tk()
    root.withdraw()

    # engine start
    th = threading.Thread(target=engine_loop, daemon=True)
    th.start()

    settings_window_ref = {"win": None}

    def open_settings(_icon, _item):
        def _():
            # 既に開いてるなら前面へ
            win = settings_window_ref["win"]
            if win is not None and win.winfo_exists():
                win.deiconify()
                win.lift()
                win.focus_force()
                return
            settings_window_ref["win"] = App(root)
        root.after(0, _)

    def show_about(_icon, _item):
        def _():
            root.attributes("-topmost", True)
            messagebox.showinfo(APP_TITLE, f"{APP_TITLE} Version {VERSION}\nby kaguyachan\nhttps://kaguyachan.net/", parent=root)
            root.attributes("-topmost", False)
        root.after(0, _)

    def do_exit(_icon, _item):
        def _():
            stop_event.set()
            try:
                icon.stop()
            except Exception:
                pass
            root.quit()
        root.after(0, _)

    icon = Icon(
        APP_TITLE,
        create_tray_image(),
        APP_TITLE,
        Menu(
            MenuItem("設定", open_settings),
            MenuItem("バージョン情報", show_about),
            MenuItem("終了", do_exit),
        ),
    )

    icon.run_detached()
    root.mainloop()

if __name__ == "__main__":
    main()

