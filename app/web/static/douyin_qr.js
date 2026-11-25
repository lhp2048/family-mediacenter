(function () {
  'use strict';

  let pollTimer = null;
  let qrSessionId = null;
  let flowGen = 0;

  function apiHeaders(json) {
    const h = json ? { 'Content-Type': 'application/json' } : {};
    const apiKey = localStorage.getItem('api_key');
    if (apiKey) h['X-API-Key'] = apiKey;
    return h;
  }

  function el(id) {
    return document.getElementById(id);
  }

  function setQrMessage(text, isError) {
    const node = el('douyin-qr-message');
    if (!node) return;
    node.textContent = text || '';
    node.classList.toggle('form-error', !!isError);
    node.classList.toggle('form-message-ok', !isError && !!text);
  }

  function stopPolling(cancel) {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    const sessionId = qrSessionId;
    qrSessionId = null;
    if (cancel && sessionId) {
      fetch(`/api/v1/douyin/qr/cancel?session_id=${encodeURIComponent(sessionId)}`, {
        method: 'POST',
        headers: apiHeaders(true),
      }).catch(() => {});
    }
  }

  function renderQrUrl(url) {
    const canvas = el('douyin-qr-canvas');
    const fallback = el('douyin-qr-fallback');
    if (!canvas || !url) return;
    if (typeof QRCode !== 'undefined') {
      QRCode.toCanvas(canvas, url, { width: 240, margin: 1 }, (err) => {
        if (err && fallback) {
          fallback.src =
            'https://api.qrserver.com/v1/create-qr-code/?size=240x240&data=' +
            encodeURIComponent(url);
          fallback.hidden = false;
          canvas.hidden = true;
        }
      });
      canvas.hidden = false;
      if (fallback) fallback.hidden = true;
      return;
    }
    if (fallback) {
      fallback.src =
        'https://api.qrserver.com/v1/create-qr-code/?size=240x240&data=' +
        encodeURIComponent(url);
      fallback.hidden = false;
      canvas.hidden = true;
    }
  }

  function renderQrPayload(data) {
    const canvas = el('douyin-qr-canvas');
    const fallback = el('douyin-qr-fallback');
    const image = data.qrcode_base64 || '';
    if (image && fallback) {
      fallback.src = image.indexOf('data:') === 0 ? image : 'data:image/png;base64,' + image;
      fallback.hidden = false;
      if (canvas) canvas.hidden = true;
      return;
    }
    if (data.url) renderQrUrl(data.url);
  }

  async function refreshDouyinLoginStatus() {
    try {
      const res = await fetch('/api/v1/douyin/login/status', { headers: apiHeaders() });
      if (!res.ok) return null;
      const data = await res.json();
      document.querySelectorAll('[data-douyin-login-status]').forEach((node) => {
        if (data.logged_in) {
          const when = data.updated_at ? new Date(data.updated_at).toLocaleString() : '已配置';
          node.textContent = `抖音已登录 · ${when}`;
          node.classList.add('health-chip-ok');
          node.classList.remove('health-chip-fail');
        } else {
          node.textContent = '抖音未登录';
          node.classList.add('health-chip-fail');
          node.classList.remove('health-chip-ok');
        }
      });
      window.dispatchEvent(new CustomEvent('douyin-login-updated', { detail: data }));
      return data;
    } catch (_) {
      return null;
    }
  }

  async function pollOnce() {
    const sessionId = qrSessionId;
    const gen = flowGen;
    if (!sessionId) return;
    try {
      const res = await fetch(
        `/api/v1/douyin/qr/poll?session_id=${encodeURIComponent(sessionId)}`,
        { headers: apiHeaders() }
      );
      const data = await res.json();
      if (gen !== flowGen || sessionId !== qrSessionId) return;
      if (!res.ok) {
        setQrMessage(data.detail || '轮询失败', true);
        stopPolling(false);
        return;
      }
      setQrMessage(data.message || '', data.status === 'error');
      if (data.status === 'success') {
        stopPolling(false);
        await refreshDouyinLoginStatus();
        setTimeout(() => closeDouyinQrModal(), 1200);
        return;
      }
      if (data.status === 'expired' || data.status === 'error') {
        stopPolling(false);
      }
    } catch (e) {
      if (gen !== flowGen || sessionId !== qrSessionId) return;
      setQrMessage(e.message || String(e), true);
      stopPolling(false);
    }
  }

  async function startDouyinQrFlow() {
    flowGen += 1;
    stopPolling(false);
    setQrMessage('正在获取二维码…', false);
    const canvas = el('douyin-qr-canvas');
    const fallback = el('douyin-qr-fallback');
    if (canvas) {
      canvas.hidden = false;
      const ctx = canvas.getContext('2d');
      if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
    if (fallback) fallback.hidden = true;

    try {
      const res = await fetch('/api/v1/douyin/qr/start', {
        method: 'POST',
        headers: apiHeaders(true),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || '无法获取二维码');
      qrSessionId = data.session_id;
      renderQrPayload(data);
      setQrMessage('请使用抖音 App 扫描二维码', false);
      pollTimer = setInterval(pollOnce, 2000);
      pollOnce();
    } catch (e) {
      setQrMessage(e.message || String(e), true);
    }
  }

  window.openDouyinQrModal = function openDouyinQrModal() {
    const modal = el('douyin-qr-modal');
    if (!modal) return;
    modal.hidden = false;
    startDouyinQrFlow();
  };

  window.closeDouyinQrModal = function closeDouyinQrModal() {
    flowGen += 1;
    stopPolling(true);
    const modal = el('douyin-qr-modal');
    if (modal) modal.hidden = true;
    setQrMessage('', false);
  };

  window.refreshDouyinLoginStatus = refreshDouyinLoginStatus;
  window.restartDouyinQrFlow = startDouyinQrFlow;

  document.addEventListener('DOMContentLoaded', () => {
    refreshDouyinLoginStatus();
    const modal = el('douyin-qr-modal');
    if (modal) {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) closeDouyinQrModal();
      });
    }
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        const modal = el('douyin-qr-modal');
        if (modal && !modal.hidden) closeDouyinQrModal();
      }
    });
  });
})();
