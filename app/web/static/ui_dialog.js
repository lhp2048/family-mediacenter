/**
 * In-page dialogs replacing window.confirm / alert / prompt.
 * Usage:
 *   const ok = await uiConfirm('确定删除？');
 *   await uiAlert('已复制');
 *   const name = await uiPrompt('播放列表名称', { defaultValue: '' });
 */
(function (global) {
  const ROOT_ID = 'ui-dialog-root';

  function ensureRoot() {
    let root = document.getElementById(ROOT_ID);
    if (root) return root;
    root = document.createElement('div');
    root.id = ROOT_ID;
    root.className = 'ui-dialog-root';
    root.hidden = true;
    root.innerHTML = [
      '<div class="modal-backdrop ui-dialog-backdrop" data-ui-dialog-backdrop>',
      '  <div class="modal-card ui-dialog-card" role="dialog" aria-modal="true" aria-labelledby="ui-dialog-title" data-ui-dialog-card>',
      '    <h3 id="ui-dialog-title" class="ui-dialog-title" data-ui-dialog-title></h3>',
      '    <p class="ui-dialog-message" data-ui-dialog-message></p>',
      '    <div class="field ui-dialog-input-wrap" data-ui-dialog-input-wrap hidden>',
      '      <input type="text" class="ui-dialog-input" data-ui-dialog-input autocomplete="off">',
      '    </div>',
      '    <div class="modal-actions ui-dialog-actions">',
      '      <button type="button" class="secondary" data-ui-dialog-cancel>取消</button>',
      '      <button type="button" class="btn-primary" data-ui-dialog-ok>确定</button>',
      '    </div>',
      '  </div>',
      '</div>',
    ].join('');
    document.body.appendChild(root);
    return root;
  }

  let busy = false;

  function openDialog(opts) {
    const {
      title = '提示',
      message = '',
      mode = 'confirm', // confirm | alert | prompt
      okText = '确定',
      cancelText = '取消',
      danger = false,
      defaultValue = '',
      placeholder = '',
    } = opts || {};

    if (busy) {
      return Promise.resolve(mode === 'prompt' ? null : false);
    }
    busy = true;

    const root = ensureRoot();
    const titleEl = root.querySelector('[data-ui-dialog-title]');
    const msgEl = root.querySelector('[data-ui-dialog-message]');
    const inputWrap = root.querySelector('[data-ui-dialog-input-wrap]');
    const input = root.querySelector('[data-ui-dialog-input]');
    const okBtn = root.querySelector('[data-ui-dialog-ok]');
    const cancelBtn = root.querySelector('[data-ui-dialog-cancel]');
    const backdrop = root.querySelector('[data-ui-dialog-backdrop]');
    const card = root.querySelector('[data-ui-dialog-card]');

    titleEl.textContent = title;
    msgEl.textContent = message;
    msgEl.hidden = !message;
    okBtn.textContent = okText;
    cancelBtn.textContent = cancelText;
    okBtn.className = danger ? 'danger' : 'btn-primary';
    cancelBtn.className = 'secondary';

    const showInput = mode === 'prompt';
    inputWrap.hidden = !showInput;
    cancelBtn.hidden = mode === 'alert';
    if (showInput) {
      input.value = defaultValue || '';
      input.placeholder = placeholder || '';
    }

    root.hidden = false;

    return new Promise((resolve) => {
      const cleanup = () => {
        root.hidden = true;
        busy = false;
        okBtn.removeEventListener('click', onOk);
        cancelBtn.removeEventListener('click', onCancel);
        backdrop.removeEventListener('click', onBackdrop);
        document.removeEventListener('keydown', onKey);
      };

      const onOk = () => {
        const value = showInput ? input.value : true;
        cleanup();
        resolve(showInput ? value : true);
      };
      const onCancel = () => {
        cleanup();
        resolve(showInput ? null : false);
      };
      const onBackdrop = (e) => {
        if (e.target === backdrop) onCancel();
      };
      const onKey = (e) => {
        if (e.key === 'Escape') {
          e.preventDefault();
          onCancel();
        } else if (e.key === 'Enter' && showInput && document.activeElement === input) {
          e.preventDefault();
          onOk();
        }
      };

      okBtn.addEventListener('click', onOk);
      cancelBtn.addEventListener('click', onCancel);
      backdrop.addEventListener('click', onBackdrop);
      document.addEventListener('keydown', onKey);

      requestAnimationFrame(() => {
        if (showInput) input.focus();
        else okBtn.focus();
      });

      // stop click bubbling from card
      card.addEventListener('click', (e) => e.stopPropagation(), { once: true });
    });
  }

  function uiConfirm(message, options) {
    const opts = typeof options === 'string' ? { title: options } : (options || {});
    return openDialog({
      title: opts.title || '请确认',
      message: message || '',
      mode: 'confirm',
      okText: opts.okText || '确定',
      cancelText: opts.cancelText || '取消',
      danger: !!opts.danger,
    });
  }

  function uiAlert(message, options) {
    const opts = typeof options === 'string' ? { title: options } : (options || {});
    return openDialog({
      title: opts.title || '提示',
      message: message || '',
      mode: 'alert',
      okText: opts.okText || '知道了',
    }).then(() => undefined);
  }

  function uiPrompt(message, options) {
    const opts = typeof options === 'string' ? { defaultValue: options } : (options || {});
    return openDialog({
      title: opts.title || '请输入',
      message: message || '',
      mode: 'prompt',
      okText: opts.okText || '确定',
      cancelText: opts.cancelText || '取消',
      defaultValue: opts.defaultValue || '',
      placeholder: opts.placeholder || '',
    });
  }

  function copyViaTextarea(text) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.top = '0';
    ta.style.left = '0';
    ta.style.width = '1px';
    ta.style.height = '1px';
    ta.style.padding = '0';
    ta.style.border = 'none';
    ta.style.outline = 'none';
    ta.style.boxShadow = 'none';
    ta.style.background = 'transparent';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    ta.setSelectionRange(0, ta.value.length);
    let ok = false;
    try {
      ok = document.execCommand('copy');
    } catch (_) {
      ok = false;
    }
    document.body.removeChild(ta);
    return ok;
  }

  /**
   * Copy text to clipboard. Works on HTTP LAN where navigator.clipboard may fail.
   * @returns {Promise<boolean>}
   */
  async function uiCopyText(text, options) {
    const opts = options || {};
    const value = text == null ? '' : String(text);
    if (!value) return false;

    try {
      if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
        await navigator.clipboard.writeText(value);
        return true;
      }
    } catch (_) {
      /* fall through — common on http://LAN IP */
    }

    if (copyViaTextarea(value)) return true;

    if (opts.fallbackPrompt !== false) {
      await uiPrompt(opts.promptMessage || '当前环境无法自动复制，请手动全选复制：', {
        title: opts.title || '手动复制',
        defaultValue: value,
      });
      return false;
    }
    return false;
  }

  global.uiConfirm = uiConfirm;
  global.uiAlert = uiAlert;
  global.uiPrompt = uiPrompt;
  global.uiCopyText = uiCopyText;
})(window);
