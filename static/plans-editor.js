(() => {
  const root=document.getElementById('plan-editor'); if(!root)return;
  const $=id=>document.getElementById(id), copy=x=>JSON.parse(JSON.stringify(x));
  const node=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
  const button=(text,fn,cls='outline')=>{const b=node('button',cls,text);b.type='button';b.addEventListener('click',fn);return b;};
  let plan=JSON.parse($('plan-initial').textContent), revision=Number(root.dataset.revision), dirty=false, serial=0, busy=false, suggestions=[], searchStarted=false, previewSnapshot='', editPage=0;
  const boardHistories=new Map(), boardControllers=new Map(), boardViews=new Map();
  const kinds={fitness:'体能',ball:'有球',tactics:'战术',other:'其他'};
  const mark=()=>{dirty=true;serial++;$('save-status').textContent='有未保存的修改';};
  const closeExpandedWithin=container=>{container.querySelectorAll('.board-mount.is-expanded').forEach(n=>n.classList.remove('is-expanded'));document.body.classList.toggle('board-modal-open',!!document.querySelector('.board-mount.is-expanded'));};
  const fields={title:$('plan-title'),schedule:$('plan-schedule'),location:$('plan-location'),overview:$('plan-overview')};
  function syncFields(){Object.entries(fields).forEach(([key,input])=>input.value=plan[key]||'');}
  Object.entries(fields).forEach(([key,input])=>input.addEventListener('input',()=>{plan[key]=input.value;mark();}));
  async function post(url, values){const body=new FormData();body.set('csrf',root.dataset.csrf);Object.entries(values).forEach(([k,v])=>body.set(k,v));const response=await fetch(url,{method:'POST',body,credentials:'same-origin'});let result;try{result=await response.json();}catch{throw new Error('连接已失效，请刷新页面后重试。');}if(!response.ok)throw new Error(result.error||'操作失败，请重试。');return result;}
  function field(label,value,fn,opts={}){const wrap=node('label','',label), input=node(opts.textarea?'textarea':'input');if(opts.textarea)input.rows=opts.rows||3;else if(opts.type)input.type=opts.type;if(opts.max)input.maxLength=opts.max;if(opts.min!==undefined)input.min=opts.min;if(opts.maxNumber!==undefined)input.max=opts.maxNumber;input.value=value;input.addEventListener(opts.type==='number'?'change':'input',()=>fn(input.value,input));wrap.append(input);return wrap;}
  function renderItems(){
    const list=$('drill-list');if(list._planPager){list._planPager.remove();list._planPager=null;}boardControllers.forEach((controller,id)=>{if(plan.items.some(item=>item.id===id&&item.board))boardViews.set(id,controller.getContext());});closeExpandedWithin(list);list.replaceChildren();boardControllers.clear();
    if(!plan.items.length){list.append(node('div','empty','还没有训练项目。点击“添加项目”开始编辑。'));return;}
    plan.items.forEach((item,index)=>{
      const card=node('article','card drill-editor');card.dataset.planPage='';const heading=node('div','drill-editor-head'), title=node('div');
      title.append(node('p','plans-kicker',`项目 ${String(index+1).padStart(2,'0')}`),node('h3','','训练项目'));heading.append(title);
      const actions=node('div','drill-order');const up=button('前移',()=>{[plan.items[index-1],plan.items[index]]=[plan.items[index],plan.items[index-1]];editPage=index-1;mark();renderItems();});up.disabled=index===0;const down=button('后移',()=>{[plan.items[index],plan.items[index+1]]=[plan.items[index+1],plan.items[index]];editPage=index+1;mark();renderItems();});down.disabled=index===plan.items.length-1;const remove=button('删除',()=>{if(confirm('删除这个训练项目？')){plan.items.splice(index,1);mark();renderItems();}});actions.append(up,down,remove);heading.append(actions);card.append(heading);
      const titleField=field('项目名称',item.title,v=>{item.title=v;mark();},{max:100});card.append(titleField);
      const row=node('div','plan-fields'),kindLabel=node('label','','训练类型'), select=node('select');Object.entries(kinds).forEach(([key,label])=>{const o=node('option','',label);o.value=key;select.append(o);});select.value=item.kind;select.addEventListener('change',()=>{item.kind=select.value;mark();});kindLabel.append(select);
      row.append(kindLabel,field('时长（分钟）',item.minutes,(v,input)=>{item.minutes=Math.max(0,Math.min(600,parseInt(v,10)||0));input.value=item.minutes;mark();},{type:'number',min:0,maxNumber:600}));card.append(row);
      card.append(field('训练目标',item.goal,v=>{item.goal=v;mark();},{max:500}),field('步骤与要点',item.steps,v=>{item.steps=v;mark();},{textarea:true,rows:4,max:3000}));
      const boardArea=node('div','board-area');
      if(item.board){const removeBoard=button('移除战术板',()=>{if(confirm('移除这个项目的战术板？')){item.board=null;boardHistories.delete(item.id);boardViews.delete(item.id);mark();renderItems();}});const boardRoot=node('div','board-mount');boardArea.append(removeBoard,boardRoot);if(!boardHistories.has(item.id))boardHistories.set(item.id,{undo:[],redo:[]});const controller=window.TeamBoard.mount(boardRoot,item.board,{editable:true,onChange:mark,history:boardHistories.get(item.id),context:boardViews.get(item.id)});boardControllers.set(item.id,controller);}
      else boardArea.append(button('添加战术板',()=>{item.board=window.TeamBoard.fresh();mark();renderItems();}));
      card.append(boardArea);list.append(card);
    });
    window.PlanPager.mount(list,{index:editPage,onChange:(i,previous)=>{if(i!==previous)boardControllers.get(plan.items[previous]?.id)?.render();editPage=i;}});
  }
  $('add-drill').addEventListener('click',()=>{if(plan.items.length>=16){$('save-status').textContent='最多添加 16 个项目。';return;}plan.items.push({id:'i'+Math.random().toString(36).slice(2,10),title:'',kind:'other',goal:'',minutes:0,steps:'',board:null});editPage=plan.items.length-1;mark();renderItems();});
  let libraryRequest=0, libraryAdding=false;
  async function loadLibrary(){
    const request=++libraryRequest, status=$('library-status'), list=$('library-items');
    status.textContent='正在加载项目库……';
    try{
      const url=new URL(root.dataset.library,location.href);url.searchParams.set('q',$('library-query').value.trim());
      const response=await fetch(url,{credentials:'same-origin'});if(!response.ok)throw Error('项目库暂时不可用，请重试。');
      const result=await response.json();if(request!==libraryRequest)return;list.replaceChildren();
      status.textContent=result.items.length?'显示最近 '+result.items.length+' 项，可搜索其他项目。':'没有找到训练项目；保存计划后会自动收录。';
      result.items.forEach(item=>{
        const row=node('div','library-item'),detail=node('div');
        detail.append(node('strong','',item.title||'未命名项目'),node('p','',[kinds[item.kind]||'其他',item.minutes?item.minutes+' 分钟':'',item.has_board?'含战术板':''].filter(Boolean).join(' · ')));
        if(item.goal||item.steps)detail.append(node('p','',(item.goal||item.steps).slice(0,80)));
        const add=button('加入计划',async()=>{
          if(libraryAdding)return;
          if(plan.items.length>=16){status.textContent='一份计划最多添加 16 个项目。';return;}
          libraryAdding=true;add.disabled=true;add.textContent='正在添加…';$('save-plan').disabled=true;$('preview-plan').disabled=true;
          try{
            const response=await fetch(root.dataset.library+'/'+item.library_id,{credentials:'same-origin'});
            if(!response.ok)throw Error('无法读取项目，请重试。');
            const saved=(await response.json()).item;
            if(plan.items.length>=16){status.textContent='一份计划最多添加 16 个项目。';return;}
            let id;do{id='i'+Math.random().toString(36).slice(2,10);}while(plan.items.some(x=>x.id===id));
            plan.items.push({id,title:saved.title,kind:saved.kind,goal:saved.goal,minutes:saved.minutes,steps:saved.steps,board:saved.board?copy(saved.board):null});
            editPage=plan.items.length-1;mark();renderItems();$('drill-library').open=false;
            $('drill-list').scrollIntoView({block:'start',behavior:'auto'});
          }catch(e){status.textContent=e.message||'无法读取项目，请重试。';}finally{libraryAdding=false;add.disabled=false;add.textContent='加入计划';$('save-plan').disabled=busy;$('preview-plan').disabled=false;}
        });
        row.append(detail,add);list.append(row);
      });
    }catch(e){if(request===libraryRequest){list.replaceChildren();status.textContent=e.message||'项目库暂时不可用，请重试。';}}
  }
  $('drill-library').addEventListener('toggle',()=>{if($('drill-library').open)loadLibrary();});
  $('library-search').addEventListener('click',loadLibrary);
  $('library-query').addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();loadLibrary();}});
  function videoRow(v,selected){const row=node('div','video-row'),link=node('a','',v.title);link.href=v.url;link.target='_blank';link.rel='noopener noreferrer';const details=node('div');details.append(link,node('small','',v.source));row.append(details);const action=button(selected?'移除':'选入计划',()=>{if(selected)plan.videos=plan.videos.filter(x=>x.url!==v.url);else if(!plan.videos.some(x=>x.url===v.url)){if(plan.videos.length>=20)return;plan.videos.push(v);}mark();renderVideos();});if(!selected&&plan.videos.some(x=>x.url===v.url)){action.disabled=true;action.textContent='已选';}row.append(action);return row;}
  function renderVideos(){const a=$('video-suggestions'),b=$('video-selected');a.replaceChildren();b.replaceChildren();suggestions.forEach(v=>a.append(videoRow(v,false)));if(!plan.videos.length)b.append(node('p','hint','还没有选入视频。'));else plan.videos.forEach(v=>b.append(videoRow(v,true)));}
  async function searchVideos(){searchStarted=true;$('video-status').textContent='正在搜索相关视频……';$('search-videos').disabled=true;try{const result=await post(root.dataset.videos,{items:JSON.stringify(plan.items.map(({title,goal})=>({title,goal})))});suggestions=result.videos||[];$('video-status').textContent=result.search==='error'?'视频搜索暂时不可用，可以稍后重试或手动添加。':suggestions.length?'已找到相关视频，请核对后选入。':'没有找到符合条件的视频，可以手动添加。';renderVideos();}catch(e){$('video-status').textContent=e.message;}finally{$('search-videos').disabled=false;}}
  $('search-videos').addEventListener('click',searchVideos);
  $('add-video').addEventListener('click',()=>{const title=$('video-title').value.trim(),raw=$('video-url').value.trim();try{const u=new URL(raw);if(!title||u.protocol!=='https:'||u.username||u.password||(u.port&&u.port!=='443'))throw Error();if(plan.videos.length>=20)throw Error();if(!plan.videos.some(v=>v.url===u.href))plan.videos.push({title,url:u.href,source:u.hostname});$('video-title').value='';$('video-url').value='';$('video-status').textContent='链接已选入，请核对视频内容。';mark();renderVideos();}catch{$('video-status').textContent='请填写标题和有效的 HTTPS 视频链接。';}});
  async function save(action){if(busy||libraryAdding)return;busy=true;$('save-plan').disabled=true;$('publish-plan').disabled=true;const savedSerial=serial;try{const result=await post(root.dataset.save,{action,revision:String(revision),plan:JSON.stringify(plan)});revision=result.revision;dirty=serial!==savedSerial;$('save-status').textContent=dirty?'已保存提交时的内容，之后的修改尚未保存。':action==='publish'?'已发布给队员。':'草稿已保存。';if($('drill-library').open)loadLibrary();if(action==='publish'&&!dirty)location.href=result.view_url;}catch(e){$('save-status').textContent=e.message;$('save-status').scrollIntoView({block:'nearest'});}finally{busy=false;$('save-plan').disabled=libraryAdding;$('publish-plan').disabled=false;}}
  $('save-plan').addEventListener('click',()=>{if(!searchStarted && plan.items.some(i=>i.title.trim()))searchVideos();save('save');});
  function renderPreview(){
    const box=$('preview-content');closeExpandedWithin(box);box.replaceChildren();
    box.append(node('h2','',plan.title||'未命名计划'),node('p','',`${plan.schedule||'时间待定'}${plan.location?' · '+plan.location:''}`));
    if(plan.overview)box.append(node('p','',plan.overview));
    const pages=node('div','plan-pages'),controllers=[];box.append(pages);
    plan.items.forEach((item,i)=>{
      const article=node('article','preview-drill');article.dataset.planPage='';
      article.append(node('h3','',`${i+1}. ${item.title||'未命名项目'}${item.minutes?' · '+item.minutes+' 分钟':''}`));
      if(item.goal)article.append(node('p','','目标：'+item.goal));if(item.steps)article.append(node('p','drill-steps',item.steps));
      if(item.board){const mount=node('div','board-mount');article.append(mount);controllers[i]=()=>window.TeamBoard.mount(mount,copy(item.board));}
      pages.append(article);
    });
    const mounted={};window.PlanPager.mount(pages,{onChange:(i,previous)=>{
      if(mounted[previous]&&previous!==i)mounted[previous].render();
      if(controllers[i]&&!mounted[i])mounted[i]=controllers[i]();
    }});
    if(plan.videos.length){box.append(node('h3','editor-subhead','参考视频'));plan.videos.forEach(v=>{const a=node('a','preview-video',v.title+' · '+v.source+' ↗');a.href=v.url;a.target='_blank';a.rel='noopener noreferrer';box.append(a);});}
  }
  $('preview-plan').addEventListener('click',()=>{if(!searchStarted&&plan.items.some(i=>i.title.trim()))searchVideos();previewSnapshot=JSON.stringify(plan);renderPreview();$('plan-preview').hidden=false;$('plan-preview').scrollIntoView({behavior:'smooth',block:'start'});});
  $('close-preview').addEventListener('click',()=>{closeExpandedWithin($('plan-preview'));$('plan-preview').hidden=true;});
  $('publish-plan').addEventListener('click',()=>{if(JSON.stringify(plan)!==previewSnapshot){$('save-status').textContent='内容已变化，请重新预览后发布。';$('plan-preview').hidden=true;return;}save('publish');});
  window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
  syncFields();renderItems();renderVideos();
})();
