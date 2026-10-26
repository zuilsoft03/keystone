// The P1 engines are plain scripts served by construction_core (vendored, pinned: public/vendor/VENDOR.md); the shell
// loads each one once with a script tag, as the Desk pages and the portal do (P2-05, D-120).
const loading = {}

export function loadScript(src) {
  if (!loading[src]) {
    loading[src] = new Promise((resolve, reject) => {
      const s = document.createElement('script')
      s.src = src
      s.onload = resolve
      s.onerror = () => {
        delete loading[src]
        reject(new Error(`Could not load ${src}`))
      }
      document.head.appendChild(s)
    })
  }
  return loading[src]
}

export const ENGINES = {
  whiteboard: '/assets/construction_core/js/whiteboard_loader.js',
  takeoff: '/assets/construction_core/js/takeoff_canvas.js',
  pdfjs: '/assets/construction_core/vendor/pdfjs-4.10.38/',
}

// Office files the ONLYOFFICE editor opens (construction_core.office.api.DOC_TYPES).
export const OFFICE = /\.(docx|doc|odt|rtf|txt|docm|dotx|xlsx|xls|ods|csv|pptx|ppt|odp|pdf)$/i // pdf: P3-48, D-327
