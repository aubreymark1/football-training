document.addEventListener('click',event=>{
  const link=event.target.closest('[data-comment-open]');
  if(!link)return;
  const box=document.getElementById(link.dataset.commentOpen);
  if(!box)return;
  event.preventDefault();box.classList.toggle('is-open');
  const menu=link.closest('.moment-actions');if(menu)menu.open=false;
  if(box.classList.contains('is-open'))box.querySelector('input[name=content]')?.focus();
});
