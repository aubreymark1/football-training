/* 从训练详情、比赛详情或首页带 #training-3 / #match-5 过来时，展开对应那条并定位。 */
(() => {
  const reveal = (hash) => {
    if (!hash || hash.length < 2) return;
    let target;
    try {
      target = document.getElementById(decodeURIComponent(hash.slice(1)));
    } catch (_) {
      return;
    }
    if (!target) return;
    for (let node = target; node; node = node.parentElement) {
      if (node.tagName === 'DETAILS') node.open = true;
    }
    requestAnimationFrame(() => target.scrollIntoView({ block: 'center' }));
  };
  reveal(location.hash);
  window.addEventListener('hashchange', () => reveal(location.hash));
})();
