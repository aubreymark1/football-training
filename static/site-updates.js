(() => {
  const dialog = document.getElementById('site-update');
  if (!dialog) return;
  if (typeof dialog.showModal === 'function') {
    dialog.addEventListener('cancel', event => event.preventDefault());
    dialog.showModal();
  } else {
    dialog.setAttribute('open', '');
    dialog.setAttribute('role', 'dialog');
  }
})();
