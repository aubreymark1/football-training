(() => {
  const $ = (selector, root) => (root || document).querySelector(selector);
  const $$ = (selector, root) => Array.from((root || document).querySelectorAll(selector));
  const canDialog = typeof HTMLDialogElement === 'function' && typeof HTMLDialogElement.prototype.showModal === 'function';

  /* ---- 1. 训练记录表单：运动类型快选、用力程度、截图预览、防重复提交 ---- */
  const EFFORT_WORDS = ['', '很轻松', '很轻松', '轻松', '轻松', '适中', '适中', '吃力', '吃力', '非常吃力', '极限'];
  const UPLOAD_LIMIT = 7.5 * 1024 * 1024;

  function megabytes(bytes) {
    return bytes < 1024 * 1024 ? Math.max(1, Math.round(bytes / 1024)) + ' KB' : (bytes / 1024 / 1024).toFixed(1) + ' MB';
  }

  async function shrink(file) {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, 2400 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.85));
    if (!blob || blob.size > UPLOAD_LIMIT) throw new Error('still too large');
    return new File([blob], file.name.replace(/\.\w+$/, '') + '.jpg', { type: 'image/jpeg' });
  }

  $$('form[data-record-form]').forEach((form) => {
    const sport = form.elements.sport;
    const chips = $$('.chip', form);
    const syncChips = () => chips.forEach((chip) => {
      const on = chip.dataset.sport === sport.value.trim();
      chip.classList.toggle('is-on', on);
      chip.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    chips.forEach((chip) => chip.addEventListener('click', () => { sport.value = chip.dataset.sport; syncChips(); }));
    sport.addEventListener('input', syncChips);
    syncChips();

    const effortOut = $('.effort output', form);
    const syncEffort = () => {
      const picked = $('input[name=effort]:checked', form);
      if (effortOut) effortOut.textContent = picked ? picked.value + ' · ' + EFFORT_WORDS[Number(picked.value)] : '';
    };
    form.addEventListener('change', (event) => { if (event.target.name === 'effort') syncEffort(); });
    syncEffort();

    const box = $('.upload', form);
    const input = form.elements.image;
    const thumb = $('.upload-thumb', form);
    const name = $('.upload-text strong', form);
    const meta = $('.upload-text small', form);
    const error = $('.form-error', form);
    const idle = { name: name.textContent, meta: meta.textContent };
    let preview = '';
    let selectionVersion = 0;
    let processing = false;
    const submit = $('button.primary', form);
    const submitLabel = submit.textContent;

    function processingImage(on) {
      processing = on;
      submit.disabled = on;
      submit.textContent = on ? '处理图片…' : submitLabel;
    }

    form.addEventListener('submit', (event) => {
      if (!processing) return;
      event.preventDefault();
      error.textContent = '图片正在处理，请稍等';
      error.hidden = false;
    });

    function show(file, note) {
      if (preview) URL.revokeObjectURL(preview);
      preview = file ? URL.createObjectURL(file) : '';
      box.classList.toggle('has-file', Boolean(file));
      thumb.style.backgroundImage = file ? 'url("' + preview + '")' : '';
      name.textContent = file ? file.name : idle.name;
      meta.textContent = file ? megabytes(file.size) + (note || '') + ' · 点击更换' : idle.meta;
    }

    form.addEventListener('reset', () => {
      selectionVersion++;
      processingImage(false);
      error.hidden = true;
      show(null);
      // The reset event fires before the browser restores the field values.
      Promise.resolve().then(() => {
        syncChips();
        syncEffort();
      });
    });

    input.addEventListener('change', async () => {
      const version = ++selectionVersion;
      processingImage(false);
      error.hidden = true;
      let file = input.files[0];
      if (!file) { show(null); return; }
      let note = '';
      if (file.size > UPLOAD_LIMIT) {
        processingImage(true);
        show(file, ' · 缩小中');
        try {
          const transfer = new DataTransfer();
          file = await shrink(file);
          if (version !== selectionVersion) return;
          transfer.items.add(file);
          input.files = transfer.files;
          note = '（已自动压缩）';
        } catch (e) {
          if (version !== selectionVersion) return;
          input.value = '';
          show(null);
          error.textContent = '图片超过 8MB 无法上传，请裁剪后再试';
          error.hidden = false;
          return;
        } finally {
          if (version === selectionVersion) processingImage(false);
        }
      }
      error.hidden = true;
      show(file, note);
    });
    if (input.files && input.files[0]) show(input.files[0]);
  });

  /* ---- 2. 提交防重复锁 ---- */
  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (!form.matches || !form.matches('form[data-lock]') || event.defaultPrevented) return;
    if (form.matches('form[data-remote]')) return;
    if (form.dataset.sent) { event.preventDefault(); return; }
    form.dataset.sent = '1';
    const button = event.submitter || $('button:not([type=button])', form);
    setTimeout(() => {
      if (!button) return;
      button.dataset.label = button.textContent;
      button.textContent = form.dataset.lock || '提交中';
      button.classList.add('is-busy');
      button.disabled = true;
    });
  });

  window.addEventListener('pageshow', (event) => {
    if (!event.persisted) return;
    $$('form[data-sent]').forEach((form) => {
      delete form.dataset.sent;
      $$('.is-busy', form).forEach((button) => {
        button.disabled = false;
        button.classList.remove('is-busy');
        button.textContent = button.dataset.label || button.textContent;
      });
    });
  });

  /* ---- 3. 深浅主题切换、首页滑出打卡抽屉与附加模块筛选 ---- */
  document.addEventListener('click', (event) => {
    if (!event.target || !event.target.closest) return;

    const themeBtn = event.target.closest('[data-theme-toggle]');
    if (themeBtn) {
      const root = document.documentElement;
      const next = root.dataset.theme === 'light' ? 'dark' : 'light';
      root.dataset.theme = next;
      const meta = document.getElementById('meta-theme-color');
      if (meta) meta.content = next === 'light' ? '#fafafa' : '#141415';
      try { localStorage.setItem('lu_theme', next); } catch (_) {}
      return;
    }

    const filterBtn = event.target.closest('[data-module-filter]');
    if (filterBtn) {
      const code = filterBtn.dataset.moduleFilter;
      $$('[data-module-filter]').forEach((button) => {
        const active = button === filterBtn;
        button.classList.toggle('is-active', active);
        button.setAttribute('aria-pressed', String(active));
      });
      $$('.module[data-module]').forEach((sec) => {
        sec.hidden = code !== 'all' && sec.dataset.module !== code;
      });
      return;
    }

    const drawerTrigger = event.target.closest('[data-open-submit]');
    if (drawerTrigger && canDialog) {
      const drawer = document.getElementById('submit-drawer');
      const form = drawer && $('form[data-record-form]', drawer);
      if (drawer && form) {
        event.preventDefault();
        if (form.action !== drawerTrigger.href) {
          form.reset();
          form.action = drawerTrigger.href;
        }
        const titleEl = $('#drawer-title', drawer);
        const subEl = $('#drawer-sub', drawer);
        if (titleEl) titleEl.textContent = drawerTrigger.dataset.taskTitle || '提交训练记录';
        if (subEl) subEl.textContent = drawerTrigger.dataset.taskSub || '';
        drawer.showModal();
        return;
      }
    }

    const drawerClose = event.target.closest('[data-close-drawer]');
    if (drawerClose) {
      const d = drawerClose.closest('dialog');
      if (d) d.close();
      return;
    }

    if (event.target.matches && event.target.matches('dialog.drawer')) {
      event.target.close();
      return;
    }

    const trigger = event.target.closest('[data-zoom]');
    if (trigger) {
      event.preventDefault();
      zoom(trigger.dataset.zoom || trigger.href, trigger.getAttribute('aria-label'));
    }
  });

  /* ---- 4. 二次确认弹层 ---- */
  let sheet;
  function ask(message, action) {
    if (!canDialog) return Promise.resolve(window.confirm(message));
    if (!sheet) {
      sheet = document.createElement('dialog');
      sheet.className = 'sheet';
      sheet.innerHTML = '<p></p><div class="sheet-actions"><button type="button" class="outline" data-answer="no">取消</button><button type="button" class="smallbtn" data-answer="yes"></button></div>';
      document.body.append(sheet);
      sheet.addEventListener('click', (event) => {
        const answer = event.target.dataset && event.target.dataset.answer;
        if (answer) sheet.close(answer);
        else if (event.target === sheet) sheet.close('no');
      });
    }
    $('p', sheet).textContent = message;
    $('[data-answer=yes]', sheet).textContent = action || '确认';
    sheet.returnValue = 'no';
    sheet.showModal();
    return new Promise((resolve) => sheet.addEventListener('close', () => resolve(sheet.returnValue === 'yes'), { once: true }));
  }
  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (!form.matches || !form.matches('form[data-confirm]')) return;
    if (form.dataset.confirmed) { delete form.dataset.confirmed; return; }
    event.preventDefault();
    const submitter = event.submitter;
    ask(form.dataset.confirm, form.dataset.confirmAction).then((yes) => {
      if (!yes) return;
      form.dataset.confirmed = '1';
      if (form.requestSubmit) form.requestSubmit(submitter || undefined); else form.submit();
    });
  }, true);

  /* ---- 5. 截图灯箱 ---- */
  let lightbox;
  function zoom(url, label) {
    if (!canDialog) { window.open(url, '_blank', 'noopener'); return; }
    if (!lightbox) {
      lightbox = document.createElement('dialog');
      lightbox.className = 'lightbox';
      lightbox.innerHTML = '<button type="button" class="lightbox-close" aria-label="关闭">×</button><img alt="">';
      document.body.append(lightbox);
      lightbox.addEventListener('click', (event) => { if (event.target.tagName !== 'IMG') lightbox.close(); });
      lightbox.addEventListener('close', () => $('img', lightbox).removeAttribute('src'));
    }
    const img = $('img', lightbox);
    lightbox.classList.add('is-loading');
    img.onload = img.onerror = () => lightbox.classList.remove('is-loading');
    img.alt = label || '训练截图';
    img.src = url;
    lightbox.showModal();
  }

  /* ---- 6. 趋势图提示与任务表单类型联动 ---- */
  $$('.plot').forEach((plot) => {
    let tip;
    const hide = () => { if (tip) { tip.remove(); tip = null; } };
    const showTip = (hit) => {
      hide();
      tip = document.createElement('div');
      tip.className = 'tip';
      tip.textContent = hit.dataset.tip;
      plot.append(tip);
      const bar = $('.bar', hit).getBoundingClientRect();
      const frame = plot.getBoundingClientRect();
      const half = tip.offsetWidth / 2;
      const centre = bar.left + bar.width / 2 - frame.left;
      tip.style.left = Math.max(half, Math.min(frame.width - half, centre)) + 'px';
      tip.style.top = Math.max(tip.offsetHeight, bar.top - frame.top - 8) + 'px';
    };
    $$('.bar-hit', plot).forEach((hit) => {
      hit.addEventListener('pointerenter', () => showTip(hit));
      hit.addEventListener('focus', () => showTip(hit));
      hit.addEventListener('pointerleave', hide);
      hit.addEventListener('blur', hide);
    });
  });

  $$('#tasks form').forEach((form) => {
    const kind = form.querySelector && form.querySelector('select[name="kind"]');
    const mod = form.querySelector && form.querySelector('select[name="module"]');
    const cap = form.querySelector && form.querySelector('input[name="cap"]');
    if (!kind || !mod) return;
    const bonusRow = mod.closest('.cols');
    const capLabel = cap && cap.closest('label');
    const sync = () => {
      const isBonus = kind.value === 'bonus';
      if (bonusRow) bonusRow.classList.toggle('is-dimmed', !isBonus);
      if (capLabel) capLabel.classList.toggle('is-dimmed', !isBonus);
    };
    kind.addEventListener('change', sync);
    sync();
  });
})();
