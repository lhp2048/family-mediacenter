(function () {
  'use strict';

  let pollTimer = null;
  let qrSessionId = null;

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
    const node = el('bilibili-qr-message');
    if (!node) return;
    node.textContent = text || '';
    node.classList.toggle('form-error', !!isError);
    node.classList.toggle('form-message-ok', !isError && !!text);
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    qrSessionId = null;
  }

  function renderQrUrl(url) {
    const canvas = el('bilibili-qr-canvas');
    const fallback = el('bilibili-qr-fallback');
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

  async function refreshBilibiliLoginStatus() {
    try {
      const res = await fetch('/api/v1/bilibili/login/status', { headers: apiHeaders() });
      if (!res.ok) return null;
      const data = await res.json();
      document.querySelectorAll('[data-bilibili-login-status]').forEach((node) => {
        if (data.logged_in) {
          const when = data.updated_at
            ? new Date(data.updated_at).toLocaleString()
            : '已配置';
          node.textContent = `B 站已登录 · ${when}`;
          node.classList.add('health-chip-ok');
          node.classList.remove('health-chip-fail');
        } else {
          node.textContent = 'B 站未登录';
          node.classList.add('health-chip-fail');
          node.classList.remove('health-chip-ok');
        }
      });
      if (window.Alpine && typeof window.dispatchEvent === 'function') {
        window.dispatchEvent(new CustomEvent('bilibili-login-updated', { detail: data }));
      }
      return data;
    } catch (_) {
      return null;
    }
  }

  async function pollOnce() {
    if (!qrSessionId) return;
    try {
      const res = await fetch(
        `/api/v1/bilibili/qr/poll?session_id=${encodeURIComponent(qrSessionId)}`,
        { headers: apiHeaders() }
      );
      const data = await res.json();
      if (!res.ok) {
        setQrMessage(data.detail || '轮询失败', true);
        stopPolling();
        return;
      }
      setQrMessage(data.message || '', data.status === 'error');
      if (data.status === 'success') {
        stopPolling();
        await refreshBilibiliLoginStatus();
        const cookiesInput = document.getElementById('set-ytdlp-cookies');
        if (cookiesInput) {
          cookiesInput.value = data.cookies_file || 'data/bilibili_cookies.txt';
          cookiesInput.dispatchEvent(new Event('input', { bubbles: true }));
        }
        setTimeout(() => closeBilibiliQrModal(), 1200);
        return;
      }
      if (data.status === 'expired' || data.status === 'error') {
        stopPolling();
      }
    } catch (e) {
      setQrMessage(e.message || String(e), true);
      stopPolling();
    }
  }

  async function startBilibiliQrFlow() {
    stopPolling();
    setQrMessage('正在获取二维码…', false);
    const canvas = el('bilibili-qr-canvas');
    const fallback = el('bilibili-qr-fallback');
    if (canvas) {
      canvas.hidden = false;
      const ctx = canvas.getContext('2d');
      if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
    if (fallback) fallback.hidden = true;

    try {
      const res = await fetch('/api/v1/bilibili/qr/start', {
        method: 'POST',
        headers: apiHeaders(true),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || '无法获取二维码');
      qrSessionId = data.session_id;
      renderQrUrl(data.url);
      setQrMessage('请使用 B 站 App 扫描二维码', false);
      pollTimer = setInterval(pollOnce, 2000);
      pollOnce();
    } catch (e) {
      setQrMessage(e.message || String(e), true);
    }
  }

  window.openBilibiliQrModal = function openBilibiliQrModal() {
    const modal = el('bilibili-qr-modal');
    if (!modal) return;
    modal.hidden = false;
    startBilibiliQrFlow();
  };

  window.closeBilibiliQrModal = function closeBilibiliQrModal() {
    stopPolling();
    const modal = el('bilibili-qr-modal');
    if (modal) modal.hidden = true;
    setQrMessage('', false);
  };

  window.refreshBilibiliLoginStatus = refreshBilibiliLoginStatus;
  window.restartBilibiliQrFlow = startBilibiliQrFlow;

  document.addEventListener('DOMContentLoaded', () => {
    refreshBilibiliLoginStatus();
    const modal = el('bilibili-qr-modal');
    if (modal) {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) closeBilibiliQrModal();
      });
    }
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        const modal = el('bilibili-qr-modal');
        if (modal && !modal.hidden) closeBilibiliQrModal();
      }
    });
  });
})();
