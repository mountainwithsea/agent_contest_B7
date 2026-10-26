function httpReason(code){return ({401:'密钥无效或已失效（HTTP 401）',402:'账户余额或额度不足（HTTP 402）',403:'当前密钥没有访问权限（HTTP 403）',404:'接口地址或模型名称不正确（HTTP 404）',429:'请求限流或额度不足，请稍后重试（HTTP 429）'})[code]||'服务返回 HTTP '+code}
async function checkConnection(group,values,fetcher=fetch){
 if(group==='services'){
  const results=await Promise.all(['https://anystyle.io/','https://grobidorg-grobid.hf.space/api/isalive'].map(async url=>{try{const r=await fetcher(url,{signal:AbortSignal.timeout(18000)});return `${new URL(url).hostname}：${r.ok?'可连接':'HTTP '+r.status}`}catch{return new URL(url).hostname+'：连接失败'}}));return results.join('\n');
 }
 if(group==='openalex'){
  if(!values.openalex.key)throw Error('请先填写 OpenAlex API Key');
  const r=await fetcher('https://api.openalex.org/works?per-page=1',{headers:{Authorization:'Bearer '+values.openalex.key},signal:AbortSignal.timeout(20000)});
  if(!r.ok)throw Error(httpReason(r.status));return 'OpenAlex 连接成功';
 }
 if(!['text','vision'].includes(group))throw Error('未知服务');const c=values[group];
 if(!c.key)throw Error('请先填写 API Key');
 const text='只回复 OK。';
 const tiny='iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAAN0lEQVR4nO3RwQ0AMAjDwJT9d05HMB9+vgGCZF7bXJrT9XhgwR8gEyETIRMhEyETIRMhEyEThXzH8QM9OMM6fAAAAABJRU5ErkJggg==';
 const content=group==='vision'?[{type:'text',text},{type:'image_url',image_url:{url:'data:image/png;base64,'+tiny}}]:text;
 const r=await fetcher(c.base+'/chat/completions',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+c.key},body:JSON.stringify({model:c.model,messages:[{role:'user',content}],max_tokens:64,stream:group==='vision',...(group==='vision'?{modalities:['text']}:{} )}),signal:AbortSignal.timeout(45000)});
 if(!r.ok)throw Error(httpReason(r.status));
 const raw=await r.text();let valid=false;
 if(group==='vision'&&raw.includes('data:')){
  for(const line of raw.split('\n')){if(!line.startsWith('data:')||line.slice(5).trim()==='[DONE]')continue;const event=JSON.parse(line.slice(5));if(event.error)throw Error('模型在流式响应中报告错误，请检查配置');if(event.choices?.length)valid=true}
 }else valid=!!JSON.parse(raw).choices?.length;
 if(!valid)throw Error('接口返回成功，但没有模型结果；请检查模型名称和接口格式');
 return group==='vision'?'图像模型已接受图片请求':'文本模型调用成功';
}
module.exports={checkConnection,httpReason};
