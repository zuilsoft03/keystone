"""A small DXF (ASCII) reader for the takeoff viewer (P1-16, D-099; Q-12: DXF only).

It reads what a measuring viewer needs and nothing else: LINE, LWPOLYLINE (with bulge arcs), POLYLINE/VERTEX,
CIRCLE, ARC, TEXT, MTEXT, and INSERT of blocks (flattened, with scale and rotation). Output is plain geometry in
drawing units, plus the layers, the extents and the unit from ``$INSUNITS``:

    {"units": "mm", "unit_to_m": 0.001, "layers": [...], "extents": [x0, y0, x1, y1], "count": n,
     "items": [{"t": "l", "y": layer, "p": [x1, y1, x2, y2]},
               {"t": "pl", "y": layer, "p": [x, y, x, y, ...], "c": closed},
               {"t": "c", "y": layer, "x": cx, "y0": cy, "r": r},
               {"t": "tx", "y": layer, "x": x, "y0": y, "h": height, "a": degrees, "s": text}]}

Binary DXF and DWG are refused (DWG is converted to DXF first, Q-12).
"""

import math
import re

MAX_BYTES = 40 * 1024 * 1024
MAX_ITEMS = 300_000
MAX_BLOCK_DEPTH = 8
MAX_INSERTS = 100_000  # block inserts expanded in total: blocks that insert each other cannot multiply work
ARC_SEGMENTS = 48
INSUNITS = {1: ("in", 0.0254), 2: ("ft", 0.3048), 4: ("mm", 0.001), 5: ("cm", 0.01), 6: ("m", 1.0), 14: ("dm", 0.1)}
MTEXT_CODES = re.compile(r"\\[A-Za-z][^;\\]*;|\\[PpNn~]|[{}]")


class DXFError(ValueError):
	pass


def _pairs(text: str):
	lines = text.splitlines()
	if len(lines) % 2:
		lines = lines[:-1]
	for i in range(0, len(lines), 2):
		try:
			code = int(lines[i].strip())
		except ValueError as e:
			raise DXFError(f"Not a DXF text file (line {i + 1})") from e
		yield code, lines[i + 1].rstrip("\r")


def _float(v, default=0.0):
	try:
		f = float(v)
	except (TypeError, ValueError):
		return default
	return f if math.isfinite(f) else default  # NaN/inf would break the JSON the viewer reads


def _records(pairs):
	"""Split a section into records: each starts at group code 0."""
	current = None
	for code, value in pairs:
		if code == 0:
			if current is not None:
				yield current
			current = [(0, value.strip())]
		elif current is not None:
			current.append((code, value))
	if current is not None:
		yield current


def _sections(text):
	sections, name, buf = {}, None, []
	it = _pairs(text)
	for code, value in it:
		v = value.strip()
		if code == 0 and v == "SECTION":
			c2, v2 = next(it, (None, None))
			name, buf = (v2 or "").strip() if c2 == 2 else None, []
		elif code == 0 and v == "ENDSEC":
			if name:
				sections[name] = buf
			name, buf = None, []
		elif name:
			buf.append((code, value))
	return sections


def _get(rec, code, default=None):
	for c, v in rec:
		if c == code:
			return v
	return default


def _arc_points(cx, cy, r, a0, a1):
	a0, a1 = a0 % 360.0, a1 % 360.0  # angles beyond a turn would multiply the segment count
	if a1 <= a0:
		a1 += 360.0
	n = max(4, int(ARC_SEGMENTS * (a1 - a0) / 360.0))
	pts = []
	for i in range(n + 1):
		a = math.radians(a0 + (a1 - a0) * i / n)
		pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
	return pts


def _bulge_points(x1, y1, x2, y2, bulge):
	"""Points of the arc from (x1, y1) to (x2, y2) with the DXF bulge (tan of a quarter of the angle)."""
	d = math.hypot(x2 - x1, y2 - y1)
	if not bulge or d == 0:
		return [x2, y2]
	theta = 4 * math.atan(bulge)
	r = d / (2 * math.sin(theta / 2))
	mx, my = (x1 + x2) / 2, (y1 + y2) / 2
	h = r * math.cos(theta / 2)
	ux, uy = (y1 - y2) / d, (x2 - x1) / d  # left normal of the chord
	cx, cy = mx + ux * h, my + uy * h
	a0 = math.atan2(y1 - cy, x1 - cx)
	n = max(2, int(abs(theta) / (2 * math.pi) * ARC_SEGMENTS))
	pts = []
	for i in range(1, n + 1):
		a = a0 + theta * i / n
		pts += [cx + abs(r) * math.cos(a), cy + abs(r) * math.sin(a)]
	pts[-2:] = [x2, y2]
	return pts


