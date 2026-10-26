"""Demo data for trying the app on dev.localhost (run by dev/seed-demo.sh; idempotent). P1-21 (D-104): Frappe only.

Creates a demo PM, an architect and a client (through clients.add_client, the way a PM onboards one), and the
project "Demo House (MVP)" with what the walkthroughs use:
- an RFI, a Submittal and a VO; a client-visible and an internal file; an internal and a client RFI thread;
- the client conversation on the project, and "seen by" receipts switched on;
- a whiteboard, a DXF ground-floor plan (12 x 9 m, in mm) and a PDF site plan (A3, 1:200, scale bar 10 m), both
  ready for takeoff; and the contract as a .docx for online editing.
The users' password comes from DEMO_PASSWORD (dev/.env, git-ignored) and is never printed.
"""

import io
import json
import os
import zipfile

import frappe

SITE = "dev.localhost"
PM, ARCH, CLIENT = "demo-pm@example.com", "demo-arch@example.com", "demo-client@example.com"
PROJECT = "Demo House (MVP)"


def staff(email, first_name, role):
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": first_name, "send_welcome_email": 0,
			"roles": [{"role": role}]}).insert(ignore_permissions=True)
	return email


def set_password(user):
	from frappe.utils.password import update_password

	update_password(user, os.environ["DEMO_PASSWORD"])


# --- demo files --------------------------------------------------------------------------------------------


def dxf_plan() -> bytes:
	"""A 12 x 9 m ground floor in mm: walls, three rooms, four columns and labels, on four layers."""
	rec = [(0, "SECTION"), (2, "HEADER"), (9, "$INSUNITS"), (70, 4), (0, "ENDSEC"), (0, "SECTION"), (2, "ENTITIES")]

	def poly(layer, pts, closed=True):
		rec.extend([(0, "LWPOLYLINE"), (8, layer), (90, len(pts)), (70, 1 if closed else 0)])
		for x, y in pts:
			rec.extend([(10, x), (20, y)])

	def line(layer, x0, y0, x1, y1):
		rec.extend([(0, "LINE"), (8, layer), (10, x0), (20, y0), (11, x1), (21, y1)])

	def text(x, y, value):
		rec.extend([(0, "TEXT"), (8, "TEXT"), (10, x), (20, y), (40, 250), (1, value)])

	poly("WALLS", [(0, 0), (12000, 0), (12000, 9000), (0, 9000)])
	line("WALLS", 5000, 0, 5000, 9000)
	line("WALLS", 0, 4000, 5000, 4000)
	poly("ROOMS", [(0, 0), (5000, 0), (5000, 4000), (0, 4000)])
	poly("ROOMS", [(0, 4000), (5000, 4000), (5000, 9000), (0, 9000)])
	poly("ROOMS", [(5000, 0), (12000, 0), (12000, 9000), (5000, 9000)])
	for x, y in ((0, 0), (12000, 0), (12000, 9000), (0, 9000)):
		rec.extend([(0, "CIRCLE"), (8, "COLUMNS"), (10, x), (20, y), (40, 200)])
	text(1500, 2000, "KITCHEN")
	text(1500, 6500, "BEDROOM")
	text(7500, 4500, "LIVING")
	rec.extend([(0, "ENDSEC"), (0, "EOF")])
	return ("\n".join(f"{c}\n{v}" for c, v in rec) + "\n").encode()


def pdf_site_plan() -> bytes:
	"""A3 landscape at 1:200: a 20 x 15 m lot, a 10 x 8 m house and a 10 m scale bar (1 m = 14.173 pt)."""
	k = 72 / 25.4 * 1000 / 200
	ops = ["1 w", f"60 60 {20 * k:.2f} {15 * k:.2f} re S", f"{60 + 5 * k:.2f} {60 + 3 * k:.2f} {10 * k:.2f} {8 * k:.2f} re S",
		f"700 80 m {700 + 10 * k:.2f} 80 l S", "700 75 m 700 85 l S", f"{700 + 10 * k:.2f} 75 m {700 + 10 * k:.2f} 85 l S",
		"BT /F1 12 Tf 700 90 Td (Scale bar 10 m - 1:200) Tj ET", "BT /F1 16 Tf 60 500 Td (Demo House - site plan) Tj ET"]
	stream = "\n".join(ops).encode()
	objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
		b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 1190.55 841.89] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
		b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
		b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
	out, offs = b"%PDF-1.7\n", []
	for i, o in enumerate(objs, 1):
		offs.append(len(out))
		out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
	x = len(out)
	out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offs)
	return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, x)


def contract_docx() -> bytes:
	"""A minimal Word document (WordprocessingML) for the online editor."""
	lines = ["CONSTRUCTION CONTRACT", "Project: Demo House (MVP)", "Contract sum: PHP 3,500,000.00",
		"Completion: 180 calendar days", "Retention: 10% until final acceptance"]
	body = "".join(f'<w:p><w:r><w:t xml:space="preserve">{t}</w:t></w:r></w:p>' for t in lines)
	parts = {
		"[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
		"_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
		"word/document.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + body + "</w:body></w:document>",
	}
	buf = io.BytesIO()
	with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
		for name, xml in parts.items():
			z.writestr(name, xml)
	return buf.getvalue()


