const {test}=require('node:test');const assert=require('node:assert/strict');
const {checkConnection}=require('../desktop/connections.cjs');
const config={text:{base:'https://text.example/v1',key:'unit-secret',model:'text'},vision:{base:'https://vision.example/v1',key:'vision-secret',model:'vision'},openalex:{key:'registry-key'}};
test('connection test uses the requested model and hides provider bodies on failure',async()=>{
 const fake=async(url,options)=>{assert.equal(url,'https://text.example/v1/chat/completions');assert.equal(options.headers.Authorization,'Bearer unit-secret');return new Response('unit-secret denied',{status:401})};
 await assert.rejects(checkConnection('text',config,fake),e=>e.message.includes('401')&&!e.message.includes('unit-secret'));
});
test('vision connection checks send a real image and accept a streaming-only service',async()=>{
 const fake=async(url,options)=>{const body=JSON.parse(options.body);assert.equal(body.stream,true);assert.equal(body.model,'vision');assert.ok(body.messages[0].content[1].image_url.url.startsWith('data:image/png;base64,'));return new Response('data: {"choices":[{"delta":{"content":"OK"}}]}\n\ndata: [DONE]\n',{status:200})};
 assert.match(await checkConnection('vision',config,fake),/图片/);
});
