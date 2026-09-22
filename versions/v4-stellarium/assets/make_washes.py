"""Procedural watercolour textures for V4 (Stellarium-style). Generates RGBA PNGs with
pigment bleed, edge darkening, granulation and paper grain. Textures only — no drawn illustrations."""
import numpy as np, os
from PIL import Image, ImageFilter

OUT = os.path.dirname(os.path.abspath(__file__))
rng = np.random.default_rng(7)

def fbm(h, w, octaves=5, base=4, seed=0):
    r = np.random.default_rng(seed); acc = np.zeros((h, w)); amp = 1; tot = 0
    for o in range(octaves):
        n = base * (2 ** o)
        g = r.random((n + 1, n + 1))
        ys = np.linspace(0, n, h, endpoint=False); xs = np.linspace(0, n, w, endpoint=False)
        y0 = ys.astype(int); x0 = xs.astype(int); fy = (ys - y0)[:, None]; fx = (xs - x0)[None, :]
        fy = fy * fy * (3 - 2 * fy); fx = fx * fx * (3 - 2 * fx)
        a = g[y0][:, x0]; b = g[y0][:, x0 + 1]; c = g[y0 + 1][:, x0]; d = g[y0 + 1][:, x0 + 1]
        v = a * (1 - fx) * (1 - fy) + b * fx * (1 - fy) + c * (1 - fx) * fy + d * fx * fy
        acc += v * amp; tot += amp; amp *= .5
    return acc / tot

def blob_mask(h, w, seed, cx=.5, cy=.5, rx=.36, ry=.30, wobble=.35):
    yy, xx = np.mgrid[0:h, 0:w]; x = (xx / w - cx) / rx; y = (yy / h - cy) / ry
    ang = np.arctan2(y, x); r = np.sqrt(x * x + y * y)
    r_edge = 1 + wobble * (fbm(h, w, 4, 3, seed) - .5) * 2 + .12 * np.sin(ang * 3 + seed) + .08 * np.cos(ang * 5 - seed)
    return np.clip((r_edge - r) / .08, 0, 1)

def wash(name, rgb, w=1200, h=1200, layers=3, seed=1, dark_edge=.22, alpha=.85, shape=None):
    col = np.array(rgb, float) / 255
    acc = np.zeros((h, w));
    for i in range(layers):
        s = seed * 10 + i
        cx = .5 + (rng.random() - .5) * .18; cy = .5 + (rng.random() - .5) * .18
        m = blob_mask(h, w, s, cx, cy, rx=.34 - i * .04, ry=.30 - i * .03, wobble=.35 + i * .1)
        # edge darkening: pigment collects at the rim
        rim = np.clip((m - np.clip(m - .18, 0, 1)) * 1.6, 0, 1)
        gran = fbm(h, w, 6, 12, s + 99)
        layer = m * (.55 + .45 * gran) + rim * dark_edge
        acc = acc + layer * (1 - acc * .5)
    acc = np.clip(acc, 0, 1)
    if shape is not None: acc *= shape
    grain = fbm(h, w, 3, 40, seed + 500)
    a = np.clip(acc * alpha * (.85 + .3 * grain), 0, 1)
    # colour deepens where pigment is denser
    dens = np.clip(acc, 0, 1)[..., None]
    rgbimg = (1 - dens * .35) * col + dens * .35 * (col * .7)
    img = np.dstack([np.clip(rgbimg, 0, 1) * 255, a[..., None] * 255]).astype(np.uint8)
    im = Image.fromarray(img, 'RGBA').filter(ImageFilter.GaussianBlur(1.2))
    im.save(os.path.join(OUT, name), optimize=True); print('wrote', name)

wash('wash-yellow.png', (243, 228, 150), seed=1)
wash('wash-blue.png',   (176, 212, 236), seed=2)
wash('wash-pink.png',   (242, 200, 214), seed=3)
wash('wash-rose.png',   (238, 174, 190), seed=4)
wash('wash-green.png',  (196, 224, 190), seed=5)
wash('wash-violet.png', (208, 196, 234), seed=6)

# grey speckled band: wide, denser at bottom-right, with white star specks
h, w = 900, 1600
grad = np.linspace(0, 1, h)[:, None] * np.ones((1, w))
n = fbm(h, w, 6, 4, 77); n2 = fbm(h, w, 7, 30, 78)
dens = np.clip(.15 + .75 * grad * (.6 + .6 * n) + .15 * (n2 - .5), 0, 1)
grey = 1 - dens * .2
img = np.dstack([grey * 255, grey * 255, grey * 255, np.ones((h, w)) * 255]).astype(np.uint8)
im = Image.fromarray(np.ascontiguousarray(img), 'RGBA').copy()
px = im.load()
for _ in range(450):
    x = int(rng.random() * w); y = int(rng.random() ** .6 * h); r = 1 if rng.random() < .8 else 2
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if 0 <= x + dx < w and 0 <= y + dy < h and dx * dx + dy * dy <= r * r: px[x + dx, y + dy] = (255, 255, 255, 255)
im = im.filter(ImageFilter.GaussianBlur(.4)); im.save(os.path.join(OUT, 'band-grey.png'), optimize=True); print('wrote band-grey.png')

# paper grain tile
g = fbm(512, 512, 2, 128, 900)
tile = np.dstack([np.ones((512, 512)) * 0, np.ones((512, 512)) * 0, np.ones((512, 512)) * 0, np.clip((g - .5) * .5 + .04, 0, .09) * 255]).astype(np.uint8)
Image.fromarray(tile, 'RGBA').save(os.path.join(OUT, 'grain.png'), optimize=True); print('wrote grain.png')
