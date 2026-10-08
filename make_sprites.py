# -*- coding: utf-8 -*-
"""把 ImageGen 生成的原始立绘处理成桌宠可用的透明 PNG 精灵图。

v3 规则：
- 四个动作全部以 v3_ref 那张标准定妆图为参照生成（同一张脸、同一身衣服）；
- 鹿角画进本体，不再拆组件；鱼尾下架；
- 所有姿势用同一个缩放系数（不是各自撑满 240），并按底边对齐，
  这样"坐着"自然矮一截，走动/呼吸时不会大小乱跳。
步骤：抠背景 -> 裁到内容 -> 统一缩放 -> 贴到公共画布（水平居中、底边对齐）
"""
import os
import glob
from PIL import Image, ImageChops, ImageFilter, ImageDraw

BASE = r"D:\1\Claw\deskpet\sprites"
OUT = os.path.join(BASE, "final")
os.makedirs(OUT, exist_ok=True)

TARGET_H = 480            # 站姿的目标高度，作为基准（高清：给缩放留余量）
# 坐着的时候人头自然会低一截：坐/吃的图里角色画得偏满，
# 所以额外乘一个系数，让头落下来，别出现"坐下还跟站着一样高"
POSE_FACTOR = {
    "idle": 1.0,
    "sit": 0.70,
    "eat": 0.74,
}
# 表情差分的身体和 idle 完全一样，只换脸，所以必须和 idle 同比例
GAP_X = 10                # 画布左右各留一点，防止边缘被切
WATERMARK = (0.60, 0.90)  # 右下角水印起始比例 (x, y)

# 每张图的来源目录（都放一张图，取第一张）
# v8.2：上边框贴边撤销，peek_top 相关源图全部下架
SRC = {
    "idle": "v7_idle_hd2",
    "sit": "v7_sit2",
    "eat": "v7_eat2",
    "peek_left": "v8_peekL",
    "peek_bottom": "v8_peekB",
    "expr_angry": "v7_expr_angry",
    "expr_speechless": "v7_expr_speechless",
    "expr_sad": "v7_expr_sad",
    "expr_sleepy": "v7_expr_sleepy",
    "expr_happy": "v7_expr_happy",
    "expr_smug": "v7_expr_smug",
}

# 这些目录里的图不抹水印：
#   v7_ref —— 原始截图，本来就没水印；
#   白底图（*_2）—— 水印是浅灰色，抠图灌色时已和白底一起被吃掉，
#   再抹一次反而会把伸到底边的角色（尾巴/脚）削掉一块。
NO_WATERMARK = {"v7_ref", "v7_idle_hd2", "v7_sit2", "v7_eat2",
                "v8_peekL", "v8_peekB"}

# 贴边姿势：不打到公共画布上，直接输出紧贴裁切的小图（窗口 = 角色实际大小，
# 手就落在窗口边界上）；缩放也按 idle 的同一系数，保证头一样大。
TIGHT = {"peek_left", "peek_bottom"}


def picks(d):
    r = sorted(glob.glob(os.path.join(BASE, d, "*.png")))
    return r[0] if r else None


def border_colors(im, limit=3, tol=46):
    """从四边采样出背景主色。"""
    w, h = im.size
    pts = []
    for x in range(0, w, 13):
        pts.append(im.getpixel((x, 1)))
        pts.append(im.getpixel((x, h - 2)))
    for y in range(0, h, 13):
        pts.append(im.getpixel((1, y)))
        pts.append(im.getpixel((w - 2, y)))
    clusters = []
    for p in pts:
        p = p[:3]
        for c in clusters:
            if sum(abs(a - b) for a, b in zip(c["c"], p)) < tol:
                c["n"] += 1
                break
        else:
            clusters.append({"c": p, "n": 1})
    clusters.sort(key=lambda c: -c["n"])
    return [c["c"] for c in clusters[:limit]]


def _clean_watermark(im, off=True):
    """抹掉右下角水印。off=True 时跳过（比如来源不是 ImageGen 的图）。"""
    if not off:
        return im
    w, h = im.size
    a = im.getchannel("A")
    a.paste(0, (int(w * WATERMARK[0]), int(h * WATERMARK[1]), w, h))
    im.putalpha(a)
    return im


