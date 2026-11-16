import React,{useState,useEffect,useRef} from 'react';
import {createRoot} from 'react-dom/client';
import {AssistantRuntimeProvider,useLocalRuntime,ThreadPrimitive,MessagePrimitive,ComposerPrimitive} from '@assistant-ui/react';
import {Button} from '@heroui/react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {ArrowUp,Square,Plus,Paperclip,Trash2,MessageSquare,Lightbulb} from 'lucide-react';
import '@heroui/styles';
import './chat.css';
const el=document.getElementById('assistant-root');
function emit(detail){window.dispatchEvent(new CustomEvent('team-action',{detail}))}
const makeAdapter=(threadId,thinkingRef,onComplete,onRunState)=>({async *run({messages,abortSignal}) {
 onRunState(true);emit({type:'start',deep:thinkingRef.current});
 const readable=messages.map(m=>({role:m.role,content:m.content.filter(p=>p.type==='text').map(p=>p.text).join('\n')})).filter(m=>['user','assistant'].includes(m.role)&&m.content);
 const latest=readable.pop(); const body=new FormData();body.set('csrf',el.dataset.csrf);body.set('message',latest.content);body.set('history',JSON.stringify(readable.slice(-12).map(m=>({...m,content:m.content.slice(0,3000)}))));body.set('thread_id',threadId);body.set('deep_thinking',thinkingRef.current?'1':'0');
 let accumulated='',sources=[];
 try{
  const mayBeAction=/(?:添加|新增|增加|加个|加一个|生成|创建|建立|新建|发布|制定|设置|上架|删除|取消|下架|移除|去掉|撤销|撤下|add|create|remove|delete)/i.test(latest.content) && /(?:任务|训练计划|礼品|奖品|奖励|task|reward|gift)/i.test(latest.content);
  if(el.dataset.admin==='true' && mayBeAction){
   const check=new FormData();check.set('csrf',el.dataset.csrf);check.set('message',latest.content);check.set('thread_id',threadId);check.set('deep_thinking',thinkingRef.current?'1':'0');
   const prepared=await fetch(el.dataset.prepare,{method:'POST',body:check,signal:abortSignal,credentials:'same-origin'});const planned=await prepared.json();
   if(!prepared.ok)throw Error(planned.error||'操作识别暂时不可用。');
   if(planned.action){emit(planned.action);onComplete();yield {content:[{type:'text',text:'请核对下面的操作。'}]};return;}
  }
  const response=await fetch(el.dataset.endpoint,{method:'POST',body,signal:abortSignal,credentials:'same-origin'});if(!response.ok||!response.body)throw Error('暂时无法获取回复，请稍后重试。');
  const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='',done=false;
  while(!done){const chunk=await reader.read();done=chunk.done;buffer+=decoder.decode(chunk.value||new Uint8Array(),{stream:!done});const frames=buffer.split('\n\n');buffer=frames.pop();for(const frame of frames){for(const line of frame.split('\n')){if(!line.startsWith('data:'))continue;const data=JSON.parse(line.slice(5).trim());if(data.error)throw Error(data.error);if(data.sources)sources=data.sources;if(data.status)emit({type:'progress',message:data.status});if(data.text){accumulated+=data.text;yield {content:[{type:'text',text:accumulated}]};}}}}
  if(!accumulated)throw Error('没有收到回复，请重试。');
  if(sources.length){accumulated+=sourceMarkdown(sources);yield {content:[{type:'text',text:accumulated}]};}
 }catch(e){if(e.name==='AbortError')throw e;yield {content:[{type:'text',text:accumulated+(accumulated?'\n\n':'')+(e.message||'回复中断，请重试。')}]};}finally{onRunState(false);onComplete()}
}});
function sourceMarkdown(sources){const format=items=>items.map((s,i)=>`> [${String(s.title||('来源 '+(i+1))).replace(/[\[\]\n\r]/g,' ')}](${encodeURI(s.url).replace(/[()]/g,c=>c==='('? '%28':'%29')})`).join('\n\n');const valid=sources.filter(s=>/^https?:\/\//i.test(s.url));const refs=valid.filter(s=>s.kind!=='video'),videos=valid.filter(s=>s.kind==='video');return (refs.length?'\n\n**参考资料**\n'+format(refs):'')+(videos.length?'\n\n**相关视频**\n'+format(videos):'')}
function MarkdownText({text}){return <div className="chat-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown></div>}
function UserMessage(){return <MessagePrimitive.Root className="chat-message chat-user"><div className="chat-bubble"><MessagePrimitive.Parts/></div></MessagePrimitive.Root>}
function AssistantMessage(){return <MessagePrimitive.Root className="chat-message chat-assistant"><div className="chat-avatar">AI</div><div className="chat-bubble"><MessagePrimitive.Parts components={{Text:MarkdownText}}/><MessagePrimitive.Error/></div></MessagePrimitive.Root>}
function Chat({thread,initial,onComplete,onRunState}){const thinkingRef=useRef(false);const [deepThinking,setDeepThinking]=useState(false);const [progress,setProgress]=useState('正在分析');const adapter=React.useMemo(()=>makeAdapter(thread.id,thinkingRef,onComplete,onRunState),[thread.id,onComplete,onRunState]);const runtime=useLocalRuntime(adapter,{initialMessages:initial});const [action,setAction]=useState(null);const [status,setStatus]=useState('');const [busy,setBusy]=useState(false);useEffect(()=>{const listener=e=>{if(e.detail.type==='start'){setProgress(e.detail.deep?'深度思考中':'正在分析');setAction(null);setStatus('');return}if(e.detail.type==='progress'){setProgress(e.detail.message);return}setAction(e.detail);setStatus('')};window.addEventListener('team-action',listener);return()=>window.removeEventListener('team-action',listener)},[]);
 async function execute(){setBusy(true);try{const b=new FormData();b.set('csrf',el.dataset.csrf);b.set('token',action.token);const r=await fetch(el.dataset.execute,{method:'POST',body:b,credentials:'same-origin'});const d=await r.json();setStatus(r.ok?'已完成。':d.error||'操作失败。');if(r.ok)setAction(null)}catch{setStatus('网络连接失败，请重试。')}finally{setBusy(false)}}
 return <AssistantRuntimeProvider runtime={runtime}><div className="chat-header"><span>{thread.title}</span></div><ThreadPrimitive.Root className="chat-shell"><ThreadPrimitive.Viewport className="chat-viewport"><ThreadPrimitive.Empty><div className="chat-welcome"><h2>有什么可以帮你？</h2><p>可以询问训练安排和球队任务。</p></div></ThreadPrimitive.Empty><ThreadPrimitive.Messages components={{UserMessage,AssistantMessage}}/><ThreadPrimitive.If running><div className="chat-thinking" role="status"><span></span><span></span><span></span><small>{progress}</small></div></ThreadPrimitive.If>{action&&<div className="action-card"><strong>确认操作</strong><p>{action.label}</p><div><button disabled={busy} onClick={execute}>确认</button><button disabled={busy} onClick={()=>setAction(null)}>取消</button></div></div>}{status&&<p role="status" className="action-status">{status}</p>}</ThreadPrimitive.Viewport><ComposerPrimitive.Root className="chat-composer"><ComposerPrimitive.Input className="chat-input" placeholder="输入问题或操作" aria-label="输入问题或操作" rows={2}/><div className="chat-actions"><div className="chat-tools"><a href={el.dataset.submitUrl}><Paperclip size={16}/> 提交记录</a><button type="button" className={deepThinking?"search-toggle selected":"search-toggle"} aria-pressed={deepThinking} onClick={()=>{thinkingRef.current=!deepThinking;setDeepThinking(!deepThinking)}}><Lightbulb size={16}/> 深度思考</button></div><ThreadPrimitive.If running><ComposerPrimitive.Cancel asChild><Button className="chat-send" aria-label="停止回复"><Square size={15}/></Button></ComposerPrimitive.Cancel></ThreadPrimitive.If><ThreadPrimitive.If running={false}><ComposerPrimitive.Send asChild><Button className="chat-send" aria-label="发送"><ArrowUp size={18}/></Button></ComposerPrimitive.Send></ThreadPrimitive.If></div></ComposerPrimitive.Root><p className="chat-footnote">AI 可能出错，请核对重要信息。</p></ThreadPrimitive.Root></AssistantRuntimeProvider>}
function Shell(){
 const [threads,setThreads]=useState([]),[selected,setSelected]=useState(null),[initial,setInitial]=useState([]),[loading,setLoading]=useState(true),[running,setRunning]=useState(false),[notice,setNotice]=useState(''),[deleting,setDeleting]=useState([]);
 const selectedRef=useRef(selected),selectionIntent=useRef(0);
 useEffect(()=>{selectedRef.current=selected},[selected]);
 const threadUrl=id=>el.dataset.threads+'/'+encodeURIComponent(id);
 const refresh=React.useCallback(async()=>{const r=await fetch(el.dataset.threads,{credentials:'same-origin'});if(!r.ok)throw Error('无法读取对话');const d=await r.json();setThreads(d.threads);return d.threads},[]);
 const open=async t=>{selectionIntent.current+=1;setLoading(true);try{const r=await fetch(threadUrl(t.id)+'/messages',{credentials:'same-origin'});if(!r.ok)throw Error('无法读取对话');const d=await r.json();setInitial(d.messages.map(m=>({id:m.id,role:m.role,content:[{type:'text',text:m.content+(m.role==='assistant'?sourceMarkdown(m.sources||[]):'')}]})));setSelected(t);setNotice('')}catch(e){setNotice(e.message)}finally{setLoading(false)}};
 const create=async()=>{selectionIntent.current+=1;setLoading(true);try{const b=new FormData();b.set('csrf',el.dataset.csrf);const r=await fetch(el.dataset.threads,{method:'POST',body:b,credentials:'same-origin'});if(!r.ok)throw Error('无法新建对话');const d=await r.json();setInitial([]);setSelected(d.thread);await refresh();setNotice('')}catch(e){setNotice(e.message)}finally{setLoading(false)}};
 const remove=async t=>{
  if(!window.confirm('删除这段对话？删除后无法恢复。'))return;
  const selectionAtStart=selectionIntent.current;
  setDeleting(ids=>[...ids,t.id]);
  try{
   const b=new FormData();b.set('csrf',el.dataset.csrf);
   const r=await fetch(threadUrl(t.id)+'/delete',{method:'POST',body:b,credentials:'same-origin'});
   if(!r.ok)throw Error('删除失败');
   const remaining=await refresh();
   if(selectedRef.current?.id===t.id && selectionIntent.current===selectionAtStart){
    if(remaining.length)await open(remaining[0]);
    else{setSelected(null);setInitial([])}
   }
   setNotice('对话已删除');
  }catch(e){setNotice(e.message)}
  finally{setDeleting(ids=>ids.filter(id=>id!==t.id))}
 };
 useEffect(()=>{let alive=true;refresh().then(list=>{if(!alive)return;if(list.length)open(list[0]);else setLoading(false)}).catch(()=>{if(alive){setNotice('无法读取对话');setLoading(false)}});return()=>{alive=false}},[refresh]);
 const completed=React.useCallback(()=>{refresh().catch(()=>{})},[refresh]);
 return <div className="assistant-layout"><aside className="conversation-panel"><div className="conversation-heading"><strong>对话</strong><button onClick={create} disabled={loading||running}><Plus size={16}/> 新对话</button></div><div className="conversation-list">{threads.map(t=><div key={t.id} className={selected?.id===t.id?'conversation-row active':'conversation-row'}><button className="conversation-open" disabled={loading||running||deleting.includes(t.id)} onClick={()=>open(t)}><MessageSquare size={15}/><span>{t.title}</span></button><button className="conversation-delete" disabled={loading||running||deleting.includes(t.id)} aria-label={'删除对话 '+t.title} onClick={()=>remove(t)}><Trash2 size={15}/></button></div>)}</div></aside><section className="conversation-main">{notice&&<p className="chat-notice" role="status">{notice}</p>}{loading?<p className="chat-loading">加载中</p>:selected?<Chat key={selected.id} thread={selected} initial={initial} onComplete={completed} onRunState={setRunning}/>:<div className="chat-start"><h2>球队助手</h2><p>开始一段对话，询问训练和球队情况</p><button onClick={create}>开始对话</button></div>}</section></div>
}
createRoot(el).render(<Shell/>);