def _entity_items(rec, layer_default="0"):
	"""Geometry items of one entity record (blocks are handled by the caller)."""
	kind = rec[0][1]
	layer = (_get(rec, 8) or layer_default).strip()
	if kind == "LINE":
		return [{"t": "l", "y": layer, "p": [_float(_get(rec, 10)), _float(_get(rec, 20)),
			_float(_get(rec, 11)), _float(_get(rec, 21))]}]
	if kind == "LWPOLYLINE":
		closed = bool(int(_float(_get(rec, 70), 0)) & 1)
		verts, bulges = [], []
		for c, v in rec:
			if c == 10:
				verts.append([_float(v), 0.0])
				bulges.append(0.0)
			elif c == 20 and verts:
				verts[-1][1] = _float(v)
			elif c == 42 and bulges:
				bulges[-1] = _float(v)
		return [_polyline(verts, bulges, closed, layer)] if verts else []
	if kind == "CIRCLE":
		return [{"t": "c", "y": layer, "x": _float(_get(rec, 10)), "y0": _float(_get(rec, 20)), "r": _float(_get(rec, 40))}]
	if kind == "ARC":
		pts = _arc_points(_float(_get(rec, 10)), _float(_get(rec, 20)), _float(_get(rec, 40)),
			_float(_get(rec, 50)), _float(_get(rec, 51)))
		return [{"t": "pl", "y": layer, "p": pts, "c": False}]
	if kind in ("TEXT", "MTEXT"):
		text = "".join(v for c, v in rec if c in (3, 1)) if kind == "MTEXT" else (_get(rec, 1) or "")
		if kind == "MTEXT":
			text = MTEXT_CODES.sub(" ", text).strip()
		return [{"t": "tx", "y": layer, "x": _float(_get(rec, 10)), "y0": _float(_get(rec, 20)),
			"h": _float(_get(rec, 40), 1.0), "a": _float(_get(rec, 50)), "s": text[:500]}]
	return []


def _polyline(verts, bulges, closed, layer):
	pts = [verts[0][0], verts[0][1]]
	n = len(verts)
	for i in range(n - 1 + (1 if closed else 0)):
		x1, y1 = verts[i]
		x2, y2 = verts[(i + 1) % n]
		pts += _bulge_points(x1, y1, x2, y2, bulges[i])
	if closed and len(pts) >= 4 and pts[-2:] == pts[:2]:
		pts = pts[:-2]
	return {"t": "pl", "y": layer, "p": pts, "c": closed}


def _transform(item, bx, by, sx, sy, rot, ix, iy, layer):
	"""Move a block item from block space to the insert's space."""
	cos, sin = math.cos(math.radians(rot)), math.sin(math.radians(rot))

	def tp(x, y):
		x, y = (x - bx) * sx, (y - by) * sy
		return ix + x * cos - y * sin, iy + x * sin + y * cos

	out = dict(item)
	if item.get("y") == "0":
		out["y"] = layer  # entities on layer 0 inside a block take the insert's layer
	if item["t"] in ("l", "pl"):
		p = item["p"]
		out["p"] = [c for i in range(0, len(p), 2) for c in tp(p[i], p[i + 1])]
	elif item["t"] in ("c", "tx"):
		out["x"], out["y0"] = tp(item["x"], item["y0"])
		if item["t"] == "c":
			out["r"] = item["r"] * abs(sx)
		else:
			out["h"] = item["h"] * abs(sy)
			out["a"] = item.get("a", 0) + rot
	return out


def parse(content: bytes | str) -> dict:
	"""Read a DXF; any malformed input raises DXFError (never a bare Python error)."""
	try:
		return _parse(content)
	except DXFError:
		raise
	except (ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError, ZeroDivisionError) as e:
		raise DXFError(f"The drawing could not be read ({type(e).__name__})") from e


