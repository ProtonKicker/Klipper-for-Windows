"""Generate the Klipper for Windows app icon.

Minimal reinterpretation of the Klipper for Mac icon: a 3D printer nozzle
viewed from underneath — rounded-square tile, two flat concentric rings,
an amber heated core, and a dark orifice dot. Flat colors, no gradients.

Outputs: Assets/appicon.ico (16-256) + preview PNG.
"""
from PIL import Image, ImageDraw
import os

S = 1024  # master size
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

R = 232  # tile corner radius (~23%, macOS-style squircle feel)

# tile: near-white with a hairline border for definition on dark taskbars
d.rounded_rectangle([0, 0, S - 1, S - 1], radius=R, fill=(250, 251, 252, 255),
                    outline=(225, 228, 231, 255), width=3)

cx = cy = S / 2

# nozzle body, viewed from underneath: two flat concentric rings
d.ellipse([cx - 340, cy - 340, cx + 340, cy + 340], fill=(228, 232, 235, 255))
d.ellipse([cx - 258, cy - 258, cx + 258, cy + 258], fill=(205, 211, 216, 255))

# heated core: amber disc (the hot end) with a dark orifice dot
d.ellipse([cx - 150, cy - 150, cx + 150, cy + 150], fill=(242, 158, 40, 255))
d.ellipse([cx - 44, cy - 44, cx + 44, cy + 44], fill=(43, 42, 46, 255))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)))
os.makedirs(os.path.join(out, "Assets"), exist_ok=True)

# master preview
img.save(os.path.join(out, "Assets", "icon-preview-256.png"))

# multi-resolution ico
ico_path = os.path.join(out, "Assets", "appicon.ico")
img.resize((256, 256), Image.LANCZOS).save(
    ico_path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                     (128, 128), (256, 256)])
print("wrote", ico_path)
