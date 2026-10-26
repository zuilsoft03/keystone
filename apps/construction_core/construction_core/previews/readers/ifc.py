"""IFC: no picture, an info card (design §15.2, QP-4): the schema and the authoring application from the STEP header
in the first 64 KB. Nothing else of the file is read. A real render waits for Q-11 (P5)."""

import re

from construction_core.previews.readers.common import FAILED, NOT_SUPPORTED, Refused

HEAD = 64 * 1024
SCHEMAS = ("IFC2X3", "IFC4", "IFC4X1", "IFC4X3")
MAX_TEXT = 80


def info(head: bytes) -> dict:
	"""{"schema", "app"} of a STEP header; refused when the bytes are not an IFC text file."""
	text = head[:HEAD]
	if b"\x00" in text:
		raise Refused(FAILED)
	body = text.removeprefix(b"\xef\xbb\xbf").lstrip()
	if not body.startswith(b"ISO-10303-21;") or b"HEADER;" not in body[:4096]:
		raise Refused(FAILED)
	header = body.split(b"ENDSEC;", 1)[0].decode("latin-1")
	schema = re.search(r"FILE_SCHEMA\s*\(\s*\(\s*'([A-Za-z0-9_]{1,32})'", header)
	schema = schema.group(1).upper() if schema else ""
	name = re.search(r"FILE_NAME\s*\(", header)
	args = _arguments(header, name.end()) if name else []
	app = next((a for a in (args[5:6] + args[4:5]) if a), "")  # originating system, else the preprocessor
	return {"schema": schema if schema.startswith(SCHEMAS) else (schema and "other"), "app": app}


def render(fh, px: int):
	raise Refused(NOT_SUPPORTED, info(fh.read(HEAD)))


def _arguments(text: str, at: int) -> list[str]:
	"""The top-level arguments of a STEP record from ``at`` (just past its opening parenthesis), each string unquoted
	and cleaned. Nested lists keep only their first string."""
	args, current, depth, i = [], [], 0, at
	while i < len(text) and len(args) < 8:
		c = text[i]
		if c == "'":
			end, value = _string(text, i + 1)
			if not current:
				current.append(value)
			i = end
			continue
		if c == "(":
			depth += 1
		elif c == ")":
			if depth == 0:
				args.append(_clean(current[0] if current else ""))
				break
			depth -= 1
		elif c == "," and depth == 0:
			args.append(_clean(current[0] if current else ""))
			current = []
		i += 1
	return args


def _string(text: str, i: int) -> tuple[int, str]:
	out = []
	while i < len(text):
		if text[i] == "'":
			if text[i + 1:i + 2] == "'":
				out.append("'")
				i += 2
				continue
			return i + 1, "".join(out)
		out.append(text[i])
		i += 1
	return i, "".join(out)


def _clean(value: str) -> str:
	value = re.sub(r"\\X2\\[0-9A-Fa-f]*\\X0\\|\\[A-Z]\\.?", "", value)  # STEP escapes: dropped, never decoded
	value = "".join(c for c in value if c.isprintable())
	return re.sub(r"\s+", " ", value).strip()[:MAX_TEXT]