def _parse(content: bytes | str) -> dict:
	if isinstance(content, bytes):
		if len(content) > MAX_BYTES:
			raise DXFError(f"The drawing is larger than {MAX_BYTES // 1024 // 1024} MB")
		if content.startswith(b"AutoCAD Binary DXF"):
			raise DXFError("Binary DXF is not supported: save the drawing as ASCII DXF")
		if content[:6] in (b"AC1015", b"AC1018", b"AC1021", b"AC1024", b"AC1027", b"AC1032") or content[:2] == b"AC":
			raise DXFError("This looks like a DWG file: export it as DXF first")
		try:
			text = content.decode("utf-8")
		except UnicodeDecodeError:
			text = content.decode("cp1252", errors="replace")
	else:
		text = content
	sections = _sections(text)
	if "ENTITIES" not in sections:
		raise DXFError("No ENTITIES section: this is not a DXF drawing")

	units, unit_to_m = None, None
	header = sections.get("HEADER", [])
	for i, (c, v) in enumerate(header):
		if c == 9 and v.strip() == "$INSUNITS" and i + 1 < len(header):
			code = int(_float(header[i + 1][1], 0))
			units, unit_to_m = INSUNITS.get(code, (None, None))

	blocks = {}
	name, base, current = None, (0.0, 0.0), []
	for rec in _records(sections.get("BLOCKS", [])):
		kind = rec[0][1]
		if kind == "BLOCK":
			name, base, current = (_get(rec, 2) or "").strip(), (_float(_get(rec, 10)), _float(_get(rec, 20))), []
		elif kind == "ENDBLK":
			if name is not None:
				blocks[name] = (base, current)
			name = None
		elif name is not None:
			current.append(rec)

	items = []
	inserts = [0]

	def emit(new):
		items.extend(new)
		if len(items) > MAX_ITEMS:
			raise DXFError(f"The drawing has more than {MAX_ITEMS} elements")

	def expand(records, depth, transforms):
		pending = None  # an old-style POLYLINE collecting its VERTEX records
		for rec in records:
			kind = rec[0][1]
			if pending is not None:
				if kind == "VERTEX":
					pending["v"].append([_float(_get(rec, 10)), _float(_get(rec, 20))])
					pending["b"].append(_float(_get(rec, 42)))
					continue
				if pending["v"]:
					emit(_apply([_polyline(pending["v"], pending["b"], pending["c"], pending["y"])], transforms))
				pending = None
				if kind == "SEQEND":
					continue
			if kind == "POLYLINE":
				pending = {"v": [], "b": [], "c": bool(int(_float(_get(rec, 70), 0)) & 1), "y": (_get(rec, 8) or "0").strip()}
			elif kind == "INSERT":
				block = blocks.get((_get(rec, 2) or "").strip())
				if block is None or depth >= MAX_BLOCK_DEPTH:
					continue
				inserts[0] += 1
				if inserts[0] > MAX_INSERTS:
					raise DXFError(f"The drawing expands more than {MAX_INSERTS} block inserts")
				(bx, by), brecs = block
				t = (bx, by, _float(_get(rec, 41), 1.0), _float(_get(rec, 42), 1.0), _float(_get(rec, 50)),
					_float(_get(rec, 10)), _float(_get(rec, 20)), (_get(rec, 8) or "0").strip())
				expand(brecs, depth + 1, [t] + transforms)
			else:
				emit(_apply(_entity_items(rec), transforms))
		if pending is not None and pending["v"]:
			emit(_apply([_polyline(pending["v"], pending["b"], pending["c"], pending["y"])], transforms))

	def _apply(new, transforms):
		for t in transforms:
			new = [_transform(i, *t) for i in new]
		return new

	expand(_records(sections["ENTITIES"]), 0, [])
	return {"units": units, "unit_to_m": unit_to_m, "layers": sorted({i["y"] for i in items}),
		"extents": extents(items), "count": len(items), "items": items}


def extents(items):
	xs, ys = [], []
	for i in items:
		if i["t"] in ("l", "pl"):
			xs += i["p"][0::2]
			ys += i["p"][1::2]
		elif i["t"] == "c":
			xs += [i["x"] - i["r"], i["x"] + i["r"]]
			ys += [i["y0"] - i["r"], i["y0"] + i["r"]]
		else:
			xs.append(i["x"])
			ys.append(i["y0"])
	return [min(xs), min(ys), max(xs), max(ys)] if xs else [0, 0, 1, 1]


# --- measuring (drawing units in, the caller applies the scale) --------------------------------------------


def polyline_length(points) -> float:
	return sum(math.hypot(points[i + 2] - points[i], points[i + 3] - points[i + 1]) for i in range(0, len(points) - 2, 2))


def polygon_area(points) -> float:
	n = len(points) // 2
	if n < 3:
		return 0.0
	s = 0.0
	for i in range(n):
		x1, y1 = points[2 * i], points[2 * i + 1]
		x2, y2 = points[2 * ((i + 1) % n)], points[2 * ((i + 1) % n) + 1]
		s += x1 * y2 - x2 * y1
	return abs(s) / 2
