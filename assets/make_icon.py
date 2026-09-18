"""Generates assets/glucopop.ico (multi-size) and glucopop.png with Pillow – no binary assets in git needed.

The mark is a drop with the TypeHealthy waves running through it, navy on white, matching the
brand set at typehealthy.com/about#marka. Two details are deliberate:

  * the waves are cut out of the drop in the background colour, so they read as water running
    through the shape rather than as stripes painted on top of it;
  * below 32 px three thin waves turn into grey mush, so the small sizes get a single wider
    wave. That is why `draw()` takes the size into account instead of scaling one drawing.
"""
from math import sin, pi
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
    from PIL import Image, ImageDraw

HERE = Path(__file__).parent

NAVY = (5, 10, 48, 255)
WHITE = (255, 255, 255, 255)
SS = 8          # supersampling factor: the curves are drawn big and shrunk, which is the whole
                # reason the edges look smooth at 16 px


def _drop(d: ImageDraw.ImageDraw, s: float, fill) -> None:
    """A teardrop: a circle for the bottom, a triangle for the point, sharing their width."""
    cx, top, bottom = s / 2, s * 0.10, s * 0.92
    r = s * 0.30
    cy = bottom - r
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill)
    d.polygon([(cx, top), (cx - r * 0.995, cy + r * 0.10), (cx + r * 0.995, cy + r * 0.10)], fill=fill)


def _wave(d: ImageDraw.ImageDraw, s: float, y: float, thickness: float, fill, phase: float = 0.0) -> None:
    """One horizontal band whose edges follow a sine, drawn wider than the icon so it runs off
    both sides rather than stopping inside the shape."""
    amp, wavelength, step = s * 0.055, s * 0.85, max(1.0, s / 120)
    xs = [x * step - s * 0.1 for x in range(int(s * 1.2 / step) + 1)]
    top = [(x, y + amp * sin(2 * pi * x / wavelength + phase)) for x in xs]
    bottom = [(x, ty + thickness) for x, ty in reversed(top)]
    d.polygon(top + bottom, fill=fill)


def draw(size: int) -> Image.Image:
    """The mark at one size, with a transparent background outside the drop."""
    s = size * SS
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    _drop(d, s, NAVY)

    if size <= 32:
        _wave(d, s, s * 0.56, s * 0.13, WHITE)
    else:
        for y in (0.34, 0.54, 0.74):
            _wave(d, s, s * y, s * 0.075, WHITE)

    # Keep the waves inside the drop: redraw the drop as a mask and clear everything outside it.
    mask = Image.new("L", (s, s), 0)
    _drop(ImageDraw.Draw(mask), s, 255)
    out = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    out.paste(layer, mask=mask)
    return out.resize((size, size), Image.LANCZOS)


def tile(size: int, bg=WHITE) -> Image.Image:
    """The app icon: the mark on a rounded square, which is what Windows shows."""
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.22), fill=bg)
    inner = int(s * 0.70)
    img.alpha_composite(draw(inner // SS).resize((inner, inner), Image.LANCZOS),
                        ((s - inner) // 2, (s - inner) // 2))
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [tile(z) for z in sizes]
    imgs[-1].save(HERE / "glucopop.png")
    imgs[-1].save(HERE / "glucopop.ico", sizes=[(z, z) for z in sizes], append_images=imgs[:-1])
    print("icon written")
