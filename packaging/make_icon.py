# -*- coding: utf-8 -*-
"""生成应用图标 ``assets/app.ico``。

图标是**构建资产**，不是随手画的图：它决定窗口标题栏、任务栏与桌面快捷方式的
观感，所以这里用脚本生成而不是塞一个二进制进去——配色改了能重新跑一遍。

设计取了项目自己的视觉语言：朱砂底（``cinnabar-600`` #A63B2A）+ 宣纸色「道」。
单字印章的做法在 16px 下依然可辨，比缩成一团的图形标记更稳。

用法::

    python packaging/make_icon.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "app.ico"

#: 与前端 cinnabar-600 / paper-100 保持一致，避免图标和界面像两个产品
CINNABAR = (166, 59, 42)
PAPER = (247, 244, 236)
#: 图标要显示的尺寸集合；Windows 会按场合（任务栏 32、资源管理器 48/256）自行挑
SIZES = (16, 24, 32, 48, 64, 128, 256)
#: 单字；「道」比「导」更适合做标记，笔画少、识别度高
GLYPH = "道"

FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyhbd.ttc",   # 微软雅黑 Bold
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
)


def _load_font(px: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, px)
    raise SystemExit("[图标] 找不到可用的中文字体，无法生成「%s」字模" % GLYPH)


def _render(size: int) -> Image.Image:
    """画一张 ``size × size`` 的图。

    先按 4 倍分辨率绘制再缩回来——直接在小尺寸上画字，笔画边缘会有明显锯齿。
    """
    scale = 4
    canvas = size * scale
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # 圆角矩形底：半径取边长的 22%，接近 Windows 11 图标的观感
    radius = int(canvas * 0.22)
    draw.rounded_rectangle((0, 0, canvas - 1, canvas - 1), radius=radius, fill=CINNABAR)

    # 字模占满约 74%：留白太多在 16px 下会缩成一个小点
    font = _load_font(int(canvas * 0.74))
    left, top, right, bottom = draw.textbbox((0, 0), GLYPH, font=font)
    draw.text(
        ((canvas - (right - left)) / 2 - left, (canvas - (bottom - top)) / 2 - top),
        GLYPH,
        font=font,
        fill=PAPER,
    )
    return image.resize((size, size), Image.LANCZOS)


def main() -> int:
    frames = [_render(size) for size in SIZES]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # 以最大尺寸为基准写入多帧 ICO，其余尺寸由 Windows 按需取用
    frames[-1].save(OUT, format="ICO", sizes=[(s, s) for s in SIZES])
    print("[图标] 已生成 %s（%d 种尺寸，%d 字节）" % (OUT, len(SIZES), OUT.stat().st_size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
