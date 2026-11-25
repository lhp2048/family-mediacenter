/**
 * Embedded e-book reader (materials/embed) — scroll / paginated modes, zoom, pan, lazy load.
 */
function materialEmbedPage() {
  const fileInfo = window.__MATERIAL_FILE_INFO__ || {};
  /** Non-reactive handles — Alpine proxies break PDF.js / EPUB.js objects. */
  const store = {
    pdfDoc: null,
    pdfUrl: '',
    pdfRenderedPages: new Set(),
    pdfScrollObserver: null,
    epubBook: null,
    epubRendition: null,
  };

  const PDF_SCROLL_PREFETCH_PX = 480;
  const textBook = {
    url: '',
    totalBytes: 0,
    pageStarts: [0],
    avgPageBytes: 16 * 1024,
    charBudget: 0,
    bytes: null,
    token: 0,
    exactCount: 0,
    abort: null,
  };

  function utf8Skip(buf) {
    let index = 0;
    while (index < buf.length && (buf[index] & 0xc0) === 0x80) index += 1;
    return index;
  }

  function textSliceFit(el, text, limit) {
    const cap = Math.min(text.length, 20000);
    if (!cap) return 0;
    el.textContent = text.slice(0, cap);
    if (el.scrollHeight <= limit) return cap;
    let lo = 1;
    let hi = cap;
    let best = 1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      el.textContent = text.slice(0, mid);
      if (el.scrollHeight <= limit) {
        best = mid;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }
    return best;
  }

  function snapPageEnd(text, fit) {
    if (fit >= text.length) return text.length;
    const nextBreak = text.indexOf('\n', fit);
    if (nextBreak !== -1 && nextBreak - fit <= 120) return nextBreak + 1;
    return fit;
  }

  return {
    title: fileInfo.name || '阅读',
    previewUrl: fileInfo.public_url || '',
    previewKind: '',
    previewHtml: '',
    previewText: '',
    previewLoading: false,
    previewError: '',

    viewMode: 'page',
    zoom: 1,
    panX: 0,
    panY: 0,
    isPanning: false,
    panStartX: 0,
    panStartY: 0,
    panOriginX: 0,
    panOriginY: 0,

    pdfPageCount: 0,
    pdfCurrentPage: 1,
    pdfRenderToken: 0,

    epubRenderToken: 0,

    textPageCount: 1,
    textCurrentPage: 1,
    textPageHeight: 640,
    textReady: false,

    swipeStartX: 0,
    swipeStartY: 0,
    swipeActive: false,

    supportsPageMode() {
      return ['pdf', 'epub', 'markdown', 'text'].includes(this.previewKind);
    },

    zoomLabel() {
      return `${Math.round(this.zoom * 100)}%`;
    },

    transformStyle() {
      const parts = [];
      if (this.viewMode === 'page' && this.previewKind === 'markdown') {
        const offset = (this.textCurrentPage - 1) * this.textPageHeight;
        parts.push(`translateY(-${offset}px)`);
      } else if (this.previewKind !== 'text' && (this.panX || this.panY)) {
        parts.push(`translate(${this.panX}px, ${this.panY}px)`);
      }
      if (this.zoom !== 1 && this.previewKind !== 'text') {
        parts.push(`scale(${this.zoom})`);
      }
      if (!parts.length) return '';
      return {
        transform: parts.join(' '),
        transformOrigin: 'top center',
      };
    },

    viewportClass() {
      const classes = [];
      if (this.viewMode === 'page') classes.push('is-page-mode');
      if (this.zoom > 1) classes.push('is-zoomed');
      if (this.isPanning) classes.push('is-panning');
      return classes.join(' ');
    },

    textPageIndicator() {
      if (this.previewKind === 'text' && !textBook.exactCount) {
        return `${this.textCurrentPage} / 约 ${this.textPageCount}`;
      }
      return `${this.textCurrentPage} / ${this.textPageCount}`;
    },

    textAtEnd() {
      if (this.previewKind !== 'text') return false;
      if (textBook.exactCount) return this.textCurrentPage >= textBook.exactCount;
      const next = textBook.pageStarts[this.textCurrentPage];
      return textBook.totalBytes > 0 && next != null && next >= textBook.totalBytes;
    },

    kindFromUrl(url, hint) {
      if (hint && ['markdown', 'pdf', 'epub', 'text'].includes(hint)) return hint;
      const ext = (url || '').split('?')[0].split('.').pop().toLowerCase();
      if (ext === 'md') return 'markdown';
      if (ext === 'pdf') return 'pdf';
      if (ext === 'epub') return 'epub';
      if (ext === 'txt') return 'text';
      return 'unknown';
    },

    resetPan() {
      this.panX = 0;
      this.panY = 0;
    },

    zoomIn() {
      this.zoom = Math.min(3, Math.round((this.zoom + 0.25) * 100) / 100);
      if (this.previewKind === 'text') void this.refitText();
    },

    zoomOut() {
      this.zoom = Math.max(0.5, Math.round((this.zoom - 0.25) * 100) / 100);
      if (this.zoom <= 1) this.resetPan();
      if (this.previewKind === 'text') void this.refitText();
    },

    resetZoom() {
      this.zoom = 1;
      this.resetPan();
      if (this.previewKind === 'text') void this.refitText();
    },

    detachPdfScrollObserver() {
      if (store.pdfScrollObserver) {
        store.pdfScrollObserver.disconnect();
        store.pdfScrollObserver = null;
      }
    },

    async setViewMode(mode) {
      if (this.viewMode === mode) return;
      this.viewMode = mode;
      this.resetZoom();
      this.textCurrentPage = 1;
      await this.$nextTick();
      if (this.previewKind === 'pdf' && store.pdfDoc) {
        await this.applyPdfView();
      } else if (this.previewKind === 'epub') {
        await this.renderEpubPreview(this.previewUrl, false);
      } else if (this.previewKind === 'markdown') {
        await this.$nextTick();
        this.measureTextPages();
      } else if (this.previewKind === 'text') {
        await this.$nextTick();
        if (mode === 'scroll') {
          await this.enterTextScroll();
        } else {
          const pre = this.$refs.textContent;
          if (pre) pre.style.top = '';
          if (this.$refs.viewport) this.$refs.viewport.scrollTop = 0;
          this.updateTextSpacer();
          await this.showTextAt(this.textCurrentPage);
        }
      }
    },

    clearPdfPreview() {
      this.detachPdfScrollObserver();
      store.pdfRenderedPages.clear();
      const container = this.$refs.pdfContainer;
      if (container) container.innerHTML = '';
    },

    clearEpubPreview() {
      if (store.epubRendition) {
        try { store.epubRendition.destroy(); } catch (_) {}
        store.epubRendition = null;
      }
      if (store.epubBook) {
        try { store.epubBook.destroy(); } catch (_) {}
        store.epubBook = null;
      }
      const container = this.$refs.epubContainer;
      if (container) container.innerHTML = '';
    },

    viewportHeight() {
      const viewport = this.$refs.viewport;
      return Math.max((viewport && viewport.clientHeight) || 0, 480);
    },

    pdfContainerWidth() {
      const viewport = this.$refs.viewport;
      const width = (viewport && viewport.clientWidth) || 320;
      return Math.max(width - 24, 280);
    },

    async ensurePdfLoaded(url) {
      if (store.pdfDoc) return store.pdfDoc;
      const lib = window.pdfjsLib;
      if (!lib) throw new Error('PDF 预览组件未加载');
      store.pdfUrl = url;
      store.pdfDoc = await lib.getDocument({
        url,
        disableRange: false,
        disableStream: true,
        withCredentials: false,
      }).promise;
      this.pdfPageCount = store.pdfDoc.numPages;
      if (this.pdfCurrentPage > this.pdfPageCount) {
        this.pdfCurrentPage = this.pdfPageCount;
      }
      return store.pdfDoc;
    },

    pdfPageScale(page) {
      const baseViewport = page.getViewport({ scale: 1 });
      const maxWidth = this.pdfContainerWidth();
      return Math.max(0.6, Math.min(1.6, maxWidth / baseViewport.width));
    },

    async renderPdfPageCanvas(page, target) {
      const scale = this.pdfPageScale(page);
      const viewport = page.getViewport({ scale });
      const canvas = document.createElement('canvas');
      canvas.className = 'material-pdf-page';
      canvas.dataset.rendered = '1';
      const context = canvas.getContext('2d');
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      target.appendChild(canvas);
      await page.render({ canvasContext: context, viewport }).promise;
      return canvas.getBoundingClientRect().height || canvas.height;
    },

    isPdfPageRendered(pageNum) {
      return store.pdfRenderedPages.has(pageNum);
    },

    markPdfPageRendered(pageNum) {
      store.pdfRenderedPages.add(pageNum);
    },

    findPdfPageSlot(container, pageNum) {
      return container.querySelector(`.material-pdf-page-slot[data-page-num="${pageNum}"]`);
    },

    async renderPdfPageSlot(pageNum, container, pdfDoc, token) {
      if (this.isPdfPageRendered(pageNum)) return;
      const slot = this.findPdfPageSlot(container, pageNum);
      if (!slot || slot.dataset.rendered === '1') return;
      this.markPdfPageRendered(pageNum);
      slot.classList.add('is-loading');
      try {
        const page = await pdfDoc.getPage(pageNum);
        if (token !== this.pdfRenderToken) return;
        slot.innerHTML = '';
        slot.classList.remove('is-loading');
        slot.dataset.rendered = '1';
        const height = await this.renderPdfPageCanvas(page, slot);
        if (height > 0) {
          slot.style.minHeight = `${height}px`;
        }
      } catch (e) {
        if (token !== this.pdfRenderToken) return;
        slot.classList.remove('is-loading');
        slot.innerHTML = `<p class="empty-hint">第 ${pageNum} 页加载失败</p>`;
        console.error(e);
      }
    },

    attachPdfScrollObserver(container, pdfDoc, token) {
      this.detachPdfScrollObserver();
      const root = this.$refs.viewport;
      if (!root) return;
      const observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (!entry.isIntersecting) return;
            const pageNum = Number.parseInt(entry.target.dataset.pageNum || '', 10);
            if (!Number.isFinite(pageNum)) return;
            void this.renderPdfPageSlot(pageNum, container, pdfDoc, token);
          });
        },
        { root, rootMargin: `${PDF_SCROLL_PREFETCH_PX}px 0px`, threshold: 0.01 },
      );
      container.querySelectorAll('.material-pdf-page-slot').forEach((slot) => {
        observer.observe(slot);
      });
      store.pdfScrollObserver = observer;
    },

    async setupPdfScrollLazy(container, pdfDoc, token) {
      container.innerHTML = '';
      store.pdfRenderedPages.clear();
      const firstPage = await pdfDoc.getPage(1);
      if (token !== this.pdfRenderToken) return;
      const estimatedHeight = Math.ceil(this.pdfPageScale(firstPage) * firstPage.getViewport({ scale: 1 }).height) + 16;

      for (let pageNum = 1; pageNum <= pdfDoc.numPages; pageNum += 1) {
        const slot = document.createElement('div');
        slot.className = 'material-pdf-page-slot';
        slot.dataset.pageNum = String(pageNum);
        slot.style.minHeight = `${estimatedHeight}px`;
        slot.innerHTML = `<p class="empty-hint pdf-page-placeholder">第 ${pageNum} 页</p>`;
        container.appendChild(slot);
      }

      await this.renderPdfPageSlot(1, container, pdfDoc, token);
      if (token !== this.pdfRenderToken) return;
      if (pdfDoc.numPages > 1) {
        await this.renderPdfPageSlot(2, container, pdfDoc, token);
      }
      this.attachPdfScrollObserver(container, pdfDoc, token);
    },

    async renderPdfPageMode(container, pdfDoc, token) {
      container.innerHTML = '';
      store.pdfRenderedPages.clear();
      const page = await pdfDoc.getPage(this.pdfCurrentPage);
      if (token !== this.pdfRenderToken) return;
      this.markPdfPageRendered(this.pdfCurrentPage);
      await this.renderPdfPageCanvas(page, container);
      if (token !== this.pdfRenderToken) return;
      const prefetch = [this.pdfCurrentPage - 1, this.pdfCurrentPage + 1];
      prefetch.forEach((pageNum) => {
        if (pageNum < 1 || pageNum > pdfDoc.numPages) return;
        void pdfDoc.getPage(pageNum).catch(() => {});
      });
    },

    async applyPdfView() {
      const container = this.$refs.pdfContainer;
      const pdfDoc = store.pdfDoc;
      if (!container || !pdfDoc) return;
      const token = ++this.pdfRenderToken;
      this.detachPdfScrollObserver();
      try {
        if (this.viewMode === 'page') {
          container.classList.remove('is-scroll-mode');
          await this.renderPdfPageMode(container, pdfDoc, token);
        } else {
          container.classList.add('is-scroll-mode');
          await this.setupPdfScrollLazy(container, pdfDoc, token);
        }
      } catch (e) {
        if (token !== this.pdfRenderToken) return;
        this.previewError = 'PDF 渲染失败';
        console.error(e);
      }
    },

    async renderPdfPreview(url) {
      const container = this.$refs.pdfContainer;
      if (!container) {
        this.previewError = 'PDF 预览容器未就绪';
        return;
      }
      const token = ++this.pdfRenderToken;
      this.clearPdfPreview();
      store.pdfDoc = null;
      store.pdfUrl = '';
      this.pdfPageCount = 0;
      this.pdfCurrentPage = 1;
      try {
        await this.ensurePdfLoaded(url);
        if (token !== this.pdfRenderToken) return;
        await this.applyPdfView();
      } catch (e) {
        if (token !== this.pdfRenderToken) return;
        this.previewError = 'PDF 在线阅读失败';
        console.error(e);
      }
    },

    async renderEpubPreview(url) {
      if (!window.ePub) {
        this.previewError = 'EPUB 预览组件未加载';
        return;
      }
      const token = ++this.epubRenderToken;
      this.clearEpubPreview();
      await this.$nextTick();
      const container = this.$refs.epubContainer;
      if (!container || token !== this.epubRenderToken) return;
      try {
        store.epubBook = window.ePub(url, { openAs: 'epub' });
        const height = this.viewportHeight();
        container.style.height = `${height}px`;
        store.epubRendition = store.epubBook.renderTo(container, {
          width: '100%',
          height: `${height}px`,
          flow: this.viewMode === 'page' ? 'paginated' : 'scrolled-doc',
          spread: 'none',
          allowScriptedContent: false,
        });
        await store.epubRendition.display();
      } catch (e) {
        if (token !== this.epubRenderToken) return;
        this.previewError = 'EPUB 在线阅读失败';
        console.error(e);
      }
    },

    measureTextPages() {
      const viewport = this.$refs.viewport;
      const content = this.previewKind === 'markdown'
        ? this.$refs.mdContent
        : this.$refs.textContent;
      if (!viewport || !content) {
        this.textPageCount = 1;
        this.textCurrentPage = 1;
        return;
      }
      const viewportHeight = Math.max(viewport.clientHeight - 8, 320);
      this.textPageHeight = viewportHeight;
      const totalHeight = content.scrollHeight;
      this.textPageCount = Math.max(1, Math.ceil(totalHeight / this.textPageHeight));
      if (this.textCurrentPage > this.textPageCount) {
        this.textCurrentPage = this.textPageCount;
      }
    },

    scheduleLayoutRefresh() {
      if (this._layoutTimer) clearTimeout(this._layoutTimer);
      this._layoutTimer = setTimeout(() => {
        const viewport = this.$refs.viewport;
        const height = viewport ? viewport.clientHeight : 0;
        const width = viewport ? viewport.clientWidth : 0;
        if (this.previewKind === 'text' && height === this._lastH && width === this._lastW) return;
        this._lastH = height;
        this._lastW = width;
        if (this.previewKind === 'markdown') {
          this.measureTextPages();
        } else if (this.previewKind === 'text') {
          void this.refitText();
        } else if (this.previewKind === 'pdf' && store.pdfDoc) {
          void this.applyPdfView();
        }
      }, 120);
    },

    onViewportWheel(event) {
      if (this.viewMode !== 'page' || this.zoom > 1 || this.isPanning) return;
      if (!this.supportsPageMode()) return;
      event.preventDefault();
      if (event.deltaY > 16) void this.nextPage();
      else if (event.deltaY < -16) void this.prevPage();
    },

    async prevPage() {
      if (this.viewMode !== 'page') return;
      if (this.previewKind === 'pdf') {
        if (this.pdfCurrentPage <= 1) return;
        this.pdfCurrentPage -= 1;
        await this.applyPdfView();
        return;
      }
      if (this.previewKind === 'epub' && store.epubRendition) {
        await store.epubRendition.prev();
        return;
      }
      if (this.previewKind === 'markdown') {
        if (this.textCurrentPage <= 1) return;
        this.textCurrentPage -= 1;
        return;
      }
      if (this.previewKind === 'text') {
        if (this.textCurrentPage <= 1) return;
        await this.showTextAt(this.textCurrentPage - 1);
      }
    },

    async nextPage() {
      if (this.viewMode !== 'page') return;
      if (this.previewKind === 'pdf') {
        if (this.pdfCurrentPage >= this.pdfPageCount) return;
        this.pdfCurrentPage += 1;
        await this.applyPdfView();
        return;
      }
      if (this.previewKind === 'epub' && store.epubRendition) {
        await store.epubRendition.next();
        return;
      }
      if (this.previewKind === 'markdown') {
        if (this.textCurrentPage >= this.textPageCount) return;
        this.textCurrentPage += 1;
        return;
      }
      if (this.previewKind === 'text') {
        if (this.textAtEnd()) return;
        await this.showTextAt(this.textCurrentPage + 1);
      }
    },

    onViewportPointerDown(event) {
      if (event.target.closest('.materials-embed-toolbar')) return;
      if (this.zoom > 1 && event.button === 0) {
        this.isPanning = true;
        this.panOriginX = this.panX;
        this.panOriginY = this.panY;
        this.panStartX = event.clientX;
        this.panStartY = event.clientY;
        event.currentTarget.setPointerCapture(event.pointerId);
        return;
      }
      if (this.viewMode === 'page' && this.supportsPageMode() && this.zoom <= 1 && event.button === 0) {
        this.swipeActive = true;
        this.swipeStartX = event.clientX;
        this.swipeStartY = event.clientY;
      }
    },

    onViewportPointerMove(event) {
      if (this.isPanning) {
        this.panX = this.panOriginX + (event.clientX - this.panStartX);
        this.panY = this.panOriginY + (event.clientY - this.panStartY);
      }
    },

    async onViewportPointerUp(event) {
      if (this.isPanning) {
        this.isPanning = false;
        try { event.currentTarget.releasePointerCapture(event.pointerId); } catch (_) {}
        return;
      }
      if (!this.swipeActive || this.viewMode !== 'page' || this.zoom > 1) {
        this.swipeActive = false;
        return;
      }
      const dx = event.clientX - this.swipeStartX;
      const dy = event.clientY - this.swipeStartY;
      this.swipeActive = false;
      if (Math.abs(dx) < 48 || Math.abs(dx) < Math.abs(dy)) return;
      if (dx < 0) await this.nextPage();
      else await this.prevPage();
    },

    applyTextFont() {
      const el = this.$refs.textContent;
      if (!el) return;
      el.style.fontSize = `${(1.05 * this.zoom).toFixed(3)}rem`;
    },

    updateTextSpacer() {
      const spacer = this.$refs.textSpacer;
      if (!spacer) return;
      if (this.viewMode !== 'scroll' || !textBook.totalBytes || !textBook.avgPageBytes) {
        spacer.style.height = '0px';
        return;
      }
      const pages = textBook.totalBytes / textBook.avgPageBytes;
      spacer.style.height = `${Math.max(this.viewportHeight(), pages * this.viewportHeight())}px`;
    },

    async readTextWindow(byteStart, token, want) {
      const size = Math.max(want || 0, 4096);
      if (textBook.bytes) {
        const end = Math.min(textBook.bytes.length, byteStart + size);
        const slice = textBook.bytes.subarray(byteStart, end);
        const skipped = byteStart > 0 ? utf8Skip(slice) : 0;
        return {
          text: new TextDecoder('utf-8').decode(slice.subarray(skipped)),
          skipped,
          more: end < textBook.bytes.length,
        };
      }
      if (textBook.abort) textBook.abort.abort();
      const ctrl = new AbortController();
      textBook.abort = ctrl;
      let res;
      try {
        res = await fetch(textBook.url, {
          headers: { Range: `bytes=${byteStart}-${byteStart + size - 1}` },
          signal: ctrl.signal,
        });
      } catch (err) {
        if (err.name === 'AbortError') return null;
        throw err;
      }
      if (token !== textBook.token) return null;
      if (!res.ok && res.status !== 206) throw new Error('加载失败');
      const buf = new Uint8Array(await res.arrayBuffer());
      if (token !== textBook.token) return null;
      const totalMatch = /\/(\d+)\s*$/.exec(res.headers.get('content-range') || '');
      if (totalMatch) textBook.totalBytes = Number(totalMatch[1]);
      if (res.status === 200) {
        textBook.bytes = buf;
        textBook.totalBytes = buf.length;
        const end = Math.min(buf.length, byteStart + size);
        const slice = buf.subarray(byteStart, end);
        const skipped = byteStart > 0 ? utf8Skip(slice) : 0;
        return {
          text: new TextDecoder('utf-8').decode(slice.subarray(skipped)),
          skipped,
          more: end < buf.length,
        };
      }
      const skipped = byteStart > 0 ? utf8Skip(buf) : 0;
      const receivedEnd = byteStart + buf.length;
      return {
        text: new TextDecoder('utf-8').decode(buf.subarray(skipped)),
        skipped,
        more: textBook.totalBytes ? receivedEnd < textBook.totalBytes : buf.length >= size,
      };
    },

    async showTextAt(page, token) {
      const myToken = token == null ? textBook.token : token;
      if (page < 1) return;
      const start = textBook.pageStarts[page - 1];
      if (start == null) return;
      if (textBook.totalBytes && start >= textBook.totalBytes) {
        textBook.exactCount = Math.max(1, page - 1);
        this.textPageCount = textBook.exactCount;
        if (this.textCurrentPage > this.textPageCount) this.textCurrentPage = this.textPageCount;
        return;
      }
      await this.$nextTick();
      const el = this.$refs.textContent;
      const viewport = this.$refs.viewport;
      if (!el || !viewport || myToken !== textBook.token) return;
      for (let wait = 0; wait < 6 && el.clientWidth < 40; wait += 1) {
        await new Promise((resolve) => requestAnimationFrame(resolve));
      }
      this.applyTextFont();
      const limit = Math.max(viewport.clientHeight - 24, 320);
      let want = Math.max((textBook.avgPageBytes || 16384) * 2, 64 * 1024);
      let windowText = null;
      let fit = textBook.charBudget;
      for (let attempt = 0; attempt < 4; attempt += 1) {
        windowText = await this.readTextWindow(start, myToken, want);
        if (!windowText || myToken !== textBook.token) return;
        if (!fit) {
          el.style.visibility = 'hidden';
          fit = textSliceFit(el, windowText.text, limit);
          el.style.visibility = '';
          if (fit > 0) textBook.charBudget = fit;
        }
        if (!windowText.more || (fit && fit < windowText.text.length)) break;
        want *= 2;
      }
      if (!windowText || myToken !== textBook.token) return;
      const end = snapPageEnd(windowText.text, Math.min(fit || windowText.text.length, windowText.text.length));
      const shown = windowText.text.slice(0, end);
      if (!shown) {
        textBook.exactCount = Math.max(1, page - 1);
        this.textPageCount = textBook.exactCount || 1;
        return;
      }
      el.textContent = shown;
      const consumed = new TextEncoder().encode(shown).length + windowText.skipped;
      const nextStart = start + Math.max(consumed, 1);
      textBook.pageStarts[page] = nextStart;
      textBook.avgPageBytes = Math.max(consumed, 1);
      this.textCurrentPage = page;
      this.textReady = true;
      this.previewLoading = false;
      if (textBook.totalBytes && nextStart >= textBook.totalBytes) {
        textBook.exactCount = page;
        this.textPageCount = page;
      } else if (textBook.totalBytes) {
        this.textPageCount = Math.max(page + 1, Math.ceil(textBook.totalBytes / textBook.avgPageBytes));
      } else {
        this.textPageCount = page + 1;
      }
      this._lastH = viewport.clientHeight;
      this._lastW = viewport.clientWidth;
      if (this.viewMode === 'scroll') this.updateTextSpacer();
    },

    async openText(url) {
      const token = textBook.token;
      textBook.url = url;
      textBook.totalBytes = 0;
      textBook.pageStarts = [0];
      textBook.avgPageBytes = 16 * 1024;
      textBook.charBudget = 0;
      textBook.bytes = null;
      textBook.exactCount = 0;
      this.textCurrentPage = 1;
      this.textPageCount = 1;
      this.textReady = false;
      this._scrollByte = -1;
      try {
        await this.showTextAt(1, token);
      } catch (err) {
        if (token !== textBook.token || err.name === 'AbortError') return;
        this.previewError = err.message || '加载失败';
      } finally {
        if (token === textBook.token) this.previewLoading = false;
      }
    },

    async refitText() {
      if (!this.textReady || !textBook.url) return;
      textBook.charBudget = 0;
      if (this.viewMode === 'scroll') {
        this._scrollByte = -1;
        this.updateTextSpacer();
        await this.renderTextScroll();
        return;
      }
      const byte = textBook.pageStarts[this.textCurrentPage - 1] || 0;
      textBook.pageStarts = [];
      textBook.pageStarts[this.textCurrentPage - 1] = byte;
      textBook.exactCount = 0;
      await this.showTextAt(this.textCurrentPage);
    },

    async enterTextScroll() {
      this.updateTextSpacer();
      await this.$nextTick();
      const viewport = this.$refs.viewport;
      const start = textBook.pageStarts[this.textCurrentPage - 1] || 0;
      if (viewport && textBook.totalBytes) {
        const maxScroll = Math.max(0, viewport.scrollHeight - viewport.clientHeight);
        viewport.scrollTop = (start / textBook.totalBytes) * maxScroll;
      }
      this._scrollByte = -1;
      await this.renderTextScroll();
    },

    onTextScroll() {
      if (this.previewKind !== 'text' || this.viewMode !== 'scroll') return;
      const viewport = this.$refs.viewport;
      const pre = this.$refs.textContent;
      if (viewport && pre) pre.style.top = `${viewport.scrollTop}px`;
      if (this._scrollTimer) clearTimeout(this._scrollTimer);
      this._scrollTimer = setTimeout(() => { void this.renderTextScroll(); }, 80);
    },

    async renderTextScroll() {
      if (this.viewMode !== 'scroll' || this.previewKind !== 'text') return;
      const viewport = this.$refs.viewport;
      const pre = this.$refs.textContent;
      if (!viewport || !pre || !textBook.totalBytes) return;
      const maxScroll = Math.max(1, viewport.scrollHeight - viewport.clientHeight);
      const ratio = Math.min(1, Math.max(0, viewport.scrollTop / maxScroll));
      const byte = Math.floor(ratio * Math.max(0, textBook.totalBytes - 1));
      const quantum = Math.max(textBook.avgPageBytes, 4096);
      const aligned = Math.floor(byte / quantum) * quantum;
      if (aligned === this._scrollByte && pre.textContent) {
        pre.style.top = `${viewport.scrollTop}px`;
        return;
      }
      this._scrollByte = aligned;
      const start = aligned === 0 ? 0 : Math.max(0, aligned - 128);
      const windowText = await this.readTextWindow(start, textBook.token, quantum * 3);
      if (!windowText || this.viewMode !== 'scroll' || this.previewKind !== 'text') return;
      let text = windowText.text;
      if (start > 0) {
        const nl = text.indexOf('\n');
        if (nl !== -1 && nl < 500) text = text.slice(nl + 1);
      }
      const budget = (textBook.charBudget || 1800) * 4;
      pre.textContent = text.slice(0, budget);
      pre.style.top = `${viewport.scrollTop}px`;
      this.textReady = true;
      this.previewLoading = false;
    },

    async loadPreview(url, kindHint) {
      if (textBook.abort) textBook.abort.abort();
      textBook.token += 1;
      const nextKind = this.kindFromUrl(url, kindHint);
      this.pdfRenderToken += 1;
      this.epubRenderToken += 1;
      this.previewKind = nextKind;
      this.previewUrl = url;
      this.previewHtml = '';
      this.previewText = '';
      this.previewError = '';
      this.pdfPageCount = 0;
      this.pdfCurrentPage = 1;
      store.pdfDoc = null;
      store.pdfUrl = '';
      this.textPageCount = 1;
      this.textCurrentPage = 1;
      this.textReady = false;
      this.viewMode = 'page';
      this.resetZoom();
      this.clearPdfPreview();
      this.clearEpubPreview();

      const needsMarkdown = nextKind === 'markdown';
      const needsText = nextKind === 'text';
      const needsPdf = nextKind === 'pdf';
      const needsEpub = nextKind === 'epub';
      this.previewLoading = needsMarkdown || needsText || needsPdf || needsEpub;
      if (!this.previewLoading) return;

      try {
        if (needsPdf) {
          await this.$nextTick();
          await this.renderPdfPreview(url);
          return;
        }
        if (needsEpub) {
          await this.$nextTick();
          await this.renderEpubPreview(url);
          return;
        }
        if (needsText) {
          await this.$nextTick();
          await this.openText(url);
          return;
        }
        const res = await fetch(url);
        if (!res.ok) throw new Error('加载失败');
        const text = await res.text();
        if (needsMarkdown) {
          if (window.marked?.parse) {
            this.previewHtml = window.marked.parse(text);
            await this.$nextTick();
            this.measureTextPages();
          } else {
            this.previewError = 'Markdown 预览组件未加载';
          }
        }
      } catch (e) {
        this.previewError = e.message || '加载失败';
      } finally {
        this.previewLoading = false;
      }
    },

    async init() {
      if (!this.previewUrl) {
        this.previewError = '缺少文件地址';
        return;
      }
      await this.loadPreview(this.previewUrl, fileInfo.kind);
      await this.$nextTick();
      this.scheduleLayoutRefresh();
      window.addEventListener('resize', () => this.scheduleLayoutRefresh());
    },
  };
}
