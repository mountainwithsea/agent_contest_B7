const {app,BrowserWindow,ipcMain,dialog,shell,safeStorage,Menu}=require('electron');
const fs=require('node:fs');const path=require('node:path');const {spawn}=require('node:child_process');
const {checkConnection}=require('./connections.cjs');
const {Settings}=require('./settings.cjs');const {Services}=require('./services.cjs');
const profile=process.argv.find(x=>x.startsWith('--profile='));
if(profile)app.setPath('userData',path.resolve(profile.slice(10)));
else app.setPath('userData',path.join(app.getPath('appData'),'B7ReferenceChecker'));
const locked=app.requestSingleInstanceLock();if(!locked){app.quit();}
let win,settings,services,quitting=false,closing=false,changing=false,bootError=null;
const home=path.join(__dirname,'index.html');
const payload=app.isPackaged?path.join(process.resourcesPath,'payload'):path.resolve(__dirname,'../staging/payload');
function status(){return {version:app.getVersion(),settings:settings?.public(),services:services?.status(),error:bootError,dataDir:app.getPath('userData')}}
function notify(){if(win&&!win.isDestroyed())win.webContents.send('b7:status',status())}
async function requestQuit(){
 if(quitting||closing)return;closing=true;
 try{
  if(changing)throw Error('正在保存设置，请稍后再退出');
  const active=services?await services.active():[];
  if(active.length){const r=await dialog.showMessageBox(win&&!win.isDestroyed()?win:undefined,{type:'question',buttons:['继续处理','停止任务并退出'],defaultId:0,cancelId:0,message:'还有任务正在处理',detail:'退出会停止这些任务，已保存的记录会保留。'});if(r.response!==1)return;}
  await services?.stop();quitting=true;app.quit();
 }catch(err){dialog.showErrorBox('暂时无法退出',err.message)}finally{closing=false}
}
function trusted(event){if(event.sender!==win?.webContents||event.senderFrame!==win.webContents.mainFrame||event.senderFrame.url!==require('node:url').pathToFileURL(home).href)throw Error('不接受此页面的桌面操作')}
async function guardChange(fn){if(changing)throw Error('正在保存或重启，请稍候');changing=true;try{return await fn()}finally{changing=false}}
function external(url){try{const u=new URL(url);if(['https:','http:'].includes(u.protocol)&&!u.username&&!u.password)shell.openExternal(url)}catch{}}
function register(){
 const handle=(name,fn)=>ipcMain.handle('b7:'+name,async(e,...args)=>{trusted(e);try{return {ok:true,value:await fn(...args)}}catch(err){let message=err.message||'操作失败';for(const g of ['text','vision','openalex']){const key=settings?.data[g]?.key;if(key)message=message.split(key).join('[已隐藏]')}return {ok:false,error:message}}});
 handle('state',()=>status());
 handle('save',patch=>guardChange(async()=>{if((await services.active()).length)throw Error('有任务正在运行，请等任务完成后再保存设置');await settings.save(patch);await services.stop();await services.start(await settings.values());bootError=null;notify();return status()}));
 handle('test',(group,patch)=>checkConnection(group,settings.merge(patch||{})));
 handle('restart',()=>guardChange(async()=>{if((await services.active()).length)throw Error('有任务正在运行，请稍后重试');await services.stop();await services.start(await settings.values());bootError=null;notify();return status()}));
 handle('folder',async kind=>{const folder=path.join(app.getPath('userData'),kind==='logs'?'logs':'data');fs.mkdirSync(folder,{recursive:true});const result=await shell.openPath(folder);if(result)throw Error('无法打开文件夹');return true});
 handle('update',async()=>{
  const selected=await dialog.showOpenDialog(win,{title:'选择已下载的新版安装包',properties:['openFile'],filters:[{name:'知衡 · 文献核验安装包',extensions:['exe']}]});
  if(selected.canceled)return false;const installer=selected.filePaths[0];
  if(!/^B7-Reference-Setup-[\w.-]+\.exe$/i.test(path.basename(installer)))throw Error('请选择 B7-Reference-Setup 开头的正式安装包');
  if((await services.active()).length)throw Error('请先完成当前任务再安装更新');
  const answer=await dialog.showMessageBox(win,{type:'question',buttons:['取消','关闭应用并安装'],defaultId:0,cancelId:0,message:'安装新版本',detail:'将关闭工作台并运行所选安装包。已有任务和设置会保留。'});
  if(answer.response!==1)return false;await services.stop();const child=spawn(installer,[],{detached:true,stdio:'ignore',windowsHide:false});child.unref();quitting=true;app.quit();return true;
 });
}
async function create(){
 app.setAppUserModelId('cn.edu.zzu.b7.reference');Menu.setApplicationMenu(null);
 win=new BrowserWindow({width:1440,height:980,minWidth:1000,minHeight:700,title:'知衡 · 文献核验',backgroundColor:'#ffffff',show:false,webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true,webSecurity:true}});
 win.webContents.setWindowOpenHandler(({url})=>{external(url);return {action:'deny'}});
 win.webContents.on('will-navigate',(e,url)=>{if(url!==require('node:url').pathToFileURL(home).href){e.preventDefault();external(url)}});
 win.webContents.session.setPermissionRequestHandler((_wc,_permission,callback)=>callback(false));
 app.on('web-contents-created',(_e,contents)=>{
  contents.setWindowOpenHandler(({url})=>{
   const local=Object.values(services?.urls||{}).some(base=>url.startsWith(base+'/'));
   if(local){const popup=new BrowserWindow({parent:win,width:1100,height:800,webPreferences:{sandbox:true,contextIsolation:true,nodeIntegration:false}});popup.loadURL(url);return {action:'deny'}}
   external(url);return {action:'deny'};
  });
 });
 win.webContents.session.on('will-download',(e,item)=>{
  const selected=dialog.showSaveDialogSync(win,{defaultPath:path.join(app.getPath('downloads'),path.basename(item.getFilename()))});
  if(!selected)item.cancel();else item.setSavePath(selected);
 });
 win.on('close',e=>{
  if(quitting)return;e.preventDefault();
  requestQuit();
 });
 await win.loadFile(home);win.show();
 try{await guardChange(async()=>{settings=new Settings(app.getPath('userData'),safeStorage);services=new Services(payload,app.getPath('userData'),notify);await services.start(await settings.values())})}
 catch(e){bootError=e.message}
 notify();
}
if(locked){app.on('second-instance',()=>{if(win&&!win.isDestroyed()){win.show();win.focus()}});app.whenReady().then(async()=>{register();await create()}).catch(e=>{dialog.showErrorBox('启动失败',e.message);quitting=true;app.quit()});app.on('before-quit',e=>{if(!quitting){e.preventDefault();requestQuit()}});app.on('window-all-closed',()=>{if(quitting)app.quit();else requestQuit()})}
