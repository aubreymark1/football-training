(() => {
  const $ = (selector, root) => (root || document).querySelector(selector);
  const $$ = (selector, root) => Array.from((root || document).querySelectorAll(selector));
  const canDialog = typeof HTMLDialogElement === 'function';

  /* ---- 训练记录表单：运动类型快选、用力程度、截图预览、防重复提交 ---- */
  const EFFORT_WORDS = ['', '很轻松', '很轻松', '轻松', '轻松', '有点吃力', '有点吃力', '吃力', '吃力', '非常吃力', '非常吃力'];
  const UPLOAD_LIMIT = 7.5 * 1024 * 1024; // 服务器整个请求上限 8MB，留一点给其它字段

  function megabytes(bytes) {
    return bytes < 1024 * 1024 ? Math.max(1, Math.round(bytes / 1024)) + ' KB' : (bytes / 1024 / 1024).toFixed(1) + ' MB';
  }

  // 只有超过上限的图片才在浏览器里缩小；其余原样上传，保留原始文件信息供审核核对。
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
      submit.textContent = on ? '图片处理中…' : submitLabel;
    }

    form.addEventListener('submit', (event) => {
      if (!processing) return;
      event.preventDefault();
      error.textContent = '图片正在处理，请稍等。';
      error.hidden = false;
    });

    function show(file, note) {
      if (preview) URL.revokeObjectURL(preview);
      preview = file ? URL.createObjectURL(file) : '';
      box.classList.toggle('has-file', Boolean(file));
      thumb.style.backgroundImage = file ? 'url("' + preview + '")' : '';
      name.textContent = file ? file.name : idle.name;
      meta.textContent = file ? megabytes(file.size) + (note || '') + '，点这里可以重新选' : idle.meta;
    }

    input.addEventListener('change', async () => {
      const version = ++selectionVersion;
      processingImage(false);
      error.hidden = true;
      let file = input.files[0];
      if (!file) { show(null); return; }
      let note = '';
      if (file.size > UPLOAD_LIMIT) {
        processingImage(true);
        show(file, '，正在缩小');
        try {
          const transfer = new DataTransfer();
          file = await shrink(file);
          if (version !== selectionVersion) return;
          transfer.items.add(file);
          input.files = transfer.files;
          note = '（原图太大，已缩小）';
        } catch (e) {
          if (version !== selectionVersion) return;
          input.value = '';
          show(null);
          error.textContent = '这张图片超过 8MB，没法上传。换一张，或先裁剪一下再选。';
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

  // 提交后锁住按钮。放到下一拍再禁用，避免把按钮自己的值从表单数据里丢掉。
  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (!form.matches('form[data-lock]') || event.defaultPrevented) return;
    if (form.matches('form[data-remote]')) return; // 点赞、评论走 interactions.js，不锁按钮
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

  /* ---- 二次确认 ---- */
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
    if (!form.matches('form[data-confirm]')) return;
    if (form.dataset.confirmed) { delete form.dataset.confirmed; return; }
    event.preventDefault();
    const submitter = event.submitter;
    ask(form.dataset.confirm, form.dataset.confirmAction).then((yes) => {
      if (!yes) return;
      form.dataset.confirmed = '1';
      if (form.requestSubmit) form.requestSubmit(submitter || undefined); else form.submit();
    });
  }, true);

  /* ---- 截图放大 ---- */
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
    img.alt = label || '训练截图';
    img.src = url;
    lightbox.showModal();
  }
  document.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-zoom]');
    if (!trigger) return;
    event.preventDefault();
    zoom(trigger.dataset.zoom || trigger.href, trigger.getAttribute('aria-label'));
  });

  /* ---- 趋势图提示 ---- */
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
})();
