"""G-38: every deploy profile is a pinned recipe (DR-1, D-083, D-104). Prints one line per check; exits 1 on any failure.

Checks: commits are full SHAs and agree across profiles and with the dev build; images are pinned by digest and
agree with the compose file; build packages (ffmpeg, build-essential) are in the `full` profile only; the
Containerfile installs them only for `full`; the Document Server is on an internal network with JWT.
P2-02 (D-110, D-111, D-112): the shell is built in its own stage from a lockfile in which every package has an
integrity hash and comes from the npm registry, with exact versions in package.json, in a Node image pinned by digest
(the same one the dev scripts use).
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILES = ("core", "core+office", "full")
SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")
failures = []


def check(ok, what):
	print(("PASS " if ok else "FAIL ") + what)
	if not ok:
		failures.append(what)


def load(profile):
	return json.loads((ROOT / "deploy" / "profiles" / profile / "apps-versions.json").read_text(encoding="utf-8"))


pins = {p: load(p) for p in PROFILES}
dev_build = (ROOT / "dev" / "build-core-image.sh").read_text(encoding="utf-8")
compose = (ROOT / "deploy" / "compose.yml").read_text(encoding="utf-8")
containerfile = (ROOT / "deploy" / "Containerfile.pinned").read_text(encoding="utf-8")

for p, d in pins.items():
	check(d.get("profile") == p, f"{p}: the file names its profile")
	for app, spec in d["apps"].items():
		if "url" in spec:
			check(bool(SHA.match(spec.get("commit", ""))), f"{p}: {app} is pinned to a full commit SHA")
			check("branch" not in spec, f"{p}: {app} has no floating branch")
		else:
			check(spec.get("source") == "repo" and (ROOT / spec.get("path", "-")).is_dir(),
				f"{p}: {app} comes from this repository")
	base = d["base"]
	check(bool(SHA.match(base.get("frappe_docker", ""))), f"{p}: the frappe_docker recipe is pinned to a SHA")
	check(bool(DIGEST.match(base.get("python", ""))), f"{p}: the Python base image is pinned by digest")
	check(bool(re.match(r"^\d+\.\d+\.\d+$", base.get("bench", ""))), f"{p}: frappe-bench is an exact version")
	for svc, image in d["services"].items():
		check(bool(DIGEST.match(image)), f"{p}: service {svc} is pinned by digest")
		check(f"image: {image}" in compose, f"{p}: compose uses the same {svc} image")
	packages = set(d.get("build_packages", []))
	if p == "full":
		check({"ffmpeg", "build-essential"} <= packages, "full: ships ffmpeg and build-essential (adapter build needs)")
	else:
		check(not packages, f"{p}: no adapter build packages")
	check(("documentserver" in d["services"]) == (p != "core"), f"{p}: Document Server only in office profiles")

commits = {d["apps"]["frappe"]["commit"] for d in pins.values()}
check(len(commits) == 1, "all profiles pin the same frappe commit")
check(next(iter(commits)) in dev_build, "the dev build uses the same frappe commit")
# D-104: the core never carries ERPNext; only `full` (the optional ws_erpnext adapter) does, pinned like the rest.
for p in ("core", "core+office"):
	check("erpnext" not in pins[p]["apps"], f"{p}: carries no ERPNext (D-104)")
check("erpnext" in pins["full"]["apps"], "full: carries ERPNext for the optional adapter")
check(pins["full"]["apps"]["erpnext"]["commit"] in dev_build, "the dev build pins the same erpnext commit (WITH_ERPNEXT=1)")

images = re.findall(r"^\s*image:\s*(\S+)", compose, re.M)
check(all(DIGEST.match(i) or i.startswith("${APP_IMAGE") or i.startswith("${RENDERER_IMAGE") for i in images),
	"compose: every image is a built image (the app's, the renderer's) or pinned by digest")
check(":latest" not in compose and ":latest" not in containerfile, "no :latest anywhere")
check('if [ "${PROFILE}" != "full" ]; then' in containerfile, "Containerfile installs build packages for full only")
office = compose.split("  documentserver:", 1)[1] if "  documentserver:" in compose else ""
check('JWT_ENABLED: "true"' in office and "networks: [office]" in office, "Document Server requires JWT, office network only")
check(re.search(r"office:\s*\n\s*internal: true", compose) is not None, "the office network is internal (no egress)")

# P2-02: the shell's build path.
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
shell_images = (ROOT / "dev" / "shell-images.sh").read_text(encoding="utf-8")
build_sh = (ROOT / "deploy" / "build.sh").read_text(encoding="utf-8")
image_pin = dict(re.findall(r'^(NODE_IMAGE)="([^"]+)"', shell_images, re.M))
nodes = {d["base"].get("shell_node", "") for d in pins.values()}
check(len(nodes) == 1 and DIGEST.match(next(iter(nodes))), "every profile pins the same shell Node image by digest")
check(image_pin.get("NODE_IMAGE") in nodes, "dev/shell-images.sh builds with the profiles' Node image")
check("FROM ${SHELL_NODE_IMAGE} AS shell-build" in containerfile and "RUN npm ci " in containerfile
	and "npm install" not in containerfile, "the Containerfile builds the shell in its own stage with npm ci")
check('--build-arg SHELL_NODE_IMAGE="$SHELL_NODE_IMAGE"' in build_sh, "deploy/build.sh passes the pinned Node image")
for p, d in pins.items():
	shell = d["apps"].get("construction_shell", {})
	check(shell.get("requires") == ["construction_core"], f"{p}: carries construction_shell, which requires construction_core")


def check_lockfile(folder, what):
	package = json.loads((ROOT / folder / "package.json").read_text(encoding="utf-8"))
	lock = json.loads((ROOT / folder / "package-lock.json").read_text(encoding="utf-8"))
	declared = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
	check(all(SEMVER.match(v) for v in declared.values()), f"{what}: every version in package.json is exact")
	root = lock.get("packages", {}).get("", {})
	check({**root.get("dependencies", {}), **root.get("devDependencies", {})} == declared,
		f"{what}: package-lock.json matches package.json")
	check(lock.get("lockfileVersion") == 3, f"{what}: package-lock.json is lockfile v3")
	entries = [(k, v) for k, v in lock["packages"].items() if k and not v.get("link")]
	check(bool(entries) and all(v.get("integrity", "").startswith("sha512-") for _, v in entries),
		f"{what}: every package has a sha512 integrity hash ({len(entries)} packages)")
	check(all(v.get("resolved", "").startswith("https://registry.npmjs.org/") for _, v in entries),
		f"{what}: every package comes from registry.npmjs.org")
	return package, lock


_, shell_lock = check_lockfile("apps/construction_shell/frontend", "shell")
# A lockfile made on another platform can lack Linux's build tools; the image builds on Linux (x64).
check({"node_modules/@rollup/rollup-linux-x64-gnu", "node_modules/@esbuild/linux-x64"} <= set(shell_lock["packages"]),
	"shell: the lockfile carries the Linux x64 build tools (rollup, esbuild)")

# P3-07 (D-159, D-179, D-182): the virus scanner, pinned like the rest. clamd parses hostile files, so it has no egress;
# its updater alone reaches the signature mirror.
clam_pins = {d["services"].get("clamav") or "" for d in pins.values()}
pin = next(iter(clam_pins))
check(len(clam_pins) == 1 and re.match(r"^clamav/clamav:\d+\.\d+\.\d+_base@sha256:[0-9a-f]{64}$", pin) is not None,
	"every profile pins the same ClamAV image by digest")


def service(text, name):
	return text.split(f"\n  {name}:\n", 1)[1].split("\n\n", 1)[0] if f"\n  {name}:\n" in text else ""


dev_compose = (ROOT / "dev" / "docker-compose.yml").read_text(encoding="utf-8")
for where, text in (("compose", compose), ("dev compose", dev_compose)):
	scanner, updater = service(text, "clamav"), service(text, "clamav-update")
	check(f"image: {pin}" in scanner and f"image: {pin}" in updater, f"{where}: clamd and its updater use the pinned image")
	check("networks: [scan]" in scanner and "networks: [scan-egress]" in updater,
		f"{where}: clamd is on the scan network only, and the updater alone has egress")
	check(re.search(r"\n  scan:\s*\n\s*internal: true", text) is not None, f"{where}: the scan network is internal")
	check("profiles:" not in scanner + updater and "ports:" not in scanner + updater,
		f"{where}: the scanner runs in every profile and publishes nothing")
	check(re.search(r"networks: \[[^\]]*\bscan\b[^\]]*\]", service(text, "backend")) is not None
		or "      scan: {}" in service(text, "backend"), f"{where}: the backend reaches clamd")
	check('CLAMD_CONF_AlertExceedsMax: "yes"' in scanner and "CLAMD_CONF_StreamMaxLength: 251M" in scanner,
		f"{where}: clamd refuses what it cannot fully scan, up to the upload ceiling (250 MB model files, D-417)")

# P3-75 (design §15.1, D-416): the renderer is built from this repository on the stack's own pinned Python base, with
# its wheels by exact version and hash, and it runs isolated: read-only, no capability, no new privileges, a non-root
# user, an init, no network at all, and no mount but its socket volume, which only the thumbs worker shares. Both
# compose files are parsed (YAML), and the renderer's settings are an allowlist: an added key fails.
renderer_file = (ROOT / "deploy" / "renderer" / "Containerfile").read_text(encoding="utf-8")
pythons = {d["base"]["python"] for d in pins.values()}
check(len(pythons) == 1 and f"FROM {next(iter(pythons))}\n" in renderer_file,
	"renderer: built on the profiles' pinned Python base")
check("--require-hashes" in renderer_file and "--no-deps" in renderer_file, "renderer: wheels installed by hash only")
reqs = (ROOT / "deploy" / "renderer" / "requirements.txt").read_text(encoding="utf-8")
packages = re.findall(r"^([A-Za-z0-9_.-]+)==(\S+) \\\n\s+--hash=sha256:[0-9a-f]{64}$", reqs, re.M)
check({n.lower() for n, _ in packages} == {"pillow", "pypdfium2"}, "renderer: only Pillow and pypdfium2, exact and hashed")
RENDERER_KEYS = {"image", "build", "user", "read_only", "cap_drop", "security_opt", "tmpfs", "pids_limit", "mem_limit",
	"memswap_limit", "cpus", "environment", "network_mode", "init", "volumes", "healthcheck", "restart"}
RENDERER_ENV = {"RENDER_JOBS", "RENDER_CHILD_MEMORY", "RENDER_SOCKET"}


def renderer_isolated(where, spec, services, volumes):
	"""Each of the renderer's settings, and nothing else: problems as text."""
	bad = [f"unexpected key {k}" for k in sorted(set(spec) - RENDERER_KEYS)]
	want = {"user": "10001:10001", "read_only": True, "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
		"network_mode": "none", "init": True, "volumes": ["render-socket:/run/renderer"]}
	bad += [f"{k} is {spec.get(k)!r}" for k, v in want.items() if spec.get(k) != v]
	tmpfs = spec.get("tmpfs") or []
	if len(tmpfs) != 1 or not str(tmpfs[0]).startswith("/tmp:size=") or not all(
			o in str(tmpfs[0]).split(":", 1)[1].split(",") for o in ("noexec", "nosuid", "nodev")):
		bad.append(f"tmpfs is {tmpfs!r}")
	for k in ("pids_limit", "mem_limit", "cpus"):
		if not spec.get(k):
			bad.append(f"no {k}")
	if spec.get("memswap_limit") != spec.get("mem_limit"):
		bad.append("memswap_limit differs from mem_limit (swap would raise the memory limit)")
	env = spec.get("environment") or {}
	if set(env) - RENDERER_ENV or str(env.get("RENDER_CHILD_MEMORY", "0")) in ("", "0"):
		bad.append(f"environment is {env!r}")
	if spec.get("restart") not in (None, "unless-stopped"):
		bad.append("restart")
	socket_volume = (volumes or {}).get("render-socket") or {}
	opts = socket_volume.get("driver_opts") or {}
	if opts.get("type") != "tmpfs" or "uid=10001" not in str(opts.get("o")):
		bad.append("render-socket is not a tmpfs volume owned by the renderer's user")
	sharing = sorted(n for n, svc in services.items() if any(str(v).startswith("render-socket:")
		for v in (svc or {}).get("volumes") or []))
	if sharing != ["queue-thumbs", "renderer"]:
		bad.append(f"render-socket is mounted by {sharing}")
	check(not bad, f"{where}: the renderer runs isolated ({'; '.join(bad) or 'every setting as allowed'})")


try:
	import yaml
except ImportError:
	yaml = None
check(yaml is not None, "PyYAML reads the compose files")
if yaml:
	for where, text in (("compose", compose), ("dev compose", dev_compose)):
		parsed = yaml.safe_load(text)
		services = parsed.get("services") or {}
		renderer_isolated(where, services.get("renderer") or {}, services, parsed.get("volumes"))
	check((yaml.safe_load(compose)["services"]["renderer"].get("image") or "").startswith("${RENDERER_IMAGE")
		and "build" not in yaml.safe_load(compose)["services"]["renderer"], "compose: the renderer runs the built image")

# P3-17 (D-214): the dev mail catcher is pinned by digest, and production never runs one.
mailpit = service(dev_compose, "mailpit")
check(re.search(r"image: axllent/mailpit:v\d+\.\d+\.\d+@sha256:[0-9a-f]{64}\n", mailpit) is not None
	and "ports:" not in mailpit, "dev compose: the mail catcher is pinned by digest and publishes nothing")
check("mailpit" not in compose.lower(), "compose: production runs no mail catcher")

print(f"{'FAILED' if failures else 'OK'}: {len(failures)} failure(s)")
sys.exit(1 if failures else 0)
