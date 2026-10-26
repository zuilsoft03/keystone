// Takeoff canvas (P1-16; reused by P1-18 for PDF): draws plain geometry in world units (y up), with pan, wheel
// zoom, layer visibility, vertex snapping and the measuring tools (length, area, count, calibrate).
// Quantities shown here are a live preview only; the server computes the saved ones (construction_core.takeoff).
(function () {
	const SNAP_PX = 10;

	class CcTakeoffCanvas {
		constructor(container, opts = {}) {
			this.opts = opts;
			this.canvas = document.createElement("canvas");
			this.canvas.style.cssText = "width:100%;height:100%;display:block;cursor:crosshair;background:#fff;touch-action:none";
			container.appendChild(this.canvas);
			this.ctx = this.canvas.getContext("2d");
			this.items = [];
			this.hidden = new Set();
			this.overlays = []; // [{color, kind, shapes: [[x,y,...]]}]
			this.tool = "pan";
			this.points = [];
			this.view = { s: 1, ox: 0, oy: 0 };
			this.background = null; // P1-18: {image, x, y, w, h} in world units
			this.bind();
			new ResizeObserver(() => this.resize()).observe(container);
		}

		// --- data ---------------------------------------------------------------------------------------

		setGeometry(geo) {
			this.items = geo.items || [];
			this.extents = geo.extents || [0, 0, 1, 1];
			this.vertices = [];
			for (const i of this.items) {
				if (i.t === "l" || i.t === "pl") for (let k = 0; k < i.p.length; k += 2) this.vertices.push(i.p[k], i.p[k + 1]);
				else if (i.t === "c") this.vertices.push(i.x, i.y0);
			}
			this.resize();
			this.fit();
		}

		setOverlays(overlays) {
			this.overlays = overlays || [];
			this.draw();
		}

		setLayerVisible(layer, visible) {
			visible ? this.hidden.delete(layer) : this.hidden.add(layer);
			this.draw();
		}

		setTool(tool) {
			this.tool = tool;
			this.points = [];
			this.canvas.style.cursor = tool === "pan" ? "grab" : "crosshair";
			this.draw();
		}

		// --- view -----------------------------------------------------------------------------------------

		resize() {
			const r = this.canvas.getBoundingClientRect();
			this.dpr = window.devicePixelRatio || 1;
			this.canvas.width = Math.max(1, r.width * this.dpr);
			this.canvas.height = Math.max(1, r.height * this.dpr);
			this.draw();
		}

		fit() {
			const [x0, y0, x1, y1] = this.extents;
			const w = this.canvas.width / this.dpr, h = this.canvas.height / this.dpr;
			const s = 0.92 * Math.min(w / Math.max(x1 - x0, 1e-9), h / Math.max(y1 - y0, 1e-9));
			this.view = { s, ox: w / 2 - s * (x0 + x1) / 2, oy: h / 2 + s * (y0 + y1) / 2 };
			this.draw();
		}

		toScreen(x, y) {
			return [this.view.ox + x * this.view.s, this.view.oy - y * this.view.s];
		}

		toWorld(sx, sy) {
			return [(sx - this.view.ox) / this.view.s, (this.view.oy - sy) / this.view.s];
		}

		snap(sx, sy) {
			if (this.opts.snap === false || !this.vertices) return this.toWorld(sx, sy);
			let best = null, bd = SNAP_PX * SNAP_PX;
			const v = this.vertices;
			for (let k = 0; k < v.length; k += 2) {
				const [px, py] = this.toScreen(v[k], v[k + 1]);
				const d = (px - sx) ** 2 + (py - sy) ** 2;
				if (d < bd) { bd = d; best = [v[k], v[k + 1]]; }
			}
			return best || this.toWorld(sx, sy);
		}

		// --- drawing --------------------------------------------------------------------------------------

		draw() {
			if (this._raf) return;
			this._raf = requestAnimationFrame(() => { this._raf = null; this.paint(); });
		}

		paint() {
			const c = this.ctx, { s, ox, oy } = this.view;
			c.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
			c.clearRect(0, 0, this.canvas.width, this.canvas.height);
			c.save();
			c.translate(ox, oy);
			c.scale(s, -s);
			if (this.background) {
				const b = this.background;
				c.save();
				c.scale(1, -1); // images are drawn y-down
				c.imageSmoothingEnabled = true;
				c.imageSmoothingQuality = "high"; // a large page shrunk to the view must not drop thin lines
				c.drawImage(b.image, b.x, -(b.y + b.h), b.w, b.h);
				c.restore();
			}
			c.lineWidth = 1 / s;
			c.strokeStyle = "#333";
			c.beginPath();
			for (const i of this.items) {
				if (this.hidden.has(i.y)) continue;
				if (i.t === "l") { c.moveTo(i.p[0], i.p[1]); c.lineTo(i.p[2], i.p[3]); }
				else if (i.t === "pl") {
					c.moveTo(i.p[0], i.p[1]);
					for (let k = 2; k < i.p.length; k += 2) c.lineTo(i.p[k], i.p[k + 1]);
					if (i.c) c.closePath();
				} else if (i.t === "c") { c.moveTo(i.x + i.r, i.y0); c.arc(i.x, i.y0, i.r, 0, 2 * Math.PI); }
			}
			c.stroke();
			c.fillStyle = "#555";
			for (const i of this.items) {
				if (i.t !== "tx" || this.hidden.has(i.y) || i.h * s < 4) continue;
				c.save();
				c.translate(i.x, i.y0);
				c.scale(1, -1);
				c.rotate((-(i.a || 0) * Math.PI) / 180);
				c.font = `${i.h}px sans-serif`;
				c.fillText(i.s, 0, 0);
				c.restore();
			}
			c.restore();
			for (const o of this.overlays) for (const shape of o.shapes) this.paintShape(shape, o.kind, o.color, 0.35);
			if (this.points.length) {
				const kind = this.tool === "area" ? "Area" : this.tool === "count" ? "Count" : "Length";
				this.paintShape(this.points.concat(this.hover || []), kind, "#1971c2", 0.2);
			}
			if (this.hover && this.tool !== "pan") {
				const [hx, hy] = this.toScreen(this.hover[0], this.hover[1]);
				c.strokeStyle = "#1971c2";
				c.lineWidth = 1.5;
				c.strokeRect(hx - 4, hy - 4, 8, 8);
			}
		}

		paintShape(p, kind, color, alpha) {
			const c = this.ctx;
			const pts = [];
			for (let k = 0; k < p.length; k += 2) pts.push(this.toScreen(p[k], p[k + 1]));
			c.strokeStyle = color;
			c.fillStyle = color;
			c.lineWidth = 2.5;
			if (kind === "Count") {
				for (const [x, y] of pts) { c.beginPath(); c.arc(x, y, 6, 0, 2 * Math.PI); c.fill(); }
				return;
			}
			c.beginPath();
			pts.forEach(([x, y], k) => (k ? c.lineTo(x, y) : c.moveTo(x, y)));
			if (kind === "Area" && pts.length > 2) {
				c.closePath();
				c.globalAlpha = alpha;
				c.fill();
				c.globalAlpha = 1;
			}
			c.stroke();
		}

		// --- input ----------------------------------------------------------------------------------------

		bind() {
			const cv = this.canvas;
			let drag = null;
			const pos = (e) => { const r = cv.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
			cv.addEventListener("wheel", (e) => {
				e.preventDefault();
				const [sx, sy] = pos(e), [wx, wy] = this.toWorld(sx, sy);
				const f = Math.exp(-e.deltaY * 0.0015);
				this.view.s *= f;
				this.view.ox = sx - wx * this.view.s;
				this.view.oy = sy + wy * this.view.s;
				this.draw();
			}, { passive: false });
			cv.addEventListener("pointerdown", (e) => {
				if (this.tool === "pan" || e.button === 1 || e.shiftKey) {
					drag = { x: e.clientX, y: e.clientY, ox: this.view.ox, oy: this.view.oy };
					cv.setPointerCapture(e.pointerId);
					return;
				}
				if (e.button !== 0) return;
				const [sx, sy] = pos(e);
				const p = this.snap(sx, sy);
				this.points.push(p[0], p[1]);
				if (this.tool === "calibrate" && this.points.length === 4) return this.finish();
				this.emitPreview();
				this.draw();
			});
			cv.addEventListener("pointermove", (e) => {
				if (drag) {
					this.view.ox = drag.ox + e.clientX - drag.x;
					this.view.oy = drag.oy + e.clientY - drag.y;
					return this.draw();
				}
				if (this.tool === "pan") return;
				const [sx, sy] = pos(e);
				this.hover = this.snap(sx, sy);
				this.draw();
			});
			cv.addEventListener("pointerup", () => (drag = null));
			cv.addEventListener("dblclick", (e) => { e.preventDefault(); this.finish(); });
			cv.tabIndex = 0;
			cv.addEventListener("keydown", (e) => {
				if (e.key === "Enter") this.finish();
				else if (e.key === "Escape") { this.points = []; this.emitPreview(); this.draw(); }
				else if (e.key === "Backspace") { this.points.splice(-2, 2); this.emitPreview(); this.draw(); }
			});
		}

		emitPreview() {
			this.opts.onPreview && this.opts.onPreview(this.tool, this.points.slice());
		}

		finish() {
			const pts = this.points.slice();
			// a double click also adds its own click points; drop repeated last points
			while (pts.length >= 4 && pts[pts.length - 1] === pts[pts.length - 3] && pts[pts.length - 2] === pts[pts.length - 4]) pts.splice(-2, 2);
			this.points = [];
			this.emitPreview();
			this.draw();
			if (pts.length && this.opts.onFinish) this.opts.onFinish(this.tool, pts);
		}
	}

	// Shared with the server's rules (construction_core.takeoff.dxf): a live preview only.
	CcTakeoffCanvas.length = (p) => { let s = 0; for (let k = 0; k + 3 < p.length; k += 2) s += Math.hypot(p[k + 2] - p[k], p[k + 3] - p[k + 1]); return s; };
	CcTakeoffCanvas.area = (p) => {
		const n = p.length / 2; if (n < 3) return 0; let s = 0;
		for (let k = 0; k < n; k++) { const j = (k + 1) % n; s += p[2 * k] * p[2 * j + 1] - p[2 * j] * p[2 * k + 1]; }
		return Math.abs(s) / 2;
	};
	window.CcTakeoffCanvas = CcTakeoffCanvas;
})();
