(() => {
  const pages=document.getElementById('published-pages');
  const boards=Array.from(pages.querySelectorAll('[data-plan-page]')).map(page=>page.querySelector('.board-mount'));
  const mounted={};
  window.PlanPager.mount(pages,{onChange:(index,previous)=>{
    if(mounted[previous]&&previous!==index)mounted[previous].render();
    const root=boards[index];
    if(root&&!mounted[index]){
      const data=root.querySelector('.board-data');
      if(data)mounted[index]=window.TeamBoard.mount(root,JSON.parse(data.textContent));
    }
  }});
})();
