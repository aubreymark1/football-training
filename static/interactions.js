/* 动态和赛后反思的点赞、评论：先发异步请求局部更新，失败再退回整页提交。 */
(() => {
  async function send(form, submitter) {
    const body = new FormData(form);
    if (submitter && submitter.name) body.append(submitter.name, submitter.value);
    const response = await fetch(form.action, {
      method: 'POST',
      body,
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'fetch', Accept: 'application/json' },
    });
    if (!response.ok) throw new Error('HTTP ' + response.status);
    if (!(response.headers.get('content-type') || '').includes('application/json')) throw new Error('not json');
    return response.json();
  }

  function fallback(form, button) {
    form.removeAttribute('data-remote');
    if (button) button.disabled = false;
    delete form.dataset.busy;
    if (form.requestSubmit) form.requestSubmit();
    else form.submit();
  }

  document.addEventListener('submit', async (event) => {
    const form = event.target.closest('form[data-remote]');
    if (!form || event.defaultPrevented) return;
    event.preventDefault();
    if (form.dataset.busy) return;
    form.dataset.busy = '1';
    const button = form.querySelector('button');
    if (button) button.disabled = true;
    try {
      const data = await send(form, event.submitter);
      if (data.label !== undefined && button) button.textContent = data.label;
      if (data.liked !== undefined) {
        form.dataset.liked = data.liked ? '1' : '0';
        if (button) button.classList.toggle('is-liked', Boolean(data.liked));
      }
      const card = form.closest('[data-card]') || document;
      const slot = form.dataset.replace && card.querySelector(form.dataset.replace);
      if (form.dataset.replace && data.html !== undefined) {
        if (data.html) {
          if (slot) slot.outerHTML = data.html;
          else {
            const anchor = card.querySelector(form.dataset.anchor) || form;
            anchor.insertAdjacentHTML('beforebegin', data.html);
          }
        } else if (slot) slot.remove();
      } else if (data.html) {
        form.insertAdjacentHTML('beforebegin', data.html);
      }
      const input = form.querySelector('input[name=content]');
      if (input && form.dataset.remote === 'comment') {
        input.value = '';
        if (window.matchMedia && window.matchMedia('(hover: hover)').matches) input.focus();
      }
    } catch (_) {
      fallback(form, button);
      return;
    }
    if (button) button.disabled = false;
    delete form.dataset.busy;
  });
})();
