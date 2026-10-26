// The Files viewer's drawing page (P3-49, D-328, D-329): mlightcad's cad-simple-viewer, in a frame of the workspace's
// FileViewer.vue. Everything it loads comes from this folder: the MTEXT and DWG workers, the LibreDWG wasm, and our own
// OFL fonts with their fonts.json (never mlightcad/cad-data, whose fonts carry no licence). The folder's policy
// (deploy/nginx/frappe.conf.template) refuses any other address, so a default left pointing at a CDN fails closed.
//
// The page bundles @mlightcad/libredwg-converter, which is GPL-3.0, so the page as a whole is offered under the
// GPL-3.0; its source is this folder, copied beside the build (source/, NOTICE.txt).
//
// The parent hands the drawing's bytes to window.ccCadView.open(); this page never fetches a drawing itself and keeps
// none in browser storage: drawings open read-only, so no markup or measurement sidecar is written, and its settings
// live under their own key.
import {
  AcApDocManager,
  AcApSettingManager,
  AcEdOpenMode,
  LIBREDWG_PARSER_WORKER_FILE,
  MTEXT_RENDERER_WORKER_FILE,
  eventBus,
} from '@mlightcad/cad-simple-viewer'
import { AcDbDatabaseConverterManager, AcDbFileType } from '@mlightcad/data-model'
import { AcDbLibreDwgConverter } from '@mlightcad/libredwg-converter'
import { FontManager } from '@mlightcad/mtext-renderer'
import { AcTrMTextRenderer } from '@mlightcad/three-renderer'

const BASE = new URL('./', location.href).href
const WORKERS = `${BASE}workers/`
// Liberation stands in for the Arial-like and SHX text fonts, Noto Sans Math for the symbols (∅ for %%c); fonts.json
// names each SHX font a drawing may ask for, so no text falls back to "?" (dev/cadviewer/fonts/fonts.json).
const TEXT_FONTS = ['liberation sans', 'noto sans math']
const SYMBOL_FONTS = ['noto sans math', 'liberation sans']
const MEASURES = { distance: 'measuredistance', area: 'measurearea' }
// Commands a read-only viewer does not offer: new or other drawings, and the exports and imports (their downloads are
// refused by the frame's sandbox anyway). The measures, pan, zoom and select stay.
const UNOFFERED = ['open', 'qnew', 'close', 'cachefont', 'entout', 'measurementexport', 'measurementimport', 'markupexport', 'markupimport']
const LAYER_EDIT = { switchCurrentLayer: false } // one layer's box never changes another layer

// Before the manager reads them: its preferences go under our own key, not the shared origin's bare "settings".
AcApSettingManager.configure({ storageKey: 'cadviewer.settings' })
// No undo, redo or delete bar over a read-only drawing; for this page only, never stored.
AcApSettingManager.instance.apply({ isShowShortCutToolbar: false }, { persist: false })

// DWG goes through LibreDWG (GPL-3.0) in its own module worker, its wasm next to it; DXF is parsed by data-model.
AcDbDatabaseConverterManager.instance.register(
  AcDbFileType.DWG,
  new AcDbLibreDwgConverter({ convertByEntityType: false, useWorker: true, parserWorkerUrl: WORKERS + LIBREDWG_PARSER_WORKER_FILE }),
)

const manager = AcApDocManager.createInstance({
  container: document.getElementById('canvas'),
  autoResize: true,
  baseUrl: BASE,
  docsBaseUrl: BASE,
  webworkerFileUrls: { mtextRender: WORKERS + MTEXT_RENDERER_WORKER_FILE, dwgParser: WORKERS + LIBREDWG_PARSER_WORKER_FILE },
  builtinOpenFileDialog: false,
  disableExport: true,
  notificationCenter: false,
})
for (const cmd of UNOFFERED) manager.commandManager.removeCmd('ACAD', cmd) // the system group (AcEdCommandStack, not exported)
// After createInstance, which sets its own preset: the main thread's chains, then the MTEXT workers' (setFontMapping
// alone never reaches the workers).
FontManager.instance.setSymbolFonts(SYMBOL_FONTS)
FontManager.instance.setDefaultFonts(TEXT_FONTS)
const fontsReady = AcTrMTextRenderer.getInstance().setDefaultFonts(TEXT_FONTS)

