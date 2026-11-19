/* Editable tactics board. Coordinates and waypoints are stored as percentages. */
(() => {
  const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
  const btn=(text,fn,cls='outline')=>{const n=el('button',cls,text);n.type='button';n.addEventListener('click',fn);return n;};
  const copy=value=>JSON.parse(JSON.stringify(value));
  const ident=prefix=>prefix+Math.random().toString(36).slice(2,10);
  const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
  const pct=(x,y)=>[Math.round(clamp(x,0,100)*100)/100,Math.round(clamp(y,0,100)*100)/100];
  const dist=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
  function normalize(board){
    board.pitch=board.pitch||'full';board.attack=board.attack||'right';
    board.frames.forEach(frame=>{frame.paths=frame.paths||{};frame.marks=frame.marks||[];});
    return board;
  }
  function fresh(){
    const positions={p1:[25,20],p2:[60,55],b1:[30,20]};
    return normalize({pitch:'full',attack:'right',players:[{id:'p1',type:'home',label:'A'},{id:'p2',type:'home',label:'B'},{id:'b1',type:'ball',label:''}],frames:[{label:'起始位置',duration:1,positions:copy(positions)}]});
  }
  function formation(size){
    const groups=size===5?[[12,50],[35,28],[35,72],[65,32],[65,68]]:size===7?[[10,50],[30,22],[30,50],[30,78],[58,30],[58,70],[77,50]]:[[8,50],[25,14],[25,38],[25,62],[25,86],[50,22],[50,50],[50,78],[75,18],[75,50],[75,82]];
    const players=groups.map((_,i)=>({id:'p'+(i+1),type:'home',label:i===0?'GK':String(i+1)}));players.push({id:'ball1',type:'ball',label:''});
    const positions={};players.forEach((p,i)=>positions[p.id]=p.type==='ball'?[13,50]:groups[i].slice());
    return normalize({pitch:'full',attack:'right',players,frames:[{label:'起始位置',duration:1,positions:copy(positions)}]});
  }
  function pathPoint(start,end,via,progress){
    const points=[start,...(via||[]),end],lengths=[];let total=0;
    for(let i=0;i<points.length-1;i++){const d=dist(points[i],points[i+1]);lengths.push(d);total+=d;}
    if(!total)return end.slice();let left=clamp(progress,0,1)*total;
    for(let i=0;i<lengths.length;i++){if(left<=lengths[i]||i===lengths.length-1){const t=lengths[i]?left/lengths[i]:0;return [points[i][0]+(points[i+1][0]-points[i][0])*t,points[i][1]+(points[i+1][1]-points[i][1])*t];}left-=lengths[i];}
    return end.slice();
  }
  function mount(root,board,options={}){
    normalize(board);
    const editable=!!options.editable, changed=options.onChange||(()=>{}), askAI=options.onAskAI;
    const history=options.history||{undo:[],redo:[]};
    const initial=options.context||{};
    let index=Number.isInteger(initial.frame)?clamp(initial.frame-1,0,board.frames.length-1):0;
    let selected=board.players.some(p=>p.id===initial.object_id)?initial.object_id:board.players[0]?.id,animation=null,mode='select',routeTarget='new',expanded=false,previewPoints=null;
    let speed=1,loop=false,gesture=null;
    const markerId=ident('arrow');
    const message={select:'拖动球员或足球调整当前动作的位置。',run:'选择球员，再从球员拖出跑动路线；也可点球场确定终点。',dribble:'选择持球球员，再拖出带球路线；足球会一起移动。',pass:'选择持球球员或足球，再拖出传球路线。',shot:'选择持球球员或足球，向球门拖出射门路线。',arrow:'在球场上拖动，绘制战术箭头。',line:'在球场上拖动，绘制战术线。',zone:'在球场上拖动，圈出训练区域。',text:'先填写文字，再点击球场放置标注。'};
    const stop=()=>{if(animation!==null)cancelAnimationFrame(animation);animation=null;};
    const record=before=>{history.undo.push(before);if(history.undo.length>40)history.undo.shift();history.redo=[];changed();};
    const replace=value=>{Object.keys(board).forEach(k=>delete board[k]);Object.assign(board,normalize(copy(value)));selected=board.players.some(p=>p.id===selected)?selected:board.players[0]?.id;index=Math.min(index,board.frames.length-1);};
    const mutate=fn=>{const before=copy(board);fn();record(before);render();};
    const nameOf=p=>p.type==='ball'?'足球':p.type==='cone'?'标志桶'+(p.label?' '+p.label:''):(p.type==='home'?'我队 ':'对方 ')+(p.label||p.id);
    const nearBall=(frame,actor)=>{
      if(actor.type==='ball')return actor;
      const balls=board.players.filter(p=>p.type==='ball');if(!balls.length)return null;
      balls.sort((a,b)=>dist(frame.positions[a.id],frame.positions[actor.id])-dist(frame.positions[b.id],frame.positions[actor.id]));
      return dist(frame.positions[balls[0].id],frame.positions[actor.id])<=16?balls[0]:null;
    };
    function appendAction(kind,actor,to,via){
      const replacing=routeTarget==='existing';
      if(!replacing&&board.frames.length>=16){showStatus('最多添加 16 个动作。');return;}
      if(replacing&&index>=board.frames.length-1){showStatus('当前是最后一步，请选择前一步或新建下一步。');return;}
      if(['run','dribble'].includes(kind)&&!['home','away'].includes(actor.type)){showStatus('请先选中一名球员。');return;}
      if(['pass','shot'].includes(kind)&&!['home','away','ball'].includes(actor.type)){showStatus('请选择球员或足球。');return;}
      if(['pass','shot','dribble'].includes(kind)&&!nearBall(board.frames[index],actor)){showStatus('先把足球放到持球人附近，再绘制这个动作。');return;}
      const before=copy(board),source=board.frames[index];
      let next;
      if(replacing)next=board.frames[index+1];
      else{next=copy(source);const oldPaths=copy(source.paths);source.paths={};next.paths=oldPaths;next.label={run:'跑动',dribble:'带球',pass:'传球',shot:'射门'}[kind];next.duration=2;}
      if(kind==='pass'||kind==='shot'){
        const ball=nearBall(source,actor);next.positions[ball.id]=to;source.paths[ball.id]={kind,via};
      }else{
        next.positions[actor.id]=to;source.paths[actor.id]={kind,via};
        if(kind==='dribble'){
          const ball=nearBall(source,actor),a=source.positions[actor.id],b=source.positions[ball.id],dx=b[0]-a[0],dy=b[1]-a[1];
          next.positions[ball.id]=pct(to[0]+dx,to[1]+dy);source.paths[ball.id]={kind:'dribble',via:via.map(p=>pct(p[0]+dx,p[1]+dy))};
        }
      }
      if(replacing){
        Object.keys(next.positions).forEach(id=>{
          if(dist(next.positions[id],before.frames[index+1].positions[id])<.001)return;
          for(let i=index+2;i<board.frames.length;i++){
            const previous=before.frames[i-1],following=before.frames[i];
            if(dist(previous.positions[id],following.positions[id])>.001||(previous.paths[id]?.via||[]).length)break;
            board.frames[i].positions[id]=next.positions[id].slice();
          }
        });
      }else{board.frames.splice(index+1,0,next);index++;}mode='select';record(before);render();
    }
    let statusLine=null;
    function showStatus(text){if(statusLine)statusLine.textContent=text;}
    function render(){
      stop();root.replaceChildren();
      const shell=el('div','tactics-board');
      const header=el('div','tactics-head');
      const heading=el('div');heading.append(el('strong','','战术板'),el('span','hint',(board.pitch==='half'?'半场':'全场')+' · '+(board.attack==='right'?'向右进攻 →':'← 向左进攻')));header.append(heading);
      const topActions=el('div','board-top-actions');
      if(editable&&askAI)topActions.append(btn('AI 操作',()=>{if(expanded){expanded=false;root.classList.remove('is-expanded');document.body.classList.toggle('board-modal-open',!!document.querySelector('.board-mount.is-expanded'));render();}askAI();},'outline'));
      topActions.append(btn(expanded?'退出放大':editable?'放大编辑':'放大查看',()=>{expanded=!expanded;root.classList.toggle('is-expanded',expanded);document.body.classList.toggle('board-modal-open',!!document.querySelector('.board-mount.is-expanded'));render();},'outline'));
      header.append(topActions);shell.append(header);
      if(editable){
        const setup=el('div','board-setup');
        const pitch=el('label','','球场'),pitchSel=el('select');pitchSel.setAttribute('aria-label','球场范围');[['full','全场'],['half','半场']].forEach(([v,t])=>{const o=el('option','',t);o.value=v;pitchSel.append(o);});pitchSel.value=board.pitch;pitchSel.addEventListener('change',()=>mutate(()=>board.pitch=pitchSel.value));pitch.append(pitchSel);
        const direction=el('label','','进攻方向'),dirSel=el('select');dirSel.setAttribute('aria-label','进攻方向');[['right','向右 →'],['left','← 向左']].forEach(([v,t])=>{const o=el('option','',t);o.value=v;dirSel.append(o);});dirSel.value=board.attack;dirSel.addEventListener('change',()=>mutate(()=>board.attack=dirSel.value));direction.append(dirSel);
        const preset=el('label','','阵型预设'),presetSel=el('select');presetSel.setAttribute('aria-label','阵型预设');[['','选择'],['5','5 人制'],['7','7 人制'],['11','11 人制']].forEach(([v,t])=>{const o=el('option','',t);o.value=v;presetSel.append(o);});preset.append(presetSel);
        const applyPreset=btn('套用',()=>{const count=Number(presetSel.value);if(!count){showStatus('请先选择阵型。');return;}if(!confirm('套用阵型会替换当前战术板，可以用撤销恢复。继续吗？'))return;mutate(()=>{const next=formation(count);Object.keys(board).forEach(k=>delete board[k]);Object.assign(board,next);selected=board.players[0].id;index=0;});});
        setup.append(pitch,direction,preset,applyPreset);const settings=el('details','board-settings');settings.append(el('summary','','球场和阵型设置'),setup);shell.append(settings);
      }
      const pitch=el('div','tactics-pitch');pitch.setAttribute('aria-label','二维足球场');
      const full='<rect x="3" y="4" width="94" height="62"/><path d="M50 4v62"/><circle cx="50" cy="35" r="9"/><circle cx="50" cy="35" r=".45" fill="currentColor"/><path d="M3 21h14v28H3M97 21H83v28h14M3 27h5v16H3M97 27h-5v16h5"/>';
      const half='<rect x="3" y="4" width="94" height="62"/><path d="M3 26a9 9 0 0 1 0 18M97 17H72v36h25M97 26H88v18h9"/><circle cx="83" cy="35" r=".45" fill="currentColor"/>';
      const mirror=board.pitch==='half'&&board.attack==='left'?' transform="translate(100 0) scale(-1 1)"':'';
      pitch.innerHTML='<svg class="pitch-lines" viewBox="0 0 100 70" preserveAspectRatio="none" aria-hidden="true"><g'+mirror+'>'+(board.pitch==='half'?half:full)+'</g></svg>';
      const ns='http://www.w3.org/2000/svg',routes=document.createElementNS(ns,'svg');routes.setAttribute('viewBox','0 0 100 100');routes.setAttribute('preserveAspectRatio','none');routes.classList.add('pitch-routes');pitch.append(routes);
      const markers=new Map();
      function svg(tag,attrs){const n=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,String(v)));return n;}
      function drawRoutes(){
        routes.replaceChildren();
        const defs=svg('defs',{}),arrow=svg('marker',{id:markerId,markerWidth:5,markerHeight:5,refX:4,refY:2.5,orient:'auto'});arrow.append(svg('path',{d:'M0,0 L5,2.5 L0,5 Z',fill:'#fff'}));defs.append(arrow);routes.append(defs);
        const frame=board.frames[index],next=board.frames[index+1];
        if(next)board.players.forEach(player=>{
          const a=frame.positions[player.id],b=next.positions[player.id],path=frame.paths[player.id]||{kind:player.type==='ball'?'pass':'run',via:[]};
          if(!a||!b||(dist(a,b)<1&&!(path.via||[]).length))return;
          const points=[a,...(path.via||[]),b].map(p=>p.join(',')).join(' ');
          const line=svg('polyline',{points,fill:'none',stroke:path.kind==='shot'?'#ffe075':'#fff','stroke-width':path.kind==='shot'?1.1:.8,opacity:.92,'marker-end':`url(#${markerId})`});
          if(['pass','shot'].includes(path.kind))line.setAttribute('stroke-dasharray','2 1.4');routes.append(line);
        });
        frame.marks.forEach(mark=>{
          const a=mark.start,b=mark.end;
          if(mark.kind==='zone')routes.append(svg('rect',{x:Math.min(a[0],b[0]),y:Math.min(a[1],b[1]),width:Math.abs(a[0]-b[0]),height:Math.abs(a[1]-b[1]),fill:'#ffdf6655',stroke:'#ffe075','stroke-width':.7,'stroke-dasharray':'2 1'}));
          else if(mark.kind==='text'){const t=svg('text',{x:a[0],y:a[1],fill:'#fff','font-size':'4','font-weight':'700'});t.textContent=mark.label;routes.append(t);}
          else {const line=svg('line',{x1:a[0],y1:a[1],x2:b[0],y2:b[1],stroke:'#ffe075','stroke-width':.9});if(mark.kind==='arrow')line.setAttribute('marker-end',`url(#${markerId})`);routes.append(line);}
          if(mark.kind!=='text'&&mark.label){const t=svg('text',{x:a[0],y:Math.max(4,a[1]-2),fill:'#fff','font-size':'3.2'});t.textContent=mark.label;routes.append(t);}
        });
        if(previewPoints&&previewPoints.length>1)routes.append(svg('polyline',{points:previewPoints.map(p=>p.join(',')).join(' '),fill:'none',stroke:'#ffe075','stroke-width':1,'stroke-dasharray':'2 1'}));
      }
      function paint(positions){board.players.forEach(p=>{const n=markers.get(p.id),xy=positions[p.id];if(n&&xy){n.style.left=xy[0]+'%';n.style.top=xy[1]+'%';}});}
      const loc=event=>{const r=pitch.getBoundingClientRect();return pct((event.clientX-r.left)/r.width*100,(event.clientY-r.top)/r.height*100);};
      function selectPlayer(player){selected=player.id;shell.querySelectorAll('.pitch-marker,.board-object').forEach(n=>n.classList.toggle('selected',n.dataset.object===selected));updateSelection();}
      function startGesture(event,player){
        if(!editable||animation!==null)return;
        if(player&&mode==='pass'&&selected&&player.id!==selected&&['home','away'].includes(player.type)){
          const passer=board.players.find(p=>p.id===selected);event.preventDefault();event.stopPropagation();
          if(passer)appendAction('pass',passer,board.frames[index].positions[player.id].slice(),[]);return;
        }
        if(player)selectPlayer(player);
        if(mode==='select'&&!player)return;
        event.preventDefault();event.stopPropagation();
        const actor=board.players.find(p=>p.id===selected);
        if(['run','dribble','pass','shot'].includes(mode)&&!actor){showStatus('请先选择球员或足球。');return;}
        const capture=event.currentTarget;capture.setPointerCapture(event.pointerId);
        const at=loc(event),start=player&&mode==='select'?board.frames[index].positions[player.id].slice():['run','dribble','pass','shot'].includes(mode)?board.frames[index].positions[actor.id].slice():at;
        gesture={pointer:event.pointerId,capture,actor,player,start,origin:at,points:[start],before:copy(board),moved:false};
        if(mode!=='select'){gesture.points.push(at);previewPoints=gesture.points.slice();drawRoutes();}
      }
      function moveGesture(event){
        if(!gesture||event.pointerId!==gesture.pointer)return;event.preventDefault();
        const at=loc(event);gesture.moved=gesture.moved||dist(gesture.origin,at)>1;
        if(mode==='select'&&gesture.player){board.frames[index].positions[gesture.player.id]=at;paint(board.frames[index].positions);drawRoutes();}
        else if(gesture.points.length<60&&(dist(gesture.points[gesture.points.length-1],at)>1)){gesture.points.push(at);previewPoints=gesture.points.slice();drawRoutes();}
      }
      function endGesture(event){
        if(!gesture||event.pointerId!==gesture.pointer)return;const g=gesture;gesture=null;previewPoints=null;
        if(event.type==='pointercancel'){replace(g.before);render();return;}
        const end=loc(event);
        if(mode==='select'){if(g.moved){record(g.before);render();}else drawRoutes();return;}
        if(['run','dribble','pass','shot'].includes(mode)){
          if(g.player&&!g.moved){drawRoutes();return;}
          if(dist(g.start,end)<2){drawRoutes();return;}
          const points=g.points.slice(1);if(!points.length||dist(points[points.length-1],end)>.5)points.push(end);
          const middle=points.slice(0,-1),via=[];let last=g.start;
          middle.forEach(p=>{if(dist(last,p)>=5&&via.length<10){via.push(p);last=p;}});
          appendAction(mode,g.actor,end,via);return;
        }
        const markMode=mode,markStart=g.start,markEnd=end;
        if(markMode!=='text'&&dist(markStart,markEnd)<2){drawRoutes();return;}
        const label=markMode==='text'?(shell.querySelector('.mark-text-input')?.value||'').trim():'';
        if(markMode==='text'&&!label){showStatus('先输入标注文字，再点球场。');drawRoutes();return;}
        if(board.frames[index].marks.length>=24){showStatus('当前动作最多 24 个标注。');drawRoutes();return;}
        const before=copy(board);board.frames[index].marks.push({id:ident('m'),kind:markMode,start:markStart,end:markEnd,label});mode='select';record(before);render();
      }
      pitch.addEventListener('pointerdown',event=>{if(event.target.closest('.pitch-marker'))return;startGesture(event,null);});
      pitch.addEventListener('pointermove',moveGesture);pitch.addEventListener('pointerup',endGesture);pitch.addEventListener('pointercancel',endGesture);
      board.players.forEach(player=>{
        const text=player.type==='ball'?'⚽':player.type==='cone'?'▲':player.label||(player.type==='home'?'我':'对');
        const marker=el('button','pitch-marker '+player.type+(selected===player.id&&editable?' selected':''),text);marker.type='button';marker.dataset.object=player.id;marker.title=nameOf(player);marker.setAttribute('aria-label',nameOf(player)+(editable?'，方向键可以移动':''));if(!editable)marker.tabIndex=-1;
        if(editable){
          marker.addEventListener('focus',()=>selectPlayer(player));marker.addEventListener('pointerdown',event=>startGesture(event,player));
          marker.addEventListener('pointermove',moveGesture);marker.addEventListener('pointerup',endGesture);marker.addEventListener('pointercancel',endGesture);
          marker.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;event.preventDefault();const before=copy(board),p=board.frames[index].positions[player.id];p[0]=clamp(p[0]+(event.key==='ArrowLeft'?-1:event.key==='ArrowRight'?1:0),0,100);p[1]=clamp(p[1]+(event.key==='ArrowUp'?-1:event.key==='ArrowDown'?1:0),0,100);paint(board.frames[index].positions);drawRoutes();record(before);});
        }
        markers.set(player.id,marker);pitch.append(marker);
      });
      shell.append(pitch,el('p','board-legend','实线：跑动或带球 · 虚线：传球或射门'));paint(board.frames[index].positions);drawRoutes();
      if(editable){
        const tools=el('div','board-mode-tools');
        [['select','移动'],['run','跑动'],['dribble','带球'],['pass','传球'],['shot','射门']].forEach(([key,label])=>{const b=btn(label,()=>{mode=key;render();},'board-mode'+(mode===key?' active':''));b.setAttribute('aria-pressed',String(mode===key));tools.append(b);});shell.append(tools);
        const more=el('details','board-settings'),extra=el('div','board-mode-tools');more.open=['arrow','line','zone','text'].includes(mode);more.append(el('summary','','标注工具'),extra);[['arrow','箭头'],['line','直线'],['zone','区域'],['text','文字']].forEach(([key,label])=>{const b=btn(label,()=>{mode=key;render();},'board-mode'+(mode===key?' active':''));b.setAttribute('aria-pressed',String(mode===key));extra.append(b);});shell.append(more);
        if(['run','dribble','pass','shot'].includes(mode)){const targetLabel=el('label','board-route-target','路线写入'),target=el('select');target.setAttribute('aria-label','路线写入方式');[['new','新建下一步'],['existing','修改已有的下一步']].forEach(([v,t])=>{const o=el('option','',t);o.value=v;target.append(o);});target.value=routeTarget;target.addEventListener('change',()=>routeTarget=target.value);targetLabel.append(target);shell.append(targetLabel);}
        if(mode==='text'){const text=el('input','mark-text-input');text.maxLength=60;text.placeholder='输入标注文字，再点球场';text.setAttribute('aria-label','标注文字');shell.append(text);}
        statusLine=el('p','board-hint',message[mode]);statusLine.setAttribute('role','status');shell.append(statusLine);
        const objects=el('div','board-objects');board.players.forEach(player=>{const b=btn(player.type==='ball'?'⚽':player.type==='cone'?'▲':player.label||player.id,()=>{selectPlayer(player);},'board-object '+player.type+(selected===player.id?' selected':''));b.dataset.object=player.id;b.setAttribute('aria-label','选中'+nameOf(player));objects.append(b);});shell.append(objects);
      }
      const transport=el('div','board-transport');
      const play=btn('▶ 播放',()=>{
        if(board.frames.length<2)return;
        if(animation!==null){stop();render();return;}
        let frame=index>=board.frames.length-1?0:index,started=null;play.textContent='■ 停止';shell.classList.add('playing');
        const tick=time=>{if(!root.isConnected){stop();return;}if(started===null)started=time;const a=board.frames[frame],b=board.frames[frame+1],ratio=Math.min(1,(time-started)/(a.duration*1000/speed)),positions={};board.players.forEach(p=>positions[p.id]=pathPoint(a.positions[p.id],b.positions[p.id],a.paths[p.id]?.via||[],ratio));paint(positions);playStatus.textContent=`播放中 · ${frame+1} → ${frame+2} / ${board.frames.length}`;
          if(ratio>=1){frame++;started=time;if(frame>=board.frames.length-1){if(loop){frame=0;}else{animation=null;index=board.frames.length-1;render();return;}}}animation=requestAnimationFrame(tick);};animation=requestAnimationFrame(tick);
      },'smallbtn');play.disabled=board.frames.length<2;transport.append(play);
      const playStatus=el('span','hint',`动作 ${index+1} / ${board.frames.length} · ${board.frames[index].label||'未命名'}`);playStatus.setAttribute('role','status');transport.append(playStatus);
      const speedSel=el('select','board-speed');speedSel.setAttribute('aria-label','播放速度');[['0.5','0.5×'],['1','1×'],['2','2×']].forEach(([v,t])=>{const o=el('option','',t);o.value=v;speedSel.append(o);});speedSel.value=String(speed);speedSel.addEventListener('change',()=>speed=Number(speedSel.value));transport.append(speedSel);
      const loopLabel=el('label','board-loop'),loopInput=el('input');loopInput.type='checkbox';loopInput.checked=loop;loopInput.addEventListener('change',()=>loop=loopInput.checked);loopLabel.append(loopInput,document.createTextNode('循环'));transport.append(loopLabel);shell.append(transport);
      const frames=el('div','board-frames');board.frames.forEach((frame,i)=>{const b=btn(`${i+1} ${frame.label||'未命名'}`,()=>{index=i;render();},'frame-button'+(i===index?' active':''));b.setAttribute('aria-label',`查看动作 ${i+1} ${frame.label}`);b.setAttribute('aria-pressed',String(i===index));frames.append(b);});shell.append(frames);
      let selectionWrap;
      function updateSelection(){
        if(!selectionWrap)return;const p=board.players.find(x=>x.id===selected);selectionWrap.replaceChildren();if(!p)return;
        selectionWrap.append(el('span','hint','选中：'+nameOf(p)));
        if(p.type!=='ball'){const input=el('input');input.value=p.label;input.maxLength=8;input.setAttribute('aria-label','球员或标志桶标记');let before=null;input.addEventListener('focus',()=>before=copy(board));input.addEventListener('input',()=>{p.label=input.value;const marker=markers.get(p.id);if(marker&&p.type!=='cone')marker.textContent=p.label||'•';changed();});input.addEventListener('change',()=>{if(before&&JSON.stringify(before)!==JSON.stringify(board)){record(before);render();}before=null;});selectionWrap.append(input);}
        const remove=btn('移除选中',()=>{if(board.players.length<=1)return;mutate(()=>{board.players=board.players.filter(x=>x.id!==selected);board.frames.forEach(f=>{delete f.positions[selected];delete f.paths[selected];});selected=board.players[0].id;});});remove.disabled=board.players.length<=1;selectionWrap.append(remove);
      }
      if(editable){
        const frame=board.frames[index],fields=el('div','board-frame-edit');
        const label=el('label','','动作说明'),name=el('input');name.value=frame.label;name.maxLength=80;let beforeLabel=null;name.addEventListener('focus',()=>beforeLabel=copy(board));name.addEventListener('input',()=>{frame.label=name.value;changed();});name.addEventListener('change',()=>{if(beforeLabel&&JSON.stringify(beforeLabel)!==JSON.stringify(board)){record(beforeLabel);render();}beforeLabel=null;});label.append(name);
        const dur=el('label','','到下一步（秒）'),n=el('input');n.type='number';n.min='.5';n.max='15';n.step='.5';n.value=frame.duration;n.addEventListener('change',()=>mutate(()=>{frame.duration=clamp(Number(n.value)||2,.5,15);}));dur.append(n);fields.append(label,dur);shell.append(fields);
        const actions=el('div','board-tools');
        const earlier=btn('动作前移',()=>mutate(()=>{[board.frames[index-1],board.frames[index]]=[board.frames[index],board.frames[index-1]];index--;}));earlier.disabled=index===0;
        const later=btn('动作后移',()=>mutate(()=>{[board.frames[index],board.frames[index+1]]=[board.frames[index+1],board.frames[index]];index++;}));later.disabled=index===board.frames.length-1;
        const add=btn('新增下一步',()=>mutate(()=>{const next=copy(board.frames[index]);next.label='新动作';board.frames.splice(index+1,0,next);index++;}));add.disabled=board.frames.length>=16;
        const remove=btn('删除此动作',()=>mutate(()=>{board.frames.splice(index,1);index=Math.min(index,board.frames.length-1);}));remove.disabled=board.frames.length<=1;
        const undo=btn('撤销',()=>{if(!history.undo.length)return;history.redo.push(copy(board));replace(history.undo.pop());changed();render();});undo.disabled=!history.undo.length;
        const redo=btn('重做',()=>{if(!history.redo.length)return;history.undo.push(copy(board));replace(history.redo.pop());changed();render();});redo.disabled=!history.redo.length;
        actions.append(add,undo,redo);shell.append(actions);const ordering=el('details','board-settings'),orderActions=el('div','board-tools');orderActions.append(earlier,later,remove);ordering.append(el('summary','','调整动作顺序或删除'),orderActions);shell.append(ordering);
        const addObjects=el('div','board-tools');[['home','+ 我队'],['away','+ 对方'],['ball','+ 足球'],['cone','+ 标志桶']].forEach(([type,text])=>{const add=btn(text,()=>mutate(()=>{const id=ident('p'),count=board.players.filter(p=>p.type===type).length+1;const p={id,type,label:type==='ball'?'':String(count)};board.players.push(p);board.frames.forEach(f=>f.positions[id]=[type==='away'?72:30,65]);selected=id;}));add.disabled=board.players.length>=32;addObjects.append(add);});shell.append(addObjects);
        selectionWrap=el('div','board-selected');shell.append(selectionWrap);updateSelection();
        if(frame.marks.length){const marks=el('div','board-mark-list');marks.append(el('span','hint','当前标注'));frame.marks.forEach(mark=>marks.append(btn('删除'+({arrow:'箭头',line:'直线',zone:'区域',text:'文字'}[mark.kind])+(mark.label?' '+mark.label:''),()=>mutate(()=>{frame.marks=frame.marks.filter(x=>x.id!==mark.id);}),'outline')));shell.append(marks);}
      }
      root.append(shell);
    }
    root.addEventListener('keydown',event=>{if(event.key==='Escape'&&expanded){expanded=false;root.classList.remove('is-expanded');document.body.classList.toggle('board-modal-open',!!document.querySelector('.board-mount.is-expanded'));render();}});
    render();return {render,stop,getContext:()=>({frame:index+1,object_id:selected||null})};
  }
  window.TeamBoard={mount,fresh,formation};
})();
