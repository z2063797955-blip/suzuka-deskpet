# -*- coding: utf-8 -*-
"""无窗自检：不显示窗口，验证贴边/表情/睡意/位置记忆几条链路。"""
import sys
import time

sys.path.insert(0, r"D:\1\Claw\deskpet")
import deskpet  # noqa: E402

deskpet.Pet._register_window = lambda self: setattr(self, "hwnd", 0)

p = deskpet.Pet()
print("1. 表情表:", sorted(p.assets["expr"]))
print("   起始位置:", p.x, p.y, "| 窗口:", p.cw, p.ch)

# --- 贴边：拖到左边
p.x, p.y = 2, 300
p._maybe_peek()
print("2. 贴边:", p.peek, "图:", p.pose, "窗口:", p.cw, p.ch, "x=", p.x)

# --- 贴边时做表情：应该先出边、再换脸
e = next(x for x in p.expr_defs if x["key"] == "happy")
p.play_expression(e, secs=0.4)
print("3. 贴边做表情 -> peek:", p.peek, "| expr:", p.expr, "| pose:", p.pose,
      "| 待返回边:", p._peek_return, "| x=", p.x)
im = p.frame()
print("   表情帧:", im.size if im else None)

# --- 表情过期后应自动躲回左边
time.sleep(0.6)
p.think(0.03)
print("4. 表情结束后 -> peek:", p.peek, "| pose:", p.pose, "| expr:", p.expr)

# --- 贴边时单击 = 自己出来，且不再自动躲回去
p._unpeek()
p._maybe_peek()
p._peek_return = "left"
p._wndproc(0, deskpet.WM_LBUTTONDOWN, 0, 0)
print("5. 手动抓取后 peek:", p.peek, "| 待返回边:", p._peek_return)

# --- 睡意：久无人理 -> 打瞌睡；再摸一下 -> 醒
p.dragging = False
p.bubble = None
p.expr = None
p.last_touch = time.time() - (p.SLEEP_AFTER + 5)
p.think(0.03)
print("6. 无人理:", p.sleeping, "| expr:", p.expr, "| pose:", p.pose,
      "| 睡姿帧:", (p.frame() or None) and (p.frame()).size)
p._touch()
print("   摸一下 -> 睡:", p.sleeping, "| expr:", p.expr)

# --- 位置记忆
p.peek = None
p.x, p.y = 321, 654
p._save_pos()
st = deskpet.load_state()
print("7. 存位置:", st.get("x"), st.get("y"))
p2 = deskpet.Pet()
print("   重开还原:", p2.x, p2.y)
p.peek = "left"
p._save_pos()
print("   贴边时不记录（还是上次的值）:", deskpet.load_state().get("x"), deskpet.load_state().get("y"))

# --- 自启开关检测
print("8. 自启快捷方式:", p._autostart_link(), "| 当前:", p._autostart_on())
print("OK")
