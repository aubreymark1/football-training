(() => {
  const dataEl = document.getElementById('case-data');
  if (!dataEl) return;

  const data = JSON.parse(dataEl.textContent);
  const track = document.getElementById('case-track');
  const reel = track.parentElement;
  const btn = document.getElementById('case-open');
  const wish = document.getElementById('case-wish');
  const result = document.getElementById('case-result');
  const balanceEl = document.getElementById('case-balance');
  const progressEl = document.getElementById('case-progress');
  const barEl = document.getElementById('case-bar');
  const reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  let token = null;
  const WIN_INDEX = 40;

  const tiles = [
    ...data.items.map((x) => ({ name: x.name, img: data.assetBase.replace('__FILE__', x.image) })),
    { name: '0.5积分奖励' },
    { name: '1积分奖励' },
    { name: '2积分奖励' },
    { name: '谢谢参与' }
  ];

  function createTile(item) {
    const el = document.createElement('div');
    el.className = 'case-tile';
    if (item.img) {
      const img = document.createElement('img');
      img.src = item.img;
      img.alt = '';
      el.appendChild(img);
    } else {
      const icon = document.createElement('div');
      icon.style.cssText = 'height:96px;display:grid;place-items:center;font:500 18px var(--mono);color:var(--text-3);background:var(--bg-deep);border-radius:4px';
      icon.textContent = item.name === '谢谢参与' ? '—' : '+' + item.name.replace('积分奖励', '');
      el.appendChild(icon);
    }
    const label = document.createElement('span');
    label.textContent = item.name;
    el.appendChild(label);
    return el;
  }

  function populate(finalItem) {
    track.replaceChildren();
    for (let i = 0; i < 46; i++) {
      const pick = i === WIN_INDEX ? finalItem : tiles[Math.floor(Math.random() * tiles.length)];
      track.appendChild(createTile(pick));
    }
    track.style.transition = 'none';
    track.style.transform = 'translateX(0)';
  }

  function syncPrizeStock(prizeName) {
    const card = Array.from(document.querySelectorAll('.case-prize[data-prize-name]')).find(
      (el) => el.dataset.prizeName === prizeName
    );
    if (!card) return;
    const stockSpan = card.querySelector('.prize-stock');
    if (stockSpan) {
      const m = stockSpan.textContent.match(/(\d+)/);
      if (m) {
        const nextStock = Math.max(0, Number(m[1]) - 1);
        stockSpan.textContent = '库存 ' + nextStock;
        if (nextStock === 0 && card.dataset.prizeId) {
          const opt = wish.querySelector(`option[value="${card.dataset.prizeId}"]`);
          if (opt) {
            opt.disabled = true;
            if (!opt.textContent.includes('已兑完')) opt.textContent += '（已兑完）';
            if (wish.value === card.dataset.prizeId) {
              const fallback = wish.querySelector('option:not(:disabled)');
              if (fallback) wish.value = fallback.value;
            }
          }
        }
      }
    }
  }

  populate(tiles[0] || { name: '谢谢参与' });

  wish.addEventListener('change', async () => {
    btn.disabled = true;
    try {
      const response = await fetch(data.wishUrl, {
        method: 'POST',
        body: new URLSearchParams({ csrf: data.csrf, wish: wish.value }),
        credentials: 'same-origin'
      });
      const payload = await response.json();
      result.textContent = response.ok ? '已保存保底偏好' : (payload.error || '保存失败，请重试');
    } catch (_) {
      result.textContent = '网络中断，将在下次开箱时同步';
    } finally {
      const availableOpt = wish.querySelector('option:not(:disabled)');
      btn.disabled = !availableOpt || Number(balanceEl.textContent) < 1;
    }
  });

  btn.addEventListener('click', async () => {
    if (!wish.value) return;
    btn.disabled = true;
    wish.disabled = true;
    result.textContent = '正在抽取…';
    token = token || crypto.randomUUID();
    const body = new URLSearchParams({ csrf: data.csrf, wish: wish.value, token });

    let response;
    let payload;
    try {
      response = await fetch(data.drawUrl, { method: 'POST', body, credentials: 'same-origin' });
      payload = await response.json();
      if (!response.ok) {
        token = null;
        result.textContent = payload.error || '未完成，请重试';
        btn.disabled = false;
        wish.disabled = false;
        return;
      }
    } catch (_) {
      result.textContent = '网络中断，再次点击可恢复本次结果';
      btn.disabled = false;
      wish.disabled = false;
      return;
    }

    token = null;
    const finalItem = tiles.find((x) => x.name === payload.result) || { name: payload.result };
    populate(finalItem);
    const dest = track.children[WIN_INDEX];
    const targetX = reel.clientWidth / 2 - dest.offsetLeft - dest.offsetWidth / 2;
    const spinDuration = reduced ? 40 : 4600;

    requestAnimationFrame(() => requestAnimationFrame(() => {
      track.style.transition = reduced ? 'none' : 'transform 4.6s cubic-bezier(.22, 1, .36, 1)';
      track.style.transform = `translateX(${targetX}px)`;
    }));

    setTimeout(() => {
      dest.classList.add('is-winner');
      const isPhysical = !payload.result.includes('积分奖励') && payload.result !== '谢谢参与';
      result.textContent = (payload.guaranteed ? '保底结果：' : '结果：') + payload.result;
      balanceEl.textContent = payload.points;
      progressEl.textContent = payload.progress;
      barEl.style.width = (payload.progress * 2) + '%';

      if (isPhysical) {
        result.textContent += ' · 已计入兑换记录';
        if (!payload.duplicate) syncPrizeStock(payload.result);
      }

      const hasAvailable = Boolean(wish.querySelector('option:not(:disabled)'));
      wish.disabled = false;
      btn.disabled = !hasAvailable || payload.points < 1;
    }, spinDuration + 80);
  });
})();
