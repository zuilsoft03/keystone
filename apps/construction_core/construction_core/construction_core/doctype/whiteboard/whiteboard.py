# Copyright (c) 2026, Construction Workspace and contributors
"""Whiteboard (P1-15, D-099): a free canvas per project on Excalidraw. The scene and its version are written only
through ``construction_core.whiteboard.api.save``, which keeps every version (Whiteboard Version)."""

from frappe.model.document import Document

SERVER_FIELDS = ("scene", "version", "last_saved_by", "last_saved_on", "scene_size")
EMPTY_SCENE = '{"elements": [], "appState": {}, "files": {}}'


class Whiteboard(Document):
	def before_insert(self):
		self.scene, self.version, self.scene_size = EMPTY_SCENE, 0, len(EMPTY_SCENE)
		self.last_saved_by = self.last_saved_on = None

	def validate(self):
		if self.flags.cc_scene_save:
			return
		before = self.get_doc_before_save()
		for f in SERVER_FIELDS:
			if before:
				self.set(f, before.get(f))
