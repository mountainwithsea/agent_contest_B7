const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const os=require('node:os');const path=require('node:path');
const {Settings,makeEnvironment,validateBase}=require('../desktop/settings.cjs');
test('official Alibaba preset uses the native model id',()=>{
 assert.equal(require('../desktop/settings.cjs').DEFAULTS.vision.model,'qwen3.8-omni-flash');
});
const crypto={encryptString:s=>Buffer.from('encrypted:'+s),decryptString:b=>b.toString().slice(10),isEncryptionAvailable:()=>true};
test('settings keep secrets off public state and preserve blank keys',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'b7-settings-'));
 try{
  const s=new Settings(dir,crypto);await s.save({text:{key:'test-key-123',model:'example'}});
  assert.equal(s.public().text.hasKey,true);assert.ok(!JSON.stringify(s.public()).includes('test-key'));
  assert.ok(!fs.readFileSync(path.join(dir,'settings.json'),'utf8').includes('"key": "test-key'));
  await s.save({text:{key:'',model:'changed'}});assert.equal((await s.values()).text.key,'test-key-123');
  const restored=new Settings(dir,crypto);assert.equal((await restored.values()).text.key,'test-key-123');
  await restored.save({text:{clearKey:true}});assert.equal(restored.public().text.hasKey,false);
 }finally{fs.rmSync(dir,{recursive:true,force:true})}
});
test('environment excludes development secrets and uses writable data directories',()=>{
 const settings={text:{key:'teacher',base:'https://api.deepseek.com',model:'m'},vision:{key:'',base:'https://example.org/v1',model:'v'},openalex:{key:''},fakeDns:false};
 const env=makeEnvironment(settings,'C:/Program Files/B7/payload','C:/Users/Teacher/AppData/B7',{PATH:'system',DEEPSEEK_API_KEY:'developer',B7_LLM_API_KEY:'developer',PYTHONPATH:'external',LLM_API_KEY:'developer'});
 assert.equal(env.DEEPSEEK_API_KEY,'teacher');assert.equal(env.LLM_API_KEY,'');assert.equal(env.B7_LLM_API_KEY,undefined);
 assert.match(env.REFERENCE_DATA_DIR,/data.reference$/);assert.match(env.B7_ENV_FILE,/no-env-file/);
});
test('base validation prevents embedded credentials and query strings',()=>{
 for(const b of ['http://example.org','https://x:password@example.org','https://example.org/?key=x','file:///x'])assert.throws(()=>validateBase(b));
 assert.equal(validateBase('https://api.deepseek.com/'),'https://api.deepseek.com');
});
