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
      if (this.viewMode === 'page' && (this.previewKind === 'markdown' || this.previewKind === 'text')) {
        const offset = (this.textCurrentPage - 1) * this.textPageHeight;
        parts.push(`translateY(-${offset}px)`);
      } else if (this.panX || this.panY) {
        parts.push(`translate(${this.panX}px, ${this.panY}px)`);
      }
      if (this.zoom !== 1) {
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
      return `${this.textCurrentPage} / ${this.textPageCount}`;
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
    },

    zoomOut() {
      this.zoom = Math.max(0.5, Math.round((this.zoom - 0.25) * 100) / 100);
      if (this.zoom <= 1) this.resetPan();
    },

    resetZoom() {
      this.zoom = 1;
      this.resetPan();
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
      } else if (this.previewKind === 'markdown' || this.previewKind === 'text') {
        await this.$nextTick();
        this.measureTextPages();
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
      window.requestAnimationFrame(() => {
        if (this.previewKind === 'markdown' || this.previewKind === 'text') {
          this.measureTextPages();
        } else if (this.previewKind === 'pdf' && store.pdfDoc) {
          void this.applyPdfView();
        }
      });
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
      if (this.previewKind === 'markdown' || this.previewKind === 'text') {
        if (this.textCurrentPage <= 1) return;
        this.textCurrentPage -= 1;
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
      if (this.previewKind === 'markdown' || this.previewKind === 'text') {
        if (this.textCurrentPage >= this.textPageCount) return;
        this.textCurrentPage += 1;
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

    async loadPreview(url, kindHint) {
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
        } else {
          this.previewText = text;
          await this.$nextTick();
          this.measureTextPages();
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