def knockout_mask(rgb, tol=18):
    """棋盘格背景：边框采样底色做掩膜，再从四边连通域填充，
    只吃与边缘相连的底色，不会挖穿人物内部。"""
    w, h = rgb.size
    bgs = border_colors(rgb, limit=3, tol=30) or [(255, 255, 255)]
    d = None
    for bg in bgs:
        dd = ImageChops.difference(rgb, Image.new("RGB", rgb.size, bg)).convert("L")
        d = dd if d is None else ImageChops.darker(d, dd)
    mask = d.point(lambda p: 0 if p <= tol else 255)
    for s in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
              (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]:
        if mask.getpixel(s) == 0:
            ImageDraw.floodfill(mask, s, 128, thresh=0)
    alpha = mask.point(lambda p: 0 if p == 128 else 255)
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.6))
    return Image.merge("RGBA", (*rgb.split(), alpha))


def to_rgba(im, checker=False, wm=True):
    """抠背景：从四边往中间灌色，人物描边挡住填充，纯色/渐变背景都能吃干净。"""
    rgb = im.convert("RGB").copy()
    w, h = rgb.size
    if checker:
        return _clean_watermark(knockout_mask(rgb), wm)

    if im.mode in ("RGBA", "LA"):
        a0 = im.getchannel("A")
        border = [a0.getpixel((x, 1)) for x in range(0, w, 13)]
        border += [a0.getpixel((1, y)) for y in range(0, h, 13)]
        if sum(border) / len(border) < 12:
            return _clean_watermark(im.convert("RGBA"), wm)

    px = rgb.load()
    MAGIC = (255, 0, 254)
    seeds = [(1, 1), (w - 2, 1), (1, h - 2), (w - 2, h - 2),
             (w // 2, 1), (w // 2, h - 2), (1, h // 2), (w - 2, h // 2),
             (w // 4, 1), (3 * w // 4, h - 2)]
    for s in seeds:
        if px[s[0], s[1]] != MAGIC:
            try:
                ImageDraw.floodfill(rgb, s, MAGIC, thresh=64)
            except Exception:
                pass

    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, MAGIC)).convert("L")
    alpha = diff.point(lambda p: 0 if p < 8 else 255)
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.6))
    # 灌色残留下来的"魔色"像素（RGB≈魔色）哪怕 alpha 很低，贴在深色壁纸上
    # 也会显出一条淡色的边——这里把它们连边一起抹干净。
    alpha = ImageChops.darker(alpha, diff.point(lambda p: 0 if p < 40 else 255))
    return _clean_watermark(Image.merge("RGBA", (*rgb.split(), alpha)), wm)


def _dark(a, px, x, y, thr=110):
    """该像素是不是"深色线条"候选（不透明 且 三通道都很暗）。"""
    if a.getpixel((x, y)) < 128:
        return False
    r, g, b = px[x, y][:3]
    return max(r, g, b) < thr


