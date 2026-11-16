(() => {
  const root = document.getElementById('tour');
  if (!root) return;

  const STEPS = [
    { title: '第 1 步 · 每周任务', body: '这里列出本周的必做和附加任务。必做任务没完成，这一周会扣 10 分；附加任务每完成 1 项加积分。', target: '#guide-tasks' },
    { title: '第 2 步 · 提交训练记录', body: '练完点任务右侧的「去提交」，选择运动类型、填写时长和主观用力，再上传截图。管理员审核通过后才算完成。', target: '.required-block .task-go, .home-grid .module, #guide-records' },
    { title: '第 3 步 · 积分商城', body: '底部「积分」里可以用积分兑换球队礼品，申请后由管理员线下交付。', target: '#guide-nav-rewards' },
    { title: '第 4 步 · 球队概览', body: '「球队」页有积分排名。排名后 20% 会被标出来，当周需要额外完成 1 项附加训练。', target: '#guide-nav-team' },
    { title: '第 5 步 · 训练助手', body: '「助手」里可以问训练安排和球队信息。训练类问题会自动检索资料和视频，也可以开启深度思考。', target: '#guide-nav-assistant' },
    { title: '第 6 步 · 可以开始了', body: '完成训练后记得提交记录。想再看一遍，可以在「账号」里重新打开这个引导。', target: '' }
  ];

  let index = 0;
  const overlay = document.createElement('div');
  overlay.className = 'tour-overlay';
  const spot = document.createElement('div');
  spot.className = 'tour-spot';
  spot.hidden = true;
  const bubble = document.createElement('div');
  bubble.className = 'tour-bubble';
  bubble.setAttribute('role', 'dialog');
  bubble.setAttribute('aria-modal', 'true');
  bubble.setAttribute('aria-label', '新手引导');
  bubble.tabIndex = -1;
  bubble.innerHTML = '<div class="tour-top"><span class="tour-step"></span><button type="button" class="tour-skip">跳过</button></div><h2 class="tour-title"></h2><p class="tour-body"></p><div class="tour-foot"><div class="tour-dots" aria-hidden="true"></div><div class="tour-actions"><button type="button" class="tour-prev outline">上一步</button><button type="button" class="tour-next primary">下一步</button></div></div>';

  document.body.append(overlay, spot, bubble);
  document.body.classList.add('tour-open');

  const stepLabel = bubble.querySelector('.tour-step');
  const titleEl = bubble.querySelector('.tour-title');
  const bodyEl = bubble.querySelector('.tour-body');
  const dotsEl = bubble.querySelector('.tour-dots');
  const prevBtn = bubble.querySelector('.tour-prev');
  const nextBtn = bubble.querySelector('.tour-next');
  const skipBtn = bubble.querySelector('.tour-skip');

  function findTarget(step) {
    if (!step.target) return null;
    for (const selector of step.target.split(',')) {
      const el = document.querySelector(selector.trim());
      if (el) return el;
    }
    return null;
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function place() {
    const step = STEPS[index];
    stepLabel.textContent = (index + 1) + ' / ' + STEPS.length;
    titleEl.textContent = step.title;
    bodyEl.textContent = step.body;
    prevBtn.disabled = index === 0;
    nextBtn.textContent = index === STEPS.length - 1 ? '完成' : '下一步';
    dotsEl.innerHTML = STEPS.map((_, i) => '<span class="' + (i === index ? 'on' : '') + '"></span>').join('');

    const target = findTarget(step);
    let anchor = null;
    if (target) {
      const rect = target.getBoundingClientRect();
      // 底部导航是 fixed，滚动它没有意义，反而可能把页面滚走
      if (!target.closest('.bottom') && (rect.top < 8 || rect.bottom > window.innerHeight - 8)) {
        target.scrollIntoView({ block: 'center' });
      }
      anchor = target.getBoundingClientRect();
      const pad = 6;
      // 贴边的元素（手机底栏、桌面顶栏）把高亮框裁进视口，避免光晕被切掉
      const left = Math.max(0, anchor.left - pad);
      const top = Math.max(0, anchor.top - pad);
      const width = Math.min(anchor.width + pad * 2, window.innerWidth - left);
      const height = Math.min(anchor.height + pad * 2, window.innerHeight - top);
      spot.hidden = false;
      // 只改 transform 和尺寸，移动时不触发整页重排
      spot.style.transform = 'translate(' + Math.round(left) + 'px,' + Math.round(top) + 'px)';
      spot.style.width = Math.round(width) + 'px';
      spot.style.height = Math.round(height) + 'px';
    } else {
      spot.hidden = true;
    }

    // offsetWidth/offsetHeight 不受 transform 影响，气泡在移动途中也能量准
    const size = { width: bubble.offsetWidth, height: bubble.offsetHeight };
    const margin = 16;
    let left;
    let top;
    if (anchor) {
      left = clamp(anchor.left, margin, window.innerWidth - size.width - margin);
      const below = anchor.bottom + 14;
      const above = anchor.top - size.height - 14;
      top = below + size.height <= window.innerHeight - margin ? below : Math.max(margin, above);
    } else {
      left = (window.innerWidth - size.width) / 2;
      top = Math.max(margin, (window.innerHeight - size.height) / 2);
    }
    bubble.style.transform = 'translate(' + Math.round(left) + 'px,' + Math.round(top) + 'px)';
  }

  function markSeen() {
    try {
      const body = new FormData();
      body.set('csrf', root.dataset.csrf || '');
      fetch(root.dataset.markUrl, { method: 'POST', body, credentials: 'same-origin' }).catch(() => {});
    } catch (e) {
      /* 标记失败不影响使用，下次进入会再显示 */
    }
  }

  function close(mark) {
    document.removeEventListener('keydown', onKey);
    window.removeEventListener('resize', place);
    overlay.remove();
    spot.remove();
    bubble.remove();
    document.body.classList.remove('tour-open');
    if (mark) markSeen();
  }

  function next() {
    if (index === STEPS.length - 1) close(true);
    else { index += 1; place(); bubble.focus(); }
  }

  function prev() {
    if (index > 0) { index -= 1; place(); bubble.focus(); }
  }

  function onKey(event) {
    const key = event.key;
    if (key === 'Escape') { event.preventDefault(); close(true); }
    else if (key === 'ArrowRight') { event.preventDefault(); next(); }
    else if (key === 'ArrowLeft') { event.preventDefault(); prev(); }
  }

  nextBtn.addEventListener('click', next);
  prevBtn.addEventListener('click', prev);
  skipBtn.addEventListener('click', () => close(true));
  overlay.addEventListener('click', (event) => event.stopPropagation());
  document.addEventListener('keydown', onKey);
  window.addEventListener('resize', place);

  place();
  bubble.focus();
})();
