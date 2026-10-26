"""The screens' words in Simple and Advanced mode (P3-01; D-154, D-155, D-161, D-162, D-163).

One glossary, words.json, is read here and by the app (frontend/src/words.js), so the server's text (notices, P3-06)
and the screens say the same thing. Display only: nothing here changes stored data or a permission.
"""

import json
import os
from functools import lru_cache

SIMPLE, ADVANCED = "simple", "advanced"


@lru_cache(maxsize=1)
def glossary() -> dict:
	with open(os.path.join(os.path.dirname(__file__), "words.json"), encoding="utf-8") as f:
		return json.load(f)


def normal(mode) -> str:
	"""Only exactly "advanced" is Advanced; anything else, junk included, is the default Simple (D-154)."""
	return ADVANCED if mode == ADVANCED else SIMPLE


def shows(section: str, mode) -> bool:
	"""Whether a section is on the rail in this mode. A hidden one still opens from a link (a view, not a lock)."""
	return normal(mode) == ADVANCED or section in glossary()["simple_sections"]


def section_label(section: str, mode) -> str:
	return glossary()["sections"].get(section, {}).get(normal(mode), section)


def noun(section: str, mode) -> str:
	return glossary()["nouns"].get(section, {}).get(normal(mode), section)


def state_label(state: str, mode) -> str:
	"""A record's state as Simple mode words it (D-162); a state the table does not name shows as stored."""
	if normal(mode) == ADVANCED or not state:
		return state
	return glossary()["states"].get(state, state)


def portal_state_label(state: str, mode) -> str:
	"""A state as the client portal words it: as Simple mode does, except where the word would suggest the client owes
	a decision, which they never do in the portal (D-134, D-165)."""
	if normal(mode) == ADVANCED or not state:
		return state
	return glossary()["portal_states"].get(state) or state_label(state, mode)
