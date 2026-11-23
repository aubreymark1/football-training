(() => {
  const form = document.querySelector('#avatar-form');
  if (!form) return;
  const input = form.elements.avatar;
  const button = form.querySelector('button[type=submit], button:not([type])');
  const status = document.querySelector('#avatar-status');
  const box = form.querySelector('.upload');
  const thumb = form.querySelector('.upload-thumb');
  const name = form.querySelector('.upload-text strong');
  const meta = form.querySelector('.upload-text small');
  const idle = { name: name.textContent, meta: meta.textContent };
  let preview = '';
  let version = 0;
  let processing = false;

  const size = (bytes) => bytes < 1024 * 1024
    ? Math.max(1, Math.round(bytes / 1024)) + ' KB'
    : (bytes / 1024 / 1024).toFixed(1) + ' MB';

  function show(file, note) {
    if (preview) URL.revokeObjectURL(preview);
    preview = file ? URL.createObjectURL(file) : '';
    box.classList.toggle('has-file', Boolean(file));
    thumb.style.backgroundImage = file ? 'url("' + preview + '")' : '';
    name.textContent = file ? file.name : idle.name;
    meta.textContent = file ? size(file.size) + (note || '') + '，点这里可以重新选' : idle.meta;
  }

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
    return new File([blob], 'avatar.jpg', { type: 'image/jpeg' });
  }

  input.addEventListener('change', async () => {
    const current = ++version;
    let file = input.files && input.files[0];
    status.textContent = '';
    if (!file) { processing = false; button.disabled = false; show(null); return; }
    processing = true; button.disabled = true;
    show(file, '，正在缩小');
    try {
      const compressed = await compress(file);
      if (current !== version) return;
      const transfer = new DataTransfer();
      transfer.items.add(compressed);
      input.files = transfer.files;
      show(compressed);
      status.textContent = '图片已缩小，可以上传。';
    } catch (_) {
      if (current !== version) return;
      input.value = '';
      show(null);
      status.textContent = '无法处理这张图片，请换一张 JPG、PNG 或截图后重试。';
    } finally {
      if (current === version) { processing = false; button.disabled = false; }
    }
  });
  form.addEventListener('submit', event => {
    if (processing) { event.preventDefault(); status.textContent = '图片正在处理，请稍等。'; }
  });
})();
