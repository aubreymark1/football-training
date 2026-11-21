(() => {
  const form = document.querySelector('#avatar-form');
  if (!form) return;
  const input = form.elements.avatar;
  const button = form.querySelector('button[type=submit], button:not([type])');
  const status = document.querySelector('#avatar-status');
  let version = 0;
  let processing = false;

  function loadImage(file) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const image = new Image();
      image.onload = () => { URL.revokeObjectURL(url); resolve(image); };
      image.onerror = () => { URL.revokeObjectURL(url); reject(new Error('unsupported')); };
      image.src = url;
    });
  }
  async function compress(file) {
    const image = await loadImage(file);
    const width = image.naturalWidth, height = image.naturalHeight;
    if (!width || !height) throw new Error('empty image');
    const ratio = Math.min(1, 1024 / Math.max(width, height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(width * ratio));
    canvas.height = Math.max(1, Math.round(height * ratio));
    const context = canvas.getContext('2d');
    if (!context) throw new Error('canvas unavailable');
    context.fillStyle = '#fff';
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.85));
    if (!blob || blob.size > 7 * 1024 * 1024) throw new Error('compression failed');
    return new File([blob], 'avatar.jpg', {type: 'image/jpeg'});
  }
  input.addEventListener('change', async () => {
    const current = ++version;
    const file = input.files && input.files[0];
    status.textContent = '';
    if (!file) { processing = false; button.disabled = false; return; }
    processing = true; button.disabled = true;
    status.textContent = ' 正在压缩图片…';
    try {
      const compressed = await compress(file);
      if (current !== version) return;
      const transfer = new DataTransfer();
      transfer.items.add(compressed);
      input.files = transfer.files;
      status.textContent = ' 图片已压缩，可以上传。';
    } catch (_) {
      if (current !== version) return;
      input.value = '';
      status.textContent = ' 无法处理这张图片，请换一张 JPG、PNG 或截图后重试。';
    } finally {
      if (current === version) { processing = false; button.disabled = false; }
    }
  });
  form.addEventListener('submit', event => {
    if (processing) { event.preventDefault(); status.textContent = ' 图片正在压缩，请稍等。'; }
  });
})();
