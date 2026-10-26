"""The registered payload parts (D-358, D-398): one line per part module, in a fixed order. A part module that is
not listed here fails test_discuss_core."""

from construction_core.discuss.parts import (
	approval,
	attachments,
	file_requests,
	mentions,
	pointer,
	polls,
	reactions,
	refs,
	voice,
)

PARTS = (attachments.PART, pointer.PART, mentions.PART, refs.PART, voice.PART, polls.PART, reactions.PART,
	file_requests.PART,  # file_requests: P3-71
	approval.PART)  # approval: P3-78; after pointer, whose page rows it draws


def by_key() -> dict:
	return {p.key: p for p in PARTS}
