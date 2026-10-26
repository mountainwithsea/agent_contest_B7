const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const {Services}=require('../desktop/services.cjs');
const {makeEnvironment}=require('../desktop/settings.cjs');
test('one reference backend is sufficient for ready state',()=>{
 const s=new Services('unused','unused');s.urls.reference='http://127.0.0.1:1';assert.equal(s.status().ready,true);
});
test('desktop contains no dependency or navigation to another application',()=>{
 const root=path.join(__dirname,'../desktop');
 for(const file of ['services.cjs','renderer.js','index.html'])assert.doesNotMatch(fs.readFileSync(path.join(root,file),'utf8'),/teaching|教学数据|成绩/);
 const pkg=require('../package.json');assert.notEqual(pkg.build.appId,'cn.edu.zzu.b7.workbench');
});
test('desktop without local formatter runtime explicitly uses public conversion',()=>{
 const s={text:{key:'',base:'https://api.deepseek.com',model:'m'},vision:{key:'',base:'https://example.org/v1',model:'v'},openalex:{key:''},fakeDns:false};
 const env=makeEnvironment(s,'missing-payload','user',{});assert.equal(env.ANYSTYLE_FORMAT_MODE,'remote');assert.ok(!env.B7_DATA_DIR);assert.ok(!env.B7_LLM_API_KEY);
});
