"""Check a Keystone approvals evidence pack (approvals design §4.6), with the Python standard library only.

    python -I verify_chain.py <pack.zip> [--heads heads.json]

It checks the chain (sequence 1..n, every previous hash and hash, the first from the site and project in seq 1's own
text), that each request's snapshot hashes to the terms_hash its terms events carry, that each frozen file's bytes hash
to its name, each personal detail row's commitment when the pack holds them (a row whose location was cleared, as a
location_cleared event says, is accepted), and with --heads that each outside head {"project", "seq", "hash"} of this
pack's project is in the chain; each request's shown copies must be in the pack. Prints PACK OK and exits 0, or names each problem and exits 1.

The pack: events.jsonl (one {"name", "seq", "prev_hash", "hash", "canonical"} per line, in order), requests/<name>.json
({"name", "terms_hash", "snapshot"}), frozen/<sha256>, detail.jsonl (optional: {"event", "name", "salt", <fields>}).
"""

import hashlib
import json
import sys
import unicodedata
import zipfile

GENESIS_LABEL = "Keystone approvals chain, version 1"
DETAIL_FIELDS = ("network_address", "ip_trust", "user_agent", "browser", "system", "wsgi_peer", "location")
TERMS_EVENTS = ("drafted", "requested", "internal_review")


def sha256(value):
	return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def link(prev, canonical_text):  # as approvals.canonical.link
	return sha256(f"{prev}\n{canonical_text}")


def genesis(site, project):  # as approvals.canonical.genesis
	return sha256(f"{GENESIS_LABEL}\n{site}\n{project}")


def text(values):
	"""approvals.canonical.text of a flat dict of strings (a detail row's values)."""
	out = {"canonical_version": "1", **{unicodedata.normalize("NFC", k): unicodedata.normalize("NFC", v)
		for k, v in values.items()}}
	return json.dumps(out, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def check(pack, heads=None):
	"""The problems found, as lines; none means the pack is whole."""
	bad = []
	with zipfile.ZipFile(pack) as z:
		names = set(z.namelist())
		events, texts = [], {}
		for n, line in enumerate(z.read("events.jsonl").split(b"\n"), start=1):
			if not line.strip():
				continue
			try:
				e = json.loads(line.decode("utf-8"))
				t = json.loads(e["canonical"])
				e["seq"] = int(e["seq"])
				if not isinstance(t, dict):
					raise ValueError
			except (ValueError, KeyError, TypeError):
				bad.append(f"events.jsonl line {n}: not an event")
				continue
			events.append(e)
			texts[e["name"]] = t
		prev, last = None, 0
		for e in events:
			t = texts[e["name"]]
			if e["seq"] != last + 1:
				bad.append(f"seq {e['seq']}: the sequence breaks after {last}")
			last = e["seq"]
			if e["seq"] == 1:
				prev = genesis(t.get("site", ""), t.get("project", ""))
			if e["prev_hash"] != prev:
				bad.append(f"seq {e['seq']}: the previous hash is not the previous event's")
			if link(e["prev_hash"], e["canonical"]) != e["hash"] or t.get("seq") != str(e["seq"]):
				bad.append(f"seq {e['seq']}: the hash is not its canonical text's")
			prev = e["hash"]
		project = texts[events[0]["name"]].get("project") if events else None
		if not events:
			bad.append("events.jsonl: the pack holds no events")
		bad += [f"seq {e['seq']}: the event is not of project {project}" for e in events
			if texts[e["name"]].get("project") != project]
		bad += [f"requests/{r}.json: missing" for r in sorted({t.get("request") for t in texts.values()
			if t.get("kind") in TERMS_EVENTS and t.get("request")}) if f"requests/{r}.json" not in names]
		for name in sorted(n for n in names if n.startswith("requests/") and n.endswith(".json")):
			try:
				r = json.loads(z.read(name).decode("utf-8"))
				carried = {t.get("terms_hash") for t in texts.values()
					if t.get("request") == r["name"] and t.get("kind") in TERMS_EVENTS}
				ok = sha256(r["snapshot"]) == r["terms_hash"] and carried == {r["terms_hash"]}
				shown = [x["shown_sha256"] for x in json.loads(r["snapshot"])["frozen"].values()]
			except (ValueError, KeyError, TypeError, AttributeError):
				ok, shown = False, []
			if not ok:
				bad.append(f"{name}: the snapshot is not its request's terms_hash")
			bad += [f"{name}: the frozen copy {sha} is not in the pack" for sha in shown if f"frozen/{sha}" not in names]
		for name in sorted(n for n in names if n.startswith("frozen/") and not n.endswith("/")):
			if sha256(z.read(name)) != name.rsplit("/", 1)[1]:
				bad.append(f"{name}: the bytes are not their name's SHA-256")
		if "detail.jsonl" in names:
			located = set()
			for t in texts.values():
				body = t.get("body") if isinstance(t.get("body"), dict) else {}
				if t.get("kind") == "location_cleared":
					located.add((body.get("event"), body.get("detail")))
			for n, line in enumerate(z.read("detail.jsonl").split(b"\n"), start=1):
				if not line.strip():
					continue
				try:
					d = json.loads(line.decode("utf-8"))
					t = texts.get(d["event"], {})
					values = {f: d.get(f) or "" for f in DETAIL_FIELDS}
					ok = sha256(f"{d['salt']}\n{text(values)}") == t.get("detail_commitment") or (
						values["location"] == "" and (d["event"], d["name"]) in located)
					where = f"seq {t.get('seq', '?')}"
				except (ValueError, KeyError, TypeError, AttributeError):
					ok, where = False, f"detail.jsonl line {n}"
				if not ok:
					bad.append(f"{where}: the personal detail is not its commitment")
		checked = skipped = 0
		for h in heads or []:
			try:
				if h["project"] != project:
					skipped += 1
					continue
				checked += 1
				found = any(e["seq"] == int(h["seq"]) and e["hash"] == h["hash"] for e in events)
			except (KeyError, TypeError, ValueError):
				found = False
			if not found:
				bad.append(f"outside head {h!r}: not in the chain")
		if heads:
			print(f"outside heads: {checked} checked, {skipped} of other projects skipped")
			if not checked:  # a pack re-chained under another project name would skip every real head
				bad.append(f"outside heads: none is of project {project}")
	return bad


def main(argv):
	args = list(argv)
	heads = None
	if "--heads" in args:
		i = args.index("--heads")
		try:
			with open(args[i + 1], encoding="utf-8") as fh:
				heads = json.load(fh)
		except (IndexError, OSError, ValueError):
			print("the heads file cannot be read")
			return 1
		del args[i:i + 2]
	if len(args) != 1:
		print(__doc__)
		return 2
	try:
		bad = check(args[0], heads if isinstance(heads, list) or heads is None else [heads])
	except (OSError, KeyError, zipfile.BadZipFile) as e:
		bad = [f"the pack cannot be read: {e}"]
	for line in bad:
		print(line)
	if bad:
		return 1
	print("PACK OK")
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
