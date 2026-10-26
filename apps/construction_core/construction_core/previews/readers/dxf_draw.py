"""DXF drawn with Pillow from the takeoff viewer's own parse (design §15.2; ``takeoff/dxf.py``, with its caps on size,
elements and block inserts): one ink colour, fitted to the drawing's extents, drawn at twice the size and scaled down.
Text is left out (the parse gives its place, not its shapes)."""

from PIL import Image, ImageDraw

from construction_core.previews.readers.common import BLANK, FAILED, TOO_LARGE, Refused, to_webp
from construction_core.takeoff import dxf

PAPER, INK = 255, 48  # grey levels: white paper, dark grey lines
MARGIN = 0.04


def render(fh, px: int):
	content = fh.read(dxf.MAX_BYTES + 1)
	if len(content) > dxf.MAX_BYTES:
		raise Refused(TOO_LARGE)
	try:
		parsed = dxf.parse(content)
	except dxf.DXFError as e:
		raise Refused(TOO_LARGE if "more than" in str(e) else FAILED) from None
	items = [i for i in parsed["items"] if i["t"] in ("l", "pl", "c")]
	if not items:
		raise Refused(BLANK)
	return to_webp(_draw(items, parsed["extents"], px * 2), px)


def _draw(items: list, extents: list, side: int):
	x0, y0, x1, y1 = extents
	span = max(x1 - x0, y1 - y0)
	if not span > 0:
		raise Refused(BLANK)
	scale = side * (1 - 2 * MARGIN) / span
	width = max(1, round((x1 - x0) * scale + side * 2 * MARGIN))
	height = max(1, round((y1 - y0) * scale + side * 2 * MARGIN))
	image = Image.new("L", (width, height), PAPER)
	pen = ImageDraw.Draw(image)
	offset = side * MARGIN

	def at(x, y):
		return (x - x0) * scale + offset, height - ((y - y0) * scale + offset)  # the drawing's y runs up

	for item in items:
		if item["t"] == "c":
			cx, cy = at(item["x"], item["y0"])
			r = item["r"] * scale
			if r > 0:
				pen.ellipse((cx - r, cy - r, cx + r, cy + r), outline=INK, width=2)
			continue
		p = item["p"]
		points = [at(p[i], p[i + 1]) for i in range(0, len(p) - 1, 2)]
		if item.get("c") and len(points) > 2:
			points.append(points[0])
		if len(points) >= 2:
			pen.line(points, fill=INK, width=2)
	if image.getextrema()[0] == PAPER:
		raise Refused(BLANK)
	return image
