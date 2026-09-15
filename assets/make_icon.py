"""Generates assets/glucopop.ico (multi-size) and glucopop.png with Pillow – no binary assets in git needed."""
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
    from PIL import Image, ImageDraw

HERE = Path(__file__).parent


def draw(size: int) -> Image.Image:
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.24), fill=(21, 24, 29, 255))
    # drop shape
    cx, top, bottom = s / 2, s * 0.14, s * 0.86
    r = s * 0.26
    d.ellipse((cx - r, bottom - 2 * r, cx + r, bottom), fill=(62, 194, 107, 255))
    d.polygon([(cx, top), (cx - r * 0.98, bottom - r * 1.15), (cx + r * 0.98, bottom - r * 1.15)], fill=(62, 194, 107, 255))
    # highlight
    hr = r * 0.28
    d.ellipse((cx - r * 0.45 - hr, bottom - r * 1.1 - hr, cx - r * 0.45 + hr, bottom - r * 1.1 + hr), fill=(255, 255, 255, 140))
    return img


if __name__ == "__main__":
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [draw(z) for z in sizes]
    imgs[-1].save(HERE / "glucopop.png")
    imgs[-1].save(HERE / "glucopop.ico", sizes=[(z, z) for z in sizes], append_images=imgs[:-1])
    print("icon written")
