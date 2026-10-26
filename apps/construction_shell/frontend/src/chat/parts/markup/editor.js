// "Mark up" (P3-70, design §3.11, D-372, D-457): the picture editor for a client and for staff in Simple mode, on the vendored
// Excalidraw 0.17.6 that the boards use. The pure parts: who gets which button, the settings, and the file it makes. The original is
// never changed (L-4): the marked-up picture is a new file that joins the message tray. The scene lives only in the dialog.
import { composerActions } from '../../registry.js'
import { MAX_SIDE, PICTURE, flatBlob } from './board.js'

// 'canvas': a team-only board holds the picture (board.js, staff in Advanced mode); 'editor': the small editor (a client, staff in
// Simple mode); null: neither (the staff preview of the portal). A client's mode never decides, as the portal shows their own.
export function markupOf(viewer, mode) {
  if (viewer === 'client') return 'editor'
  if (viewer === 'staff') return mode === 'advanced' ? 'canvas' : 'editor'
  return null
}

// The button a reader gets in the picture viewer: markupOf's kind, once they may send files in this conversation (the box's own Attach
// test: registry.js composerActions) and, for a Canvas, once the host can make a board. `thread`: { capabilities }.
export function buttonOf(host, mode, thread) {
  if (!composerActions(host, thread).some((a) => a.id === 'attach')) return null
  const kind = markupOf(host.viewer, mode)
  return kind === 'canvas' && !(host.markup && host.project) ? null : kind
}

// The new file's name: the original's, without its type, and "-marked.jpg" (client_files.clean_name keeps the hyphen).
export const markedName = (fileName) => `${fileName.replace(/\.\w+$/, '')}-marked.jpg`

// Everything Excalidraw 0.17.6 lets UIOptions hide, for a person who only draws on a picture: no export, save, load, clear canvas,
// background or theme control, and no image tool. Not hideable there: the Library button, the main menu's Help and its links, and
// the canvas menu's "Unlock all", which can unlock the picture.
export const UI_OPTIONS = {
  canvasActions: { changeViewBackgroundColor: false, clearCanvas: false, export: false, loadScene: false, saveToActiveFile: false, saveAsImage: false, toggleTheme: false },
  tools: { image: false },
}

// The edited picture as a JPEG (quality 0.9, long side at most MAX_SIDE) on white. The photo's own element stands in as the export
// frame, which 0.17.6 crops to with no padding: a mark that runs past the photo's edge is cut there.
export const markedBlob = (lib, api) => flatBlob(lib, api, {
  mimeType: 'image/jpeg', quality: 0.9, maxWidthOrHeight: MAX_SIDE, exportPadding: 0,
  exportingFrame: api.getSceneElements().find((e) => e.id === PICTURE),
})