// Why the last open failed, in the viewer's own words (LibreDWG's reason for a DWG), for the parent's message.
let lastFailure = ''
eventBus.on('failed-to-open-file', (e) => { lastFailure = e?.errorMessage || e?.errorCode || '' })

const layerListeners = new Set()
let boundStore = null

// A layer is shown when it is on and not frozen: the box the parent draws for it.
function layers() {
  return (manager.curDocument?.layerStore?.getLayers() || []).map(({ name, cssColor, isOn, isFrozen }) => ({ name, color: cssColor, on: isOn && !isFrozen }))
}
function bindLayers() {
  const store = manager.curDocument?.layerStore
  if (!store || store === boundStore) return
  boundStore = store
  store.events.changed.addEventListener(() => layerListeners.forEach((fn) => fn(layers())))
}

// What the parent calls (FileViewer.vue). Same origin, so it calls these directly; every answer is plain data.
window.ccCadView = {
  // `profile` prints the viewer's own stage timings to the console (its OPENPROF), for timing a slow drawing.
  async open(name, bytes, { profile = false } = {}) {
    await fontsReady.catch(() => {})
    lastFailure = ''
    // into this page's own buffer: the parent's comes from another realm, which the parser's instanceof refuses
    const own = new Uint8Array(bytes.byteLength)
    own.set(new Uint8Array(bytes))
    // drawNoPlotLayers: layers marked not to plot are still shown on screen, as AutoCAD and Open CAD Studio show them
    const options = { mode: AcEdOpenMode.Read, drawNoPlotLayers: true, sysVars: profile ? { openprof: true } : {} }
    const ok = await manager.openDocument(String(name), own.buffer, options).catch((e) => {
      lastFailure ||= String(e?.message || e)
      return false
    })
    if (!ok) return { ok: false, error: `The drawing viewer could not read this drawing${lastFailure ? ` (${lastFailure})` : ''}.` }
    bindLayers()
    return { ok: true, layers: layers() }
  },
  fit() {
    manager.curView.zoomToFitDrawing()
  },
  // Where the view looks and how much of the drawing it shows, so a pan or zoom can be seen from outside.
  view() {
    const v = manager.curView
    const width = document.getElementById('canvas').clientWidth
    if (!width || !v?.activeLayoutView) return null // no drawing or no canvas size yet
    try {
      const a = v.screenToWorld({ x: 0, y: 0 })
      const b = v.screenToWorld({ x: width, y: 0 })
      return { x: v.center.x, y: v.center.y, span: Math.abs(b.x - a.x) }
    } catch {
      return null
    }
  },
  measure(kind) {
    const cmd = MEASURES[kind]
    if (cmd) manager.sendStringToExecute(cmd)
  },
  clearMeasures() {
    manager.sendStringToExecute('clearmeasurements')
  },
  layers,
  // Shows a layer (on, and thawed if frozen) or hides it (off); answers whether it is shown now.
  setLayer(name, on) {
    const service = manager.curDocument.layerStore.getLayerService()
    const layer = String(name)
    if (on) {
      service.setLayerFrozen(layer, false, LAYER_EDIT)
      service.setLayerOn(layer, true, LAYER_EDIT)
    } else {
      service.setLayerOn(layer, false, LAYER_EDIT)
    }
    return !!layers().find((l) => l.name === layer)?.on
  },
  onLayers(fn) {
    layerListeners.add(fn)
    return () => layerListeners.delete(fn)
  },
}
window.dispatchEvent(new Event('cc-cadview-ready'))
