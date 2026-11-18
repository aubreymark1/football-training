(()=>{
  const login=document.getElementById('passkey-login');
  const panel=document.getElementById('passkey-panel');
  if(!login&&!panel)return;
  const decode=s=>Uint8Array.from(atob(s.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-s.length%4)%4)),c=>c.charCodeAt(0));
  const encode=b=>{if(!b)return null;let s='';new Uint8Array(b).forEach(v=>s+=String.fromCharCode(v));return btoa(s).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'')};
  const convert=(options,registration)=>{
    options.challenge=decode(options.challenge);
    if(registration){options.user.id=decode(options.user.id);(options.excludeCredentials||[]).forEach(c=>c.id=decode(c.id))}
    else (options.allowCredentials||[]).forEach(c=>c.id=decode(c.id));
    return options;
  };
  const serialize=credential=>{
    const r=credential.response, response={clientDataJSON:encode(r.clientDataJSON)};
    if(r.attestationObject){response.attestationObject=encode(r.attestationObject);if(r.getTransports)response.transports=r.getTransports()}
    else{response.authenticatorData=encode(r.authenticatorData);response.signature=encode(r.signature);response.userHandle=encode(r.userHandle)}
    return {id:credential.id,rawId:encode(credential.rawId),type:credential.type,response,clientExtensionResults:credential.getClientExtensionResults()};
  };
  const post=async(url,fields)=>{
    const form=new FormData();Object.entries(fields).forEach(([key,value])=>form.set(key,value));
    const response=await fetch(url,{method:'POST',body:form,credentials:'same-origin'});
    const data=await response.json();if(!response.ok)throw new Error(data.error||'操作失败，请重试。');return data;
  };
  const support=()=>window.isSecureContext&&window.PublicKeyCredential&&navigator.credentials;
  const showError=(error,status)=>{status.textContent=error.name==='NotAllowedError'?'已取消操作或验证超时，请重试。':(error.message||'操作失败，请重试。')};
  if(login){
    const status=document.getElementById('passkey-login-status');
    if(!support()){login.hidden=true;status.textContent='当前浏览器不支持通行密钥，可继续使用密码登录。'}
    else login.addEventListener('click',async()=>{login.disabled=true;status.textContent='请在设备上完成身份验证。';try{
      const options=await post(login.dataset.options,{csrf:login.dataset.csrf});
      const cred=await navigator.credentials.get({publicKey:convert(options,false)});
      await post(login.dataset.finish,{csrf:login.dataset.csrf,credential:JSON.stringify(serialize(cred))});
      window.location.assign(login.dataset.home);
    }catch(error){showError(error,status);login.disabled=false}});
  }
  if(panel){
    const form=panel.querySelector('#passkey-add-form'),button=form.querySelector('button'),status=panel.querySelector('#passkey-status');
    if(!support()){button.disabled=true;status.textContent='当前浏览器不支持通行密钥，请使用较新版本的浏览器。'}
    form.addEventListener('submit',async event=>{event.preventDefault();if(!support())return;button.disabled=true;status.textContent='请在设备上完成身份验证。';
      try{const password=form.elements.password.value,label=form.elements.label.value;
        const options=await post(form.dataset.options,{csrf:form.elements.csrf.value,password});
        form.elements.password.value='';
        const cred=await navigator.credentials.create({publicKey:convert(options,true)});
        await post(form.dataset.finish,{csrf:form.elements.csrf.value,label,credential:JSON.stringify(serialize(cred))});
        window.location.reload();
      }catch(error){showError(error,status);button.disabled=false}
    });
    panel.querySelectorAll('form[data-delete-url]').forEach(remove=>remove.addEventListener('submit',async event=>{
      event.preventDefault();if(!window.confirm('移除此通行密钥？'))return;
      const b=remove.querySelector('button');b.disabled=true;
      try{await post(remove.dataset.deleteUrl,{csrf:remove.elements.csrf.value,password:remove.elements.password.value});window.location.reload()}
      catch(error){showError(error,status);b.disabled=false}
    }));
  }
})();
