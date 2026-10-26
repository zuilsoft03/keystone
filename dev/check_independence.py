"""D-104 (P1-20): our apps are independent of ERPNext. Prints PASS/FAIL lines; exits 1 on a failure.

The apps are construction_core and, from P2-02, construction_shell (PLAN §5.3: the D-104 rule extends to the shell).

  3a. hooks.py `required_apps` is exactly what each app may require: nothing for construction_core, and only
      construction_core for construction_shell.
  3b. No `import erpnext` / `from erpnext`, and no "erpnext.<module>" dotted path in a string.
  3c. No doctype JSON links to an ERPNext DocType (Link, Table, Table MultiSelect options) or grants an ERPNext
      role, and no string literal in code equals an ERPNext DocType or role name (dev/erpnext-names.txt, generated
      from the pinned ERPNext by dev/erpnext_names.py), except the reviewed uses in ALLOWED below, which are not
      doctype or role references. The shell's Vue sources are checked too; its built output is not ours to check.
  3d. construction_core never references construction_shell: the shell depends on the core, never the reverse.
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# app -> the apps its hooks.py may require
APPS = {"construction_core": [], "construction_shell": ["construction_core"]}
NAMES = os.path.join(ROOT, "dev", "erpnext-names.txt")

# (path relative to apps/<app>, literal): why it is not a reference to ERPNext
ALLOWED = {
	("construction_core/takeoff/api.py", "Item"): "a column heading of the Excel export",
	("construction_core/discuss/provider.py", "Project"): "the word shown in a thread title (DISPLAY)",
	("construction_core/discuss/provider.py", "Task"): "the word shown in a thread title (DISPLAY)",
	("construction_core/tests/test_portal.py", "Location"): "the HTTP Location response header",
	("construction_shell/tests/test_routes.py", "Location"): "the HTTP Location response header",
	("construction_shell/tests/test_portal_presenter.py", "Location"): "the HTTP Location response header",
	("construction_core/tests/test_portal_spa.py", "Location"): "the HTTP Location response header",
	("construction_core/tests/test_domain_workflows.py", "Item"): "a BOQ line description in test data",
	("construction_core/tests/test_office.py", "Contract"): "a document title in test data",
	("construction_core/patches/v0/p1_20_independent_core.py", "Projects Manager"): "the migration renames this old role",
	("construction_core/patches/v0/p1_20_independent_core.py", "Projects User"): "the migration renames this old role",
	("construction_core/patches/v0/p1_20_erpnext_cleanup.py", "Project"): "the audit cleanup removes our leftovers from ERPNext's Project",
	("construction_core/patches/v0/p1_20_erpnext_cleanup.py", "Project User"): "the audit cleanup removes our leftovers from ERPNext's Project User",
	("construction_core/patches/v0/p1_20_erpnext_cleanup.py", "Task"): "the audit cleanup removes our leftovers from ERPNext's Task",
	("construction_core/patches/v0/p1_20_erpnext_cleanup.py", "Location"): "the audit cleanup removes our leftovers from ERPNext's Location",
	("construction_core/patches/v0/p1_20_erpnext_cleanup.py", "Projects Manager"): "the audit cleanup removes our leftovers from ERPNext's Projects Manager",
	("construction_core/patches/v0/p1_20_erpnext_cleanup.py", "Projects User"): "the audit cleanup removes our leftovers from ERPNext's Projects User",
	("construction_core/tests/test_permissions.py", "Project"): "the test asserts our roles get nothing on ERPNext's Project",
	("construction_core/tests/test_permissions.py", "Projects Manager"): "the test asserts our roles get nothing on ERPNext's Projects Manager",
	("construction_core/tests/test_permissions.py", "Projects User"): "the test asserts our roles get nothing on ERPNext's Projects User",
}

failures = 0


def report(ok, what):
	global failures
	print(("PASS " if ok else "FAIL ") + what)
	failures += not ok


for app, allowed in APPS.items():
	hooks = open(os.path.join(ROOT, "apps", app, app, "hooks.py"), encoding="utf-8").read()
	m = re.search(r"^required_apps\s*=\s*(\[.*?\])", hooks, re.M)
	required = json.loads(m.group(1).replace("'", '"')) if m else None
	report(required == allowed, f"rule 3a: {app} requires {allowed or 'no app'}")

names = {}
for line in open(NAMES, encoding="utf-8"):
	if line[:3] in ("D: ", "R: "):
		names[line[3:].strip()] = "doctype" if line[0] == "D" else "role"

LITERAL = re.compile(r"""(["'])((?:(?!\1)[^\\\n]|\\.){1,80})\1""")
IMPORT = re.compile(r"^\s*(from|import)\s+erpnext\b", re.M)
DOTTED = re.compile(r"""["']erpnext\.[a-z_]""")
SHELL_REF = re.compile(r"""^\s*(from|import)\s+construction_shell\b|["']construction_shell\.[a-z_]""", re.M)
SKIP = ("vendor", "__pycache__", "node_modules", ".git", "dist")


def sources(app):
	"""(name, rel, text) for every source file of `app`; vendored, installed and built files are not ours."""
	base = os.path.join(ROOT, "apps", app)
	for dirpath, dirnames, files in os.walk(base):
		dirnames[:] = [d for d in dirnames if d not in SKIP
			and not (d == "shell" and os.path.basename(dirpath) == "public")]  # the shell's built app
		for name in files:
			if name.endswith((".py", ".js", ".json", ".html", ".vue")) and name != "package-lock.json":
				path = os.path.join(dirpath, name)
				yield name, os.path.relpath(path, base).replace(os.sep, "/"), open(path, encoding="utf-8").read()


imports, hits, reverse = [], [], []
for app in APPS:
	for name, rel, text in sources(app):
		if app == "construction_core" and SHELL_REF.search(text):
			reverse.append(rel)
		if IMPORT.search(text) or DOTTED.search(text):
			imports.append(rel)
		if name.endswith(".json"):
			try:
				meta = json.loads(text)
			except ValueError:
				meta = None
			if isinstance(meta, dict) and meta.get("doctype") in ("DocType", "Page", "Report"):
				for f in meta.get("fields") or []:
					if f.get("fieldtype") in ("Link", "Table", "Table MultiSelect") and f.get("options") in names:
						hits.append(f"{rel}: field {f.get('fieldname')} links ERPNext's {f.get('options')}")
				for r in (meta.get("permissions") or []) + (meta.get("roles") or []):
					if r.get("role") in names:
						hits.append(f"{rel}: grants ERPNext's role {r.get('role')}")
				continue
		for lineno, line in enumerate(text.split("\n"), 1):
			if line.lstrip().startswith(("#", "//")):
				continue
			for mm in LITERAL.finditer(line):
				lit = mm.group(2)
				if lit in names and (rel, lit) not in ALLOWED:
					hits.append(f"{rel}:{lineno}: \"{lit}\" is an ERPNext {names[lit]}")
report(not imports, "rule 3b: nothing imports erpnext" + ("" if not imports else ": " + ", ".join(imports)))
report(not hits, f"rule 3c: no ERPNext doctype or role name in our apps ({len(names)} names checked)")
for h in hits:
	print("   " + h)
report(not reverse, "rule 3d: construction_core never references construction_shell" + ("" if not reverse else ": " + ", ".join(reverse)))
sys.exit(1 if failures else 0)
