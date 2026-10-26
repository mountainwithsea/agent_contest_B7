const {contextBridge,ipcRenderer}=require('electron');
const invoke=async(name,...args)=>{const r=await ipcRenderer.invoke('b7:'+name,...args);if(!r.ok)throw Error(r.error);return r.value};
contextBridge.exposeInMainWorld('workbench',{
 state:()=>invoke('state'),save:patch=>invoke('save',patch),test:(group,patch)=>invoke('test',group,patch),restart:()=>invoke('restart'),folder:kind=>invoke('folder',kind),update:()=>invoke('update'),
 onStatus:callback=>{const listener=(_e,value)=>callback(value);ipcRenderer.on('b7:status',listener);return ()=>ipcRenderer.removeListener('b7:status',listener)}
});
