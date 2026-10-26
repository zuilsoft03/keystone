"""Revit (RVT, RFA): the 128 px PNG in the ``RevitPreview4.0`` stream (design §15.2). The stream wraps the PNG in a
header of its own and a 40-byte trailer (measured on 4 local files, 2021 to 2026), so the PNG is found by its
signature and walked chunk by chunk to IEND."""

from construction_core.previews.readers.common import BLANK, Refused, open_embedded, png_slice, to_webp
from construction_core.previews.readers.ole import open_compound

PREVIEW_STREAM = "RevitPreview4.0"
MAX_STREAM = 2 * 1024 * 1024  # measured: 1.4 to 6.8 KB


def render(fh, px: int):
	compound = open_compound(fh)
	entry = compound.find(PREVIEW_STREAM)
	if entry is None:
		raise Refused(BLANK)
	png = png_slice(compound.read(entry, MAX_STREAM))
	return to_webp(open_embedded(png, ("PNG",)), px)
