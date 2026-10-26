const $=s=>document.querySelector(s),api=window.workbench;let state=null,tab='home';const cleared=new Set();
function show(name){
 if(['reference'].includes(name)&&!state?.services?.urls[name]){name='home';$('#boot-error').hidden=false;$('#boot-error').textContent=state?.services?.error||state?.error||'正在启动本机服务，请稍候…'}
 tab=name;for(const id of ['home','settings','help'])$('#'+id).hidden=id!==name;
 $('#workspace').hidden=!['reference'].includes(name);
 for(const id of ['reference'])$('#'+id+'-frame').hidden=id!==name;
 document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));
}
function render(next){
 state=next;const ready=state.services?.ready;
 $('#connection').textContent=state.error||state.services?.error?'服务需要检查':ready?'本机服务已就绪':'正在启动…';
 $('#version').textContent=state.version||'';
 $('#first-run').hidden=!!state.settings?.text.hasKey;
 if(state.settings){for(const group of ['text','vision']){if(document.activeElement?.id!==group+'-base')$('#'+group+'-base').value=state.settings[group].base;if(document.activeElement?.id!==group+'-model')$('#'+group+'-model').value=state.settings[group].model;}
  for(const group of ['text','vision','openalex'])$('#'+group+'-key').placeholder=state.settings[group].hasKey?'已保存 · 留空则保留':'填写自己的 API Key';
  $('#fake-dns').checked=state.settings.fakeDns;
 }
 for(const group of ['reference']){const frame=$('#'+group+'-frame'),src=state.services?.urls[group];if(src&&frame.getAttribute('src')!==src+'/')frame.src=src+'/';}
 const error=state.error||state.services?.error;$('#boot-error').hidden=!error;if(error)$('#boot-error').textContent=error;
}
function patch(){const p={fakeDns:$('#fake-dns').checked};for(const group of ['text','vision','openalex']){p[group]={key:$('#'+group+'-key').value,clearKey:cleared.has(group)};if(group!=='openalex'){p[group].base=$('#'+group+'-base').value;p[group].model=$('#'+group+'-model').value}}return p}
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>show(b.dataset.tab));$('#brand').onclick=()=>show('home');
document.querySelectorAll('[data-clear]').forEach(b=>b.onclick=()=>{const g=b.dataset.clear;cleared.add(g);$('#'+g+'-key').value='';$('#'+g+'-key').placeholder='保存后将清除';});
for(const group of ['text','vision','openalex'])$('#'+group+'-key').oninput=()=>cleared.delete(group);
document.querySelectorAll('[data-test]').forEach(b=>b.onclick=async()=>{const target=$('#'+b.dataset.test+'-test');target.classList.remove('error');target.textContent='正在检测…';b.disabled=true;try{target.textContent=await api.test(b.dataset.test,patch())}catch(e){target.classList.add('error');target.textContent=e.message}finally{b.disabled=false}});
$('#settings-form').onsubmit=async e=>{e.preventDefault();const button=e.submitter;button.disabled=true;$('#save-result').textContent='正在保存并应用…';try{const next=await api.save(patch());cleared.clear();for(const g of ['text','vision','openalex'])$('#'+g+'-key').value='';render(next);$('#save-result').textContent='已保存，文献核验已应用新设置'}catch(e){$('#save-result').textContent=e.message}finally{button.disabled=false}};
$('#restart').onclick=async()=>{try{render(await api.restart());$('#services-test').textContent='本机服务已重启'}catch(e){$('#services-test').textContent=e.message}};
document.querySelectorAll('[data-folder]').forEach(b=>b.onclick=()=>api.folder(b.dataset.folder).catch(e=>$('#help-result').textContent=e.message));
$('#update').onclick=()=>api.update().catch(e=>$('#help-result').textContent=e.message);
api.onStatus(render);api.state().then(render).catch(e=>{$('#boot-error').hidden=false;$('#boot-error').textContent=e.message});
