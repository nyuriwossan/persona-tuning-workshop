"""ホーム画面用アイコンを生成する（Pillowが必要）。python3 scripts/make_icons.py

元画像: scripts/icon-master-1024.png（1024x1024・不透明）を縮小するだけで、描き直しや角丸加工はしない。
maskable版だけは、Androidの円形マスクで図柄の端が欠けないよう、同じ画像を縮めて中央に置く。
縮めた分の余白は、縮めた画像の縁の色を外側へ延ばして軽くぼかしたもので埋める（継ぎ目が出ないようにするため）。
"""
from PIL import Image, ImageFilter
import os

HERE = os.path.dirname(__file__)
MASTER = os.path.join(HERE, 'icon-master-1024.png')
OUT = os.path.join(HERE, '..', 'icons')
os.makedirs(OUT, exist_ok=True)

# maskable: 図柄の最遠点が、安全領域（中心から幅の40%）に収まる縮小率
MASKABLE_SCALE = 0.72

master = Image.open(MASTER).convert('RGB')


def plain(size):
    return master.resize((size, size), Image.LANCZOS)


def extend_edges(img, m):
    """画像の縁の色（端4px分の平均）を、上下左右へ m px ずつ延ばす。"""
    w, h = img.size
    out = Image.new('RGB', (w + 2 * m, h + 2 * m))
    out.paste(img, (m, m))
    strips = {
        'top': (img.crop((0, 0, w, 4)).resize((w, 1), Image.BOX).resize((w, m), Image.NEAREST), (m, 0)),
        'bottom': (img.crop((0, h - 4, w, h)).resize((w, 1), Image.BOX).resize((w, m), Image.NEAREST), (m, h + m)),
        'left': (img.crop((0, 0, 4, h)).resize((1, h), Image.BOX).resize((m, h), Image.NEAREST), (0, m)),
        'right': (img.crop((w - 4, 0, w, h)).resize((1, h), Image.BOX).resize((m, h), Image.NEAREST), (w + m, m)),
    }
    for strip, pos in strips.values():
        out.paste(strip, pos)
    for (cx, cy), pos in [((0, 0), (0, 0)), ((w - 1, 0), (w + m, 0)), ((0, h - 1), (0, h + m)), ((w - 1, h - 1), (w + m, h + m))]:
        out.paste(Image.new('RGB', (m, m), img.getpixel((cx, cy))), pos)
    return out


def maskable(size):
    m = round(size * (1 - MASKABLE_SCALE) / 2)
    inner = size - 2 * m
    shrunk = master.resize((inner, inner), Image.LANCZOS)
    canvas = extend_edges(shrunk, m).filter(ImageFilter.GaussianBlur(size * 0.015))
    canvas.paste(shrunk, (m, m))
    return canvas


plain(192).save(os.path.join(OUT, 'icon-192.png'), optimize=True)
plain(512).save(os.path.join(OUT, 'icon-512.png'), optimize=True)
maskable(512).save(os.path.join(OUT, 'icon-maskable-512.png'), optimize=True)
plain(180).save(os.path.join(OUT, 'apple-touch-icon.png'), optimize=True)
plain(32).save(os.path.join(OUT, 'favicon-32.png'), optimize=True)
print('icons written to', os.path.abspath(OUT))
