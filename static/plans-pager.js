/* Pagination is added in JavaScript so all projects remain readable without it. */
(() => {
  function mount(list, {index=0, onChange=()=>{}}={}) {
    if (list._planPager) list._planPager.remove();
    const pages=Array.from(list.children).filter(el=>el.matches('[data-plan-page]'));
    if (!pages.length) return;
    let current=Math.max(0,Math.min(index,pages.length-1));
    const nav=document.createElement('nav');nav.className='plan-pager';nav.setAttribute('aria-label','训练项目分页');
    const prev=document.createElement('button'), next=document.createElement('button'), counter=document.createElement('span');
    prev.type=next.type='button';prev.className=next.className='outline';prev.textContent='上一项';next.textContent='下一项';
    counter.className='plan-page-count';counter.setAttribute('aria-live','polite');
    nav.append(prev,counter,next);list.after(nav);list._planPager=nav;
    function show(target,animate=false){
      const before=current;current=Math.max(0,Math.min(target,pages.length-1));
      pages.forEach((page,i)=>{page.hidden=i!==current;page.classList.remove('plan-page-enter');});
      if(animate){void pages[current].offsetWidth;pages[current].classList.add('plan-page-enter');}
      prev.disabled=current===0;next.disabled=current===pages.length-1;
      counter.textContent=`第 ${current+1} / ${pages.length} 项`;
      nav.hidden=pages.length<2;
      onChange(current,before);
      if(animate)pages[current].scrollIntoView({block:'start',behavior:'auto'});
    }
    prev.addEventListener('click',()=>show(current-1,true));
    next.addEventListener('click',()=>show(current+1,true));
    show(current);
  }
  window.PlanPager={mount};
})();
