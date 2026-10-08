# -*- coding: utf-8 -*-
"""形象预览：四种姿势 + 表情差分（原样 / 凑近特写两个版本）。
改了 comp_config.json 或换了底图，跑一下就看得见，不烧积分。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image
import compose  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SCALE = 1.5
BG = (232, 236, 242, 255)


def strip(ims, gap=20, pad=20):
    ims = [i for i in ims if i]
    if not ims:
        return None
    W = sum(i.width for i in ims) + gap * (len(ims) + 1)
    H = max(i.height for i in ims) + pad * 2
    sheet = Image.new("RGBA", (W, H), BG)
    x = gap
    for i in ims:
        sheet.alpha_composite(i, (x, pad))
        x += i.width + gap
    return sheet


def main():
    assets = compose.load_assets(scale=SCALE)
    compose.load_expressions(assets)
    comps = assets["cfg"].get("components", [])
    decor = {c["key"]: True for c in comps}

    poses = [p for p in compose.POSES if p in assets["poses"]]
    rows = [strip([compose.compose(assets, p, decor=decor) for p in poses])]
    if "walk" in poses:
        rows.append(strip([compose.compose(assets, "walk", flip=True, decor=decor)]))

    keys = list(assets.get("expr", {}))
    if keys:
        rows.append(strip([compose.expression_frame(assets, k) for k in keys]))
        rows.append(strip([compose.expression_frame(assets, k, zoom=True) for k in keys]))

    rows = [r for r in rows if r]
    W = max(r.width for r in rows)
    H = sum(r.height for r in rows) + 20 * (len(rows) + 1)
    sheet = Image.new("RGBA", (W + 40, H), (245, 246, 250, 255))
    y = 20
    for r in rows:
        sheet.alpha_composite(r, (20, y))
        y += r.height + 20
    out = os.path.join(HERE, "sprites", "_tune.jpg")
    sheet.convert("RGB").save(out, quality=92)
    print("预览：", out)
    print("姿势：", sorted(assets["poses"]))
    print("表情：", keys or "（无）")
    print("装饰件：", [c["key"] for c in comps] or "（空）")


if __name__ == "__main__":
    main()