def find_edge_line(probe, side):
    """生成图里常会多画一条"边缘线"（代表屏幕边/栏杆）。
    在已抠好的图上定位它，返回 (lo, hi, 线的颜色)；找不到就返回 None。
    判据：贴着该边的那一条，深色像素占比最高的一段连续行/列。"""
    w, h = probe.size
    a = probe.getchannel("A").copy()
    px = probe.load()
    step = 2

    if side == "left":
        rng = range(0, max(2, min(int(w * 0.35), w)))
        fracs = [(i, sum(1 for t in range(0, h, step) if _dark(a, px, i, t)) /
                  (h / step)) for i in rng]
    else:
        n = max(2, min(int(h * 0.35), h))
        rng = range(0, n) if side == "top" else range(h - 1, h - 1 - n, -1)
        fracs = [(i, sum(1 for t in range(0, w, step) if _dark(a, px, t, i)) /
                  (w / step)) for i in rng]

    best, run = [], []
    for idx, f in fracs:
        if f > 0.45:
            run.append((idx, f))
        else:
            if sum(x[1] for x in run) > sum(x[1] for x in best):
                best = run
            run = []
    if sum(x[1] for x in run) > sum(x[1] for x in best):
        best = run
    if not best:
        return None

    idxs = sorted(i for i, _ in best)
    lo, hi = idxs[0], idxs[-1]
    short = w if side == "left" else h
    if hi - lo + 1 > max(6, int(short * 0.08)):     # 太粗，多半认错了
        return None

    mid = idxs[len(idxs) // 2]
    samples = []
    for t in range(0, (h if side == "left" else w), 5):
        x, y = (mid, t) if side == "left" else (t, mid)
        if _dark(a, px, x, y):
            samples.append(px[x, y][:3])
    if not samples:
        return None
    samples.sort(key=lambda c: sum(c))
    return lo, hi, samples[len(samples) // 2]


def erase_edge_line(rgb, side, lo, hi, lc, tol=110):
    """把边缘线连同两侧的抗锯齿灰边一起涂成纯白，交给后面的抠图吃掉。

    关键点：**只涂"线色"和"中性灰"**，绝不整行整列清空——她常常是
    抓在这条线上的，整列清空会把手指一起削掉一块（上一版就是这么缺的）。
    涂成白色而不是直接镂空，是为了让线后面的背景能跟外部背景连起来，
    否则线右边会留一条没抠掉的白底。"""
    w, h = rgb.size
    px = rgb.load()

    def near_line(c):
        return abs(c[0] - lc[0]) + abs(c[1] - lc[1]) + abs(c[2] - lc[2]) < tol

    for i in range(lo - 2, hi + 3):
        if not (0 <= i < (w if side == "left" else h)):
            continue
        rr = range(h) if side == "left" else range(w)
        for t in rr:
            x, y = (i, t) if side == "left" else (t, i)
            r, g, b = px[x, y][:3]
            mx, mn = max(r, g, b), min(r, g, b)
            if near_line((r, g, b)) or ((mx - mn) < 30 and mx < 225):
                px[x, y] = (255, 255, 255)


print("处理精灵图：")
cut = {}
for name, d in SRC.items():
    src = picks(d)
    if not src:
        print(f"  [跳过] {name}：{d}/ 里没有图")
        continue
    raw = Image.open(src)
    wm = d not in NO_WATERMARK
    if name in TIGHT:
        # 贴边图：先定位那条多画的边缘线，把它（连同灰边）涂白再抠图，
        # 这样线不残留、线背面那半张画布的白底也能一起被吃掉。
        side = {"peek_left": "left", "peek_bottom": "bottom"}[name]
        info = find_edge_line(to_rgba(raw, wm=False), side)
        if info:
            lo, hi, lc = info
            rgb = raw.convert("RGB").copy()
            erase_edge_line(rgb, side, lo, hi, lc)
            im = to_rgba(rgb, wm=wm)
            print(f"    剔掉边缘线（{side} 方向 {lo}-{hi} 号像素，只涂线色与灰边）")
        else:
            im = to_rgba(raw, wm=wm)
    else:
        im = to_rgba(raw, wm=wm)
    bb = im.getbbox()
    if bb:
        im = im.crop(bb)
    cut[name] = im
    print(f"  抠图 OK {name}: {im.size}  <- {os.path.basename(src)}")

if "idle" not in cut:
    raise SystemExit("没有 idle 底图，先在 sprites/v3_ref/ 放一张标准定妆图")

base_factor = TARGET_H / cut["idle"].height


def _scale(n, im):
    if n in TIGHT:
        f = base_factor                        # 贴边图：跟 idle 同一系数，头一样大
    else:
        f = TARGET_H * POSE_FACTOR.get(n, 1.0) / im.height
    return im.resize((max(1, int(im.width * f)), max(1, int(im.height * f))),
                     Image.LANCZOS)


scaled = {n: _scale(n, im) for n, im in cut.items()}

CW = max(im.width for n, im in scaled.items() if n not in TIGHT) + GAP_X * 2
CH = max(im.height for n, im in scaled.items() if n not in TIGHT)

print(f"按姿势归一高度（基准 {TARGET_H}），公共画布 {CW}x{CH}")
for name, im in scaled.items():
    if name in TIGHT:
        im.save(os.path.join(OUT, f"{name}.png"))
        print(f"  {name}.png {im.size}  (紧贴，不拼画布)")
        continue
    canvas = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    canvas.alpha_composite(im, ((CW - im.width) // 2, CH - im.height))  # 居中 + 底边对齐
    dst = os.path.join(OUT, f"{name}.png")
    canvas.save(dst)
    print(f"  {name}.png {canvas.size}  (角色 {im.size})")

print("完成，输出目录：", OUT)
