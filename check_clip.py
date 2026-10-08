# -*- coding: utf-8 -*-
"""体检脚本：检查源图角色有没有伸进右下角水印区（会被 _clean_watermark 削掉）。

用法：
    python check_clip.py [目录1 目录2 ...]     # 不带参数就查 SRC 里用到的目录

原理：
- 六张表情图身体相同，它们在水印区的不透明像素 = 水印图案本身；
- 拿它当模板（膨胀 9px 容差），其他图在水印区多出来的像素 = 角色被削的部分；
- >100 像素判为被削，需要按白边规范重出。
"""
import glob
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sprites")
WM_X, WM_Y = 0.60, 0.90          # 与 make_sprites.WATERMARK 保持一致
WM_PAD = (0.55, 0.85)            # 统计时向外扩一点


def alpha_of(path):
    """粗抠出不透明掩膜（不含抹水印），供统计用。"""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    rgb = im.copy()
    MAGIC = (255, 0, 254)
    for s in [(1, 1), (w - 2, 1), (1, h - 2), (w - 2, h - 2),
              (w // 2, 1), (w // 2, h - 2), (1, h // 2), (w - 2, h // 2)]:
        try:
            ImageDraw.floodfill(rgb, s, MAGIC, thresh=64)
        except Exception:
            pass
    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, MAGIC)).convert("L")
    return diff.point(lambda p: 0 if p < 8 else 255)


def first(d):
    pngs = sorted(glob.glob(os.path.join(BASE, d, "*.png")))
    return pngs[0] if pngs else None


def watermark_template():
    tpl = None
    for d in ("v7_expr_angry", "v7_expr_sad", "v7_expr_happy"):
        p = first(d)
        if not p:
            continue
        a = alpha_of(p)
        tpl = a if tpl is None else ImageChops.lighter(tpl, a)
    if tpl is None:
        raise SystemExit("找不到表情图，无法构造水印模板")
    return tpl.filter(ImageFilter.MaxFilter(9))


def check(d, tpl):
    p = first(d)
    if not p:
        print("%-16s 没有图片" % d)
        return
    a = alpha_of(p)
    extra = ImageChops.subtract(a, tpl)
    w, h = a.size
    region = extra.crop((int(w * WM_PAD[0]), int(h * WM_PAD[1]), w, h))
    n = sum(1 for v in region.getdata() if v)
    print("%-16s 水印区角色像素: %5d  %s" % (d, n, "<-- 被削，需重出" if n > 100 else "安全"))


if __name__ == "__main__":
    # 白底图：抠图时浅灰水印已随白底一起被 floodfill 吃掉，
    # 角落里的不透明像素 = 角色本体，而且流水线不会对它们抹水印（NO_WATERMARK）。
    WHITE_BG = {"v7_idle_hd2", "v7_sit2", "v7_eat2", "v8_peekL", "v8_peekB"}
    dirs = sys.argv[1:] or (list(WHITE_BG) + [
        "v7_expr_angry", "v7_expr_speechless", "v7_expr_sad",
        "v7_expr_sleepy", "v7_expr_happy", "v7_expr_smug"])
    tpl = watermark_template()
    for d in dirs:
        if d in WHITE_BG:
            print("%-16s 白底图（不抹水印）——角落像素属于角色，安全" % d)
        else:
            check(d, tpl)