def whiteboard_scene() -> str:
	shapes = [
		{"type": "rectangle", "x": 100, "y": 100, "width": 360, "height": 240, "strokeColor": "#1e1e1e"},
		{"type": "text", "x": 120, "y": 120, "width": 300, "height": 25, "text": "Site layout ideas", "fontSize": 20,
		 "strokeColor": "#1e1e1e"},
	]
	elements = []
	for i, s in enumerate(shapes):
		base = {"id": f"demo-{i}", "angle": 0, "backgroundColor": "transparent", "fillStyle": "solid", "strokeWidth": 2,
			"strokeStyle": "solid", "roughness": 1, "opacity": 100, "groupIds": [], "seed": 1000 + i, "version": 1,
			"versionNonce": 2000 + i, "isDeleted": False, "boundElements": None, "updated": 1, "link": None, "locked": False}
		if s["type"] == "text":
			base.update({"fontFamily": 1, "textAlign": "left", "verticalAlign": "top", "baseline": 18, "containerId": None,
				"originalText": s["text"], "lineHeight": 1.25})
		elements.append({**base, **s})
	return json.dumps({"type": "excalidraw", "version": 2, "elements": elements, "appState": {}, "files": {}})


# --- seed --------------------------------------------------------------------------------------------------


def seed():
	from construction_core import clients
	from construction_core.discuss.provider import DiscussChat
	from construction_core.providers.storage import FileStorage

	frappe.set_user("Administrator")
	staff(PM, "Paula (PM)", "Construction Manager")
	staff(ARCH, "Arturo (Architect)", "Construction Staff")
	project = frappe.db.get_value("Construction Project", {"project_name": PROJECT})
	if not project:
		frappe.set_user(PM)
		p = frappe.get_doc({"doctype": "Construction Project", "project_name": PROJECT, "status": "Open",
			"estimated_costing": 3500000, "cc_contract_signed_on": frappe.utils.today()}).insert()
		p.append("users", {"user": ARCH, "welcome_email_sent": 1})
		p.save()
		project = p.name
		clients.add_client(project, CLIENT, "Carla (Client)")
		rfi = frappe.get_doc({"doctype": "RFI", "project": project, "subject": "Roof drainage outlet position",
			"question": "Please confirm the outlet at the north corner.", "client_visible": 1,
			"due_date": frappe.utils.add_days(frappe.utils.today(), 7)}).insert()
		rfi.status = "Issued"
		rfi.save()
		sub = frappe.get_doc({"doctype": "Submittal", "project": project, "title": "Kitchen cabinets shop drawing",
			"client_visible": 1}).insert()
		sub.status = "Submitted"
		sub.save()
		vo = frappe.get_doc({"doctype": "Variation Order", "project": project, "title": "Extra skylight over stairs",
			"client_visible": 1, "deltas": [{"description": "Skylight 1.2 x 0.8 m", "qty_delta": 1,
			"rate_delta": 45000}]}).insert()
		vo.stage = "Change Order Request"
		vo.save()
		store = FileStorage()
		store.put(f"Projects/{project}/06_Client", "floor-plan-for-client.txt", b"Ground floor plan, rev A",
			project=project, client_visible=True)
		store.put(f"Projects/{project}/03_RFI", "structural-calc-internal.txt", b"Beam B3 check", project=project)
		store.put(f"Projects/{project}/01_Contract", "Construction Contract - Demo House.docx", contract_docx(),
			project=project)
		drawings = f"Projects/{project}/02_Design/Drawings"
		dxf = store.put(drawings, "Ground floor plan.dxf", dxf_plan(), project=project)
		pdf = store.put(drawings, "Site plan.pdf", pdf_site_plan(), project=project)
		frappe.get_doc({"doctype": "CAD Drawing", "project": project, "title": "Ground floor plan",
			"file": frappe.db.get_value("File", dxf, "file_url")}).insert()
		frappe.get_doc({"doctype": "CAD Drawing", "project": project, "title": "Site plan (PDF)", "page": 1,
			"file": frappe.db.get_value("File", pdf, "file_url")}).insert()
		frappe.get_doc({"doctype": "Whiteboard", "project": project, "title": "Site layout ideas"}).insert()
		frappe.set_user(ARCH)
		chat = DiscussChat()
		chat.post(chat.ensure_thread("RFI", rfi.name, "Internal"), "Internal: the gutter supplier is two weeks late.")
		chat.post(chat.ensure_thread("RFI", rfi.name, "Client"), "We propose the outlet at the north corner.")
		chat.post(chat.ensure_thread("Construction Project", project, "Client"),
			"Good morning Carla, the skylight variation is ready for your review.")
		frappe.set_user(CLIENT)
		chat.post(chat.ensure_thread("Construction Project", project, "Client"), "Thanks! I will look at it tonight.")
		frappe.set_user("Administrator")
		frappe.db.set_value("Workspace Config", project, "seen_receipts", 1)
	# A board's scene arrives only through its save API (versioned and sanitised), never at insert.
	from construction_core.whiteboard import api as boards

	for name in frappe.get_all("Whiteboard", filters={"project": project, "version": 0}, pluck="name"):
		frappe.set_user(PM)
		boards.save(name, whiteboard_scene(), 0)
	frappe.set_user("Administrator")
	for user in (PM, ARCH, CLIENT):
		set_password(user)
	frappe.db.commit()
	print(f"demo project {project}: staff {PM}, {ARCH} at /app; client {CLIENT} at /portal")


if __name__ == "__main__":
	frappe.init(site=SITE, sites_path="/home/frappe/frappe-bench/sites")
	frappe.connect()
	try:
		seed()
	finally:
		frappe.destroy()
