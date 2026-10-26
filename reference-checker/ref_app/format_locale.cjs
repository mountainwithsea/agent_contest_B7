const fs=require('fs'),path=require('path');
const deps=process.env.B7_ANYSTYLE_HOME||path.join(__dirname,'../../shared/runtime/anystyle');
const {loadModule}=require(path.join(deps,'node_modules/cld3-asm'));
(async()=>{
  const input=JSON.parse(fs.readFileSync(0,'utf8'));
  const factory=await loadModule();const detector=factory.create(0,1000);
  const output=input.map(s=>s && [...s].length>8 ? detector.findLanguage(s) : null);
  detector.dispose();process.stdout.write(JSON.stringify(output));
})().catch(e=>{console.error(e);process.exit(1)});
