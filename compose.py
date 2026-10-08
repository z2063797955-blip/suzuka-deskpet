# -*- coding: utf-8 -*-
"""桌宠贴图合成：底图 + 可选装饰件。

装饰系统目前是空的（comp_config.json 里 components = []）——
形象本身已经含鹿角，鱼尾暂时下架。以后想加任何挂件（帽子、披风、
小灯笼……），只要往 components 里加一条并放好 PNG 即可，代码不用动。
tune.py 和 deskpet.py 共用这一份逻辑，保证调试所见即所得。
"""
import json
import os
import glob
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
FIN_DIR = os.path.join(HERE, "sprites", "final")
CFG_FILE = os.path.join(HERE, "comp_config.json")

POSES = ("idle", "sit", "eat", "peek_left", "peek_bottom")
TIGHT = {"peek_left", "peek_bottom"}   # 紧贴裁切、不拼公共画布的贴边图（上边框动作已撤销）
TOP_PAD = 66        # 头顶留白：给气泡用
SIDE_PAD = 14
BOTTOM_PAD = 10


def load_config():
    with open(CFG_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    if isinstance(cfg.get("components"), dict):      # 兼容旧格式
        cfg["components"] = list(cfg["components"].values())
    cfg.setdefault("components", [])
    return cfg


def _prep(im, h, rot=0, flip=False):
    s = h / im.height
    im = im.resize((max(1, int(im.width * s)), int(h)), Image.LANCZOS)
    if flip:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    if rot:
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    return im


def load_assets(scale=1.0, cfg=None, pad_top=None):
    """读底图（含镜像版）和配置里启用的装饰件。scale 用于适配高 DPI。
    pad_top=None 用默认头顶留白（给气泡），传 0 则窗口紧贴角色。"""
    cfg = cfg or load_config()
    assets = {"poses": {}, "comp": {}, "cfg": cfg, "scale": scale}

    for p in POSES:
        path = os.path.join(FIN_DIR, p + ".png")
        if not os.path.exists(path):
            continue
        im = Image.open(path).convert("RGBA")
        if scale != 1.0:
            im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
        assets["poses"][p] = im
        assets["poses"][p + "_flip"] = im.transpose(Image.FLIP_LEFT_RIGHT)

    for c in cfg.get("components", []):
        path = os.path.join(FIN_DIR, c.get("file", ""))
        if c.get("file") and os.path.exists(path):
            assets["comp"][c["key"]] = Image.open(path).convert("RGBA")

    if assets["poses"]:
        solid = [assets["poses"][p] for p in POSES
                 if p in assets["poses"] and p not in TIGHT]
        base_h = max(im.height for im in solid)
        base_w = max(im.width for im in solid)
        top = TOP_PAD if pad_top is None else pad_top
        assets["canvas_h"] = base_h + int(top * scale) + int(BOTTOM_PAD * scale)
        assets["canvas_w"] = base_w + int(SIDE_PAD * 2 * scale)
    return assets


def compose(assets, pose, flip=False, decor=None):
    """合成一张成品。decor: {组件 key: 是否显示}，空字典就是纯底图。"""
    decor = decor or {}
    key = pose + ("_flip" if flip else "")
    base = assets["poses"].get(key) or assets["poses"].get(pose)
    if base is None:
        return None

    scale = assets.get("scale", 1.0)
    cfg = assets["cfg"]
    if pose in TIGHT:
        return base.copy()          # 贴边图：紧贴裁切，不加任何留白
    cw, ch = assets["canvas_w"], assets["canvas_h"]
    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))

    bx = (cw - base.width) // 2
    by = ch - int(BOTTOM_PAD * scale) - base.height

    def draw(comp, layer):
        p = comp.get("poses", {}).get(pose)
        if not p or comp["key"] not in assets["comp"]:
            return
        im = _prep(assets["comp"][comp["key"]], max(1, int(p["h"] * scale)),
                   p.get("rot", 0), p.get("flip", False))
        if flip and p.get("mirror_with_pose", True):
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        r = p["tx"] if not (flip and p.get("mirror_with_pose", True)) else 1.0 - p["tx"]
        layer.alpha_composite(im, (bx + int(r * base.width),
                                   by + int(p["ty"] * base.height)))

    behind = [c for c in cfg["components"] if decor.get(c["key"]) and c.get("layer") == "behind"]
    front = [c for c in cfg["components"] if decor.get(c["key"]) and c.get("layer") != "behind"]
    for c in behind:
        draw(c, canvas)
    canvas.alpha_composite(base, (bx, by))
    for c in front:
        draw(c, canvas)
    return canvas


# ---------------------------------------------------------------- 表情
def load_expressions(assets):
    """把 sprites/final/expr_*.png 收进 assets["expr"]，并读好表情名对照表。"""
    assets["expr"] = {}
    for path in sorted(glob.glob(os.path.join(FIN_DIR, "expr_*.png"))):
        key = os.path.basename(path)[len("expr_"):-len(".png")]
        im = Image.open(path).convert("RGBA")
        if assets.get("scale", 1.0) != 1.0:
            s = assets["scale"]
            im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
        assets["expr"][key] = im
    return assets["expr"]


def _face_region(im, top_frac=0.52):
    """角色头脸区：从角色包围盒顶部往下 top_frac 高、取全宽。
    表情差分与 idle 是同一个身体、同一套画布坐标，两图各自按自己的
    包围盒裁同一比例，就能天然对齐。"""
    bb = im.getchannel("A").getbbox()
    if not bb:
        return None
    x0, y0, x1, y1 = bb
    y1 = min(y1, y0 + int((y1 - y0) * top_frac))
    return (x0, y0, x1, y1)


def expression_frame(assets, key, pose="idle", zoom=False):
    """表情帧：只把表情差分的头脸区贴到姿势底图上，身体不动。
    贴片底边做羽化过渡，接缝落在两图完全相同的身体上，看不出痕迹。
    zoom 参数保留兼容，不再使用（凑近特写已按用户要求去掉）。"""
    im = assets.get("expr", {}).get(key)
    base = assets["poses"].get(pose) or assets["poses"].get("idle")
    if im is None or base is None:
        return None
    r_src = _face_region(im)
    r_dst = _face_region(base)
    if not r_src or not r_dst:
        return None
    face = im.crop(r_src)
    dw, dh = r_dst[2] - r_dst[0], r_dst[3] - r_dst[1]
    if face.size != (dw, dh):
        face = face.resize((dw, dh), Image.LANCZOS)

    # 底边羽化：往下 18% 线性淡出
    fw, fh = face.size
    feather = max(4, int(fh * 0.18))
    mask = Image.new("L", (fw, fh), 255)
    md = ImageDraw.Draw(mask)
    for i in range(feather):
        v = int(255 * (feather - 1 - i) / feather)
        md.line([(0, fh - feather + i), (fw, fh - feather + i)], fill=v)

    out = base.copy()
    out.paste(face, (r_dst[0], r_dst[1]), mask)

    scale = assets.get("scale", 1.0)
    cw, ch = assets["canvas_w"], assets["canvas_h"]
    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    by = ch - int(BOTTOM_PAD * scale) - out.height
    canvas.alpha_composite(out, ((cw - out.width) // 2, by))
    return canvas
