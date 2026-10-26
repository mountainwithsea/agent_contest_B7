const {spawn}=require('node:child_process');const fs=require('node:fs');const path=require('node:path');const net=require('node:net');
const {makeEnvironment}=require('./settings.cjs');
const pause=ms=>new Promise(r=>setTimeout(r,ms));
function freePort(){return new Promise((resolve,reject)=>{const s=net.createServer();s.unref();s.on('error',reject);s.listen(0,'127.0.0.1',()=>{const port=s.address().port;s.close(()=>resolve(port))})})}
async function request(url,options={}){const r=await fetch(url,{...options,signal:AbortSignal.timeout(options.timeout||4000)});if(!r.ok)throw Error('本机服务返回 HTTP '+r.status);return r.json()}
class Services{
 constructor(payload,userDir,notify=()=>{}){this.payload=payload;this.userDir=userDir;this.notify=notify;this.children=new Map();this.urls={};this.stopping=false;this.error=null}
 async start(settings){
  this.settings=settings;this.error=null;this.stopping=false;
  const env={...makeEnvironment(settings,this.payload,this.userDir),B7_DESKTOP_PARENT:String(process.pid)};fs.mkdirSync(path.join(this.userDir,'logs'),{recursive:true});
  try{
   for(const app of ['reference']){
    const port=await freePort(),folder=path.join(this.payload,'reference-checker');
    const python=path.join(this.payload,'runtime',app,'python.exe');
    const args=['-B','-X','utf8','-m','ref_app','--port',String(port),...(settings.fakeDns?['--fake-dns']:[])];
    const log=fs.openSync(path.join(this.userDir,'logs',app+'.log'),'a');
    let child;try{child=spawn(python,args,{cwd:folder,env,windowsHide:true,stdio:['ignore',log,log]})}finally{fs.closeSync(log)}
    child.on('error',()=>{this.error='后台启动失败，请在帮助中打开日志目录检查运行环境';this.notify()});
    child.on('exit',()=>{if(!this.stopping){this.error='后台已停止，请在设置中重新启动服务';this.notify()}});
    this.children.set(app,child);const url='http://127.0.0.1:'+port;
    let ready=false;
    for(let i=0;i<120;i++){
     if(child.exitCode!==null||this.error)throw Error(this.error||'后台未能启动');
     try{await request(url+'/api/jobs',{timeout:1000});ready=true;break}catch{await pause(250)}
    }
    if(!ready)throw Error('后台启动超时，请打开日志目录查看');this.urls[app]=url;this.notify();
   }
  }catch(e){await this.stop();this.error=e.message;throw e}
 }
 async active(){
  const results=[];
  for(const [app,url] of Object.entries(this.urls)){
   try{for(const task of await request(url+'/api/jobs')){if(['running','queued'].includes(task.state))results.push({app,id:task.id})}}
   catch{if(this.children.get(app)?.exitCode===null)throw Error('暂时无法读取运行状态，请稍后重试')}
  }
  return results;
 }
 async stop(){
  this.stopping=true;
  for(const [app,url] of Object.entries(this.urls)){
   try{for(const task of await request(url+'/api/jobs')){if(!['running','queued'].includes(task.state))continue;
    const endpoint=`/api/jobs/${task.id}/cancel`;
    await request(url+endpoint,{method:'POST',headers:{Origin:url,'X-Ref-App':'1','Content-Type':'application/json'},body:'{}',timeout:15000});
   }}catch{}
  }
  const children=[...this.children.values()];
  for(const child of children)if(child.exitCode===null){child.kill();}
  await Promise.all(children.map(child=>child.exitCode!==null?null:new Promise(resolve=>{child.once('exit',resolve);setTimeout(resolve,4000).unref()})));
  this.children.clear();this.urls={};this.notify();
 }
 status(){return {urls:{...this.urls},ready:!!this.urls.reference,error:this.error}}
}
module.exports={Services,request,freePort};
