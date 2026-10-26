// "Mark up on a Canvas" (P3-70, design §3.11, D-372): the pure parts. A chat picture is made small enough for a board and
// becomes the board's first scene, one image element at its own size. The original is never touched (L-4).
import { watch } from 'vue'

export const MAX_SIDE = 2048
export const PICTURE = 'markup-image' // the scene's one image element

// The size to draw a picture at: the same shape, its long side at most `max`; never larger than it is.
export function fitSize(w, h, max = MAX_SIDE) {
  const scale = Math.min(1, max / Math.max(w, h))
  return { width: Math.max(1, Math.round(w * scale)), height: Math.max(1, Math.round(h * scale)) }
}

// The loaded <img> as a JPEG data URL (quality 0.9) through a canvas, its long side at most MAX_SIDE.
export async function jpegOf(img) {
  await img.decode()
  const { width, height } = fitSize(img.naturalWidth, img.naturalHeight)
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = 'white' // a PNG's clear corners must not turn black in a JPEG
  ctx.fillRect(0, 0, width, height)
  ctx.drawImage(img, 0, 0, width, height)
  return { dataURL: canvas.toDataURL('image/jpeg', 0.9), width, height }
}

// The first scene (what Excalidraw 0.17 loads, kept whole by whiteboard.api sanitise): one image element, locked so a mark cannot
// move the picture, and its file, embedded as data. sanitise drops a file whose mimeType is not its data URL's own, so the type is read from it.
export function sceneOf(dataURL, width, height, now) {
  const mimeType = dataURL.slice(5, dataURL.indexOf(';'))
  const fileId = `markup-${now}`
  const image = {
    type: 'image', id: PICTURE, x: 0, y: 0, width, height, angle: 0, strokeColor: 'transparent', backgroundColor: 'transparent',
    fillStyle: 'solid', strokeWidth: 1, strokeStyle: 'solid', roughness: 0, opacity: 100, groupIds: [], frameId: null, roundness: null,
    seed: 1, version: 1, versionNonce: 1, isDeleted: false, boundElements: null, updated: now, link: null, locked: true,
    status: 'saved', fileId, scale: [1, 1],
  }
  return { elements: [image], appState: {}, files: { [fileId]: { id: fileId, mimeType, dataURL, created: now, lastRetrieved: now } } }
}

// The drawing as one flat picture on white, as Excalidraw's exportToBlob makes it; `options`: mimeType, quality, maxWidthOrHeight...
export async function flatBlob(lib, api, options) {
  if (document.fonts?.ready) await document.fonts.ready // a text mark is drawn only once its font is in
  return lib.exportToBlob({
    elements: api.getSceneElements(), files: api.getFiles(), ...options,
    appState: { ...api.getAppState(), exportBackground: true, exportWithDarkMode: false },
  })
}

// Before a board's picture is made: a save already running is waited for, and what is still unsaved is saved again.
// `saving`, `unsaved`: refs; `save`: the board's own save, which does nothing while another is running.
export async function settle({ saving, unsaved, save }) {
  if (saving.value) await new Promise((resolve) => { const stop = watch(saving, () => { stop(); resolve() }) })
  if (unsaved.value) await save()
}
