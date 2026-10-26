// Loads the vendored React 18.3.1 and Excalidraw 0.17.6 bundles once (public/vendor/VENDOR.md), for the staff
// Board page and the client portal. Exposes window.ccWhiteboard.load() -> Promise<ExcalidrawLib>.
(function () {
	const BASE = "/assets/construction_core/vendor/";
	const FILES = [
		"react-18.3.1/react.production.min.js",
		"react-18.3.1/react-dom.production.min.js",
		"excalidraw-0.17.6/excalidraw.production.min.js",
	];
	let loading = null;

	function script(src) {
		return new Promise((resolve, reject) => {
			const s = document.createElement("script");
			s.src = src;
			s.onload = resolve;
			s.onerror = () => reject(new Error("Could not load " + src));
			document.head.appendChild(s);
		});
	}

	window.ccWhiteboard = {
		load() {
			if (window.ExcalidrawLib) return Promise.resolve(window.ExcalidrawLib);
			if (!loading) {
				window.EXCALIDRAW_ASSET_PATH = BASE + "excalidraw-0.17.6/";
				loading = FILES.reduce((p, f) => p.then(() => script(BASE + f)), Promise.resolve())
					.then(() => window.ExcalidrawLib);
			}
			return loading;
		},
		// Only what the server keeps (whiteboard/api.py sanitise): elements, background, grid, image files.
		serialise(elements, appState, files) {
			return JSON.stringify({
				elements: elements.filter((e) => !e.isDeleted),
				appState: { viewBackgroundColor: appState.viewBackgroundColor, gridSize: appState.gridSize },
				files: files || {},
			});
		},
	};
})();
