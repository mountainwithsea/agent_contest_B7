const fs=require('node:fs');const path=require('node:path');
const DEFAULTS={text:{base:'https://api.deepseek.com',model:'deepseek-flash',key:''},vision:{base:'https://dashscope.aliyuncs.com/compatible-mode/v1',model:'qwen3.8-omni-flash',key:''},openalex:{key:''},fakeDns:false};
function validateBase(value){
 const raw=String(value).trim().replace(/\/+$/,'');let u;
 try{u=new URL(raw)}catch{throw Error('请输入完整的 HTTPS API 地址')}
 if(u.protocol!=='https:'||u.username||u.password||u.search||u.hash)throw Error('API 地址须使用 HTTPS，且不能包含密钥、用户名或查询参数');
 return raw;
}
class Settings{
 constructor(dir,crypto){
  this.file=path.join(dir,'settings.json');this.crypto=crypto;fs.mkdirSync(dir,{recursive:true});
  this.data=structuredClone(DEFAULTS);
  if(fs.existsSync(this.file)){
   try{const saved=JSON.parse(fs.readFileSync(this.file,'utf8'));this.data=JSON.parse(crypto.decryptString(Buffer.from(saved.sealed,'base64')))}
   catch{throw Error('无法解密本机设置。请使用原 Windows 账户打开，或从数据目录备份并移走 settings.json 后重新配置。')}
  }
 }
 public(){return {...this.data,text:{base:this.data.text.base,model:this.data.text.model,hasKey:!!this.data.text.key},vision:{base:this.data.vision.base,model:this.data.vision.model,hasKey:!!this.data.vision.key},openalex:{hasKey:!!this.data.openalex.key}}}
 async values(){return structuredClone(this.data)}
 merge(patch){
  const next=structuredClone(this.data);
  for(const group of ['text','vision','openalex']){
   const p=patch[group]||{};
   if(group!=='openalex'){
    if(p.base!==undefined)next[group].base=validateBase(p.base);
    if(p.model!==undefined){if(typeof p.model!=='string'||!p.model.trim()||p.model.length>200)throw Error('请填写有效的模型名称');next[group].model=p.model.trim()}
   }
   if(p.clearKey)next[group].key='';else if(typeof p.key==='string'&&p.key.trim()){
    if(p.key.length>4000||/[\r\n]/.test(p.key))throw Error('API Key 格式不正确');next[group].key=p.key.trim();
   }
  }
  if(patch.fakeDns!==undefined)next.fakeDns=patch.fakeDns===true;
  return next;
 }
 async save(patch){
  const next=this.merge(patch);
  if(!this.crypto.isEncryptionAvailable())throw Error('Windows 密钥加密不可用，未保存设置');
  const sealed=this.crypto.encryptString(JSON.stringify(next)).toString('base64');
  const tmp=this.file+'.tmp';await fs.promises.writeFile(tmp,JSON.stringify({schema:1,sealed}),'utf8');
  const start=Date.now();
  for(;;){try{await fs.promises.rename(tmp,this.file);break}catch(e){if(!['EACCES','EPERM','EBUSY'].includes(e.code)||Date.now()-start>2000)throw e;await new Promise(r=>setTimeout(r,40))}}
  this.data=next;return this.public();
 }
}
function makeEnvironment(settings,payload,userDir,base=process.env){
 const env={...base};
 for(const k of Object.keys(env))if(/^(B7_|LLM_|DEEPSEEK_|OPENALEX_|SEMANTIC_|ANYSTYLE_|GROBID_|REFERENCE_|PYTHON)/.test(k))delete env[k];
 delete env.NODE_OPTIONS;delete env.ELECTRON_RUN_AS_NODE;
 return {...env,PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8',PYTHONDONTWRITEBYTECODE:'1',
  B7_ENV_FILE:path.join(userDir,'no-env-file'),B7_ROOT:payload,
  B7_ANYSTYLE_HOME:path.join(payload,'shared/runtime/anystyle'),B7_NODE_EXE:process.execPath,B7_NODE_IS_ELECTRON:'1',
  REFERENCE_DATA_DIR:path.join(userDir,'data/reference'),
  DEEPSEEK_API_KEY:settings.text.key,DEEPSEEK_BASE_URL:settings.text.base,DEEPSEEK_TEXT_MODEL:settings.text.model,
  LLM_API_KEY:settings.vision.key,LLM_API_BASE:settings.vision.base,LLM_MODEL:settings.vision.model,
  OPENALEX_API_KEY:settings.openalex.key,
  ANYSTYLE_FORMAT_MODE:fs.existsSync(path.join(payload,'shared/runtime/anystyle/rubyinstaller-3.3.12-2-x64/bin/ruby.exe'))&&fs.existsSync(path.join(payload,'shared/runtime/anystyle/node_modules/cld3-asm'))?'local':'remote',
  REFERENCE_FAKE_DNS:settings.fakeDns?'1':'0'};
}
module.exports={Settings,makeEnvironment,validateBase,DEFAULTS};
