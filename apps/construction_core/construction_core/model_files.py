"""Model files: Revit, IFC and SketchUp (P3-75; design §15.4, QP-2, QP-3; D-416, D-417).

**The checks** (client_files.check_structure's step 7 for these types), each on the bytes, bounded, never unpacking a
model:

- **Revit** (``.rvt``; ``.rfa`` in the Team room): a compound file walked with loop guards and caps (the renderer's
  own reader, ``previews/readers/ole.py``), with Revit's ``BasicFileInfo`` and ``RevitPreview4.0`` streams, and no
  ``Macros``, ``VBA`` or ``_VBA_PROJECT`` storage or stream.
- **IFC** (``.ifc`` only: no ``.ifczip``, no ifcXML): ``ISO-10303-21;`` then ``HEADER;`` in the first 4 KB, no NUL in
  the first 64 KB, a known schema (IFC2X3, IFC4, IFC4X1, IFC4X3), and the end marker.
- **SketchUp** (2021 and later): the header, then a ZIP read through ``_check_zip_directory`` and the entry, size and
  path caps; an older file is refused until a check exists for it (§15.9).

A file too large to scan in the request is held and scanned in the background: ``scan_holds``.
"""

import re
import struct
import zipfile
from io import BytesIO

import frappe
from frappe import _

from construction_core import client_files

SCHEMAS = ("IFC2X3", "IFC4", "IFC4X1", "IFC4X3")
MACROS = {"macros", "vba", "_vba_project"}
SKP_VERSION = re.compile(rb"\{\x00(\d\x00){1,3}\.\x00")  # the UTF-16 "{21." after the header


def check(ext: str, content: bytes) -> None:
	if ext in ("rvt", "rfa"):
		_check_revit(ext, content)
	elif ext == "ifc":
		_check_ifc(content)
	elif ext == "skp":
		_check_sketchup(content)


def _check_revit(ext: str, content: bytes) -> None:
	from construction_core.previews.readers import common, ole

	try:
		compound = ole.Compound(BytesIO(content), len(content))
	except (common.Refused, ValueError, struct.error):
		client_files._not_valid(ext)
	names = {n.lower() for n in compound.names()}
	if names & MACROS:
		frappe.throw(_("Files with macros or embedded programs cannot be sent. Save a copy without macros and send "
			"that."))
	preview = compound.find("RevitPreview4.0")
	if not (compound.find("BasicFileInfo") and preview):
		client_files._not_valid(ext)
	try:  # its preview stream reads end to end: a chain that loops or leaves the file is refused
		compound.read(preview, 2 * 1024 * 1024)
	except common.Refused:
		client_files._not_valid(ext)


def _check_ifc(content: bytes) -> None:
	from construction_core.previews.readers import common, ifc

	try:
		info = ifc.info(content[:ifc.HEAD])
	except common.Refused:
		client_files._not_valid("ifc")
	if not info["schema"].startswith(SCHEMAS):
		frappe.throw(_("This IFC schema cannot be sent. Export the model as IFC2X3, IFC4 or IFC4X3."))
	if not content[-4096:].rstrip().endswith(b"END-ISO-10303-21;"):  # the tail only: a 250 MB file is not copied
		client_files._not_valid("ifc")  # cut short


def _check_sketchup(content: bytes) -> None:
	head = content[:4096]
	start = head.find(b"PK\x03\x04")
	version = SKP_VERSION.search(head)
	major = int(version.group(0)[2::2].rstrip(b".").decode()) if version else 0
	if not head.startswith(client_files.SKP_MAGIC) or start < 0 or major < 21:
		frappe.throw(_("SketchUp files from before 2021 cannot be sent yet. Save the model in SketchUp 2021 or later "
			"and send that."))
	client_files._check_zip_directory("skp", content)
	try:
		z = zipfile.ZipFile(BytesIO(content))
	except (zipfile.BadZipFile, ValueError, OSError):
		client_files._not_valid("skp")
	with z:
		infos = z.infolist()
		if len(infos) > client_files.MAX_ENTRIES or sum(i.file_size for i in infos) > client_files.MAX_UNZIPPED:
			client_files._too_complex()
		for i in infos:
			if i.flag_bits & 0x1 or i.filename.startswith(("/", "\\")) or ".." in i.filename.replace("\\", "/").split("/"):
				client_files._not_valid("skp")
