# -*- coding: utf-8 -*-
"""让桌宠做个表情。

用法（在 deskpet.py 运行着的时候执行）：
    python send_expr.py 生气
    python send_expr.py 生气 "哼，不理你了"
    python send_expr.py angry "……" 5

原理：往 expr_trigger.json 写一条指令，桌宠主循环读到就做表情，
做完把指令文件删掉。所以哪怕桌宠没在跑，也只是文件先躺着，不会报错。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TRIGGER = os.path.join(HERE, "expr_trigger.json")


def main():
    expr = sys.argv[1] if len(sys.argv) > 1 else ""
    line = sys.argv[2] if len(sys.argv) > 2 else ""
    data = {"expr": expr}
    if line:
        data["line"] = line
    if len(sys.argv) > 3:
        try:
            data["secs"] = float(sys.argv[3])
        except ValueError:
            pass
    with open(TRIGGER, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print("已通知桌宠：", json.dumps(data, ensure_ascii=False))


if __name__ == "__main__":
    main()
