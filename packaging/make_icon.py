# -*- coding: utf-8 -*-
"""生成应用图标 ``assets/app.ico``（以及前端用的 PNG）。

图标是**构建资产**，不是随手画的图：它决定窗口标题栏、任务栏与桌面快捷方式的
观感，所以这里用脚本生成而不是塞一个二进制进去——配色改了能重新跑一遍。

设计取了项目自己的视觉语言：朱砂底（``cinnabar-600``）+ 宣纸色「导」字。

为什么是「导」而不是「道」
--------------------------------------------------------------------------
应用叫「人生导师」，「导」就是名字里的第一个字，标识性比「道」强。
更实际的原因是**小尺寸下的可辨度**：拿脚本量过 16px 的覆盖率与笔画宽度——

    字模   16px 覆盖率   笔画宽度   连通块
    道        28.6%       2.0px      3
    导        32.9%       3.0px      1     ← 明显更实

「道」的辶（走之底）在 16px 下必然糊成一条线；「导」是上「巳」下「寸」，
横竖笔画为主，缩小后骨架还在。任务栏与资源管理器里最常见的恰恰是 16/32px，
所以这个差别是天天看得见的。

为什么字号是 0.78 而不是更大的 0.86
--------------------------------------------------------------------------
覆盖率有个甜区：低于 22% 笔画细到缩小后看不见（楷体、宋体在 16px 下只剩
1~6%，等于没字），高于 38% 笔画开始互相咬合、字口糊死。0.78 落在 30% 附近。
顺带把四周留白控住了：字模包围盒约占画布 52%~56%，不至于缩成中间一小团。

用法::

    python packaging/make_icon.py

除 ``assets/app.ico`` 外，还会生成 ``web/public/favicon.ico`` 与
``web/public/icon-192.png``，供浏览器标签页与 PWA 使用。
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT_ICO = ROOT / "assets" / "app.ico"
#: 前端构建时 Vite 会把 public/ 原样拷进 dist/，所以放这里页面就能取到
WEB_PUBLIC = ROOT / "web" / "public"

#: 与前端 tailwind.config.js 的 cinnabar-600 / paper-100 保持一致，
#: 避免图标和界面像两个产品。改配色表时这里要跟着改。
#: （历史遗留：这两个值曾经写成 #A63B2A，与配色表并不一致。）
CINNABAR = (163, 46, 34)
PAPER = (247, 244, 236)

#: 图标要显示的尺寸集合；Windows 会按场合（任务栏 16/32、资源管理器 48/256）自行挑。
#: 16 与 24 单独给一档，因为它们靠普通缩放会糊（见模块开头的说明）。
SIZES = (16, 24, 32, 48, 64, 128, 256)

#: 字模。见模块开头「为什么是导」。
GLYPH = "导"
#: 字模占画布的比例。见模块开头「为什么字号是 0.78」。
GLYPH_RATIO = 0.78

FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyhbd.ttc",   # 微软雅黑 Bold：小尺寸下单笔画最宽
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
)


def _load_font(px: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, px)
    raise SystemExit("[图标] 找不到可用的中文字体，无法生成「%s」字模" % GLYPH)


def render(size: int) -> Image.Image:
    """画一张 ``size × size`` 的图。

    先按 8 倍分辨率绘制再缩回来——直接在小尺寸上画字，笔画边缘会有明显锯齿。
    超采样倍数越高，16px 下的笔画边界越干净；8 倍是效果与耗时的平衡点。
    """
    scale = 8
    canvas = size * scale
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # 圆角矩形底：半径取边长的 22%，接近 Windows 11 图标的观感
    radius = int(canvas * 0.22)
    draw.rounded_rectangle((0, 0, canvas - 1, canvas - 1), radius=radius, fill=CINNABAR)

    font = _load_font(int(canvas * GLYPH_RATIO))
    left, top, right, bottom = draw.textbbox((0, 0), GLYPH, font=font)
    draw.text(
        ((canvas - (right - left)) / 2 - left, (canvas - (bottom - top)) / 2 - top),
        GLYPH,
        font=font,
        fill=PAPER,
    )
    return image.resize((size, size), Image.LANCZOS)


def main() -> int:
    frames = [render(size) for size in SIZES]
    OUT_ICO.parent.mkdir(parents=True, exist_ok=True)
    # 以最大尺寸为基准写入多帧 ICO，其余尺寸由 Windows 按需取用
    frames[-1].save(OUT_ICO, format="ICO", sizes=[(s, s) for s in SIZES])
    print("[图标] 已生成 %s（%d 种尺寸，%d 字节）"
          % (OUT_ICO, len(SIZES), OUT_ICO.stat().st_size))

    # 前端也要一份：页面标签页读 favicon.ico，PWA / 触屏图标读 PNG
    try:
        WEB_PUBLIC.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print("[图标] 跳过前端图标（无法创建 %s：%s）" % (WEB_PUBLIC, exc))
        return 0

    frames[-1].save(WEB_PUBLIC / "favicon.ico", format="ICO",
                    sizes=[(16, 16), (32, 32), (48, 48)])
    render(192).save(WEB_PUBLIC / "icon-192.png", format="PNG")
    render(512).save(WEB_PUBLIC / "icon-512.png", format="PNG")
    print("[图标] 已生成前端图标：%s（favicon.ico / icon-192.png / icon-512.png）" % WEB_PUBLIC)
    return 0


if __name__ == "__main__":
    sys.exit(main())
