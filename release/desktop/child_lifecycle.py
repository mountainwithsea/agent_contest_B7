"""Packaged Python boot hook: own descendants and stop when desktop exits."""
import os
import sys

sys.dont_write_bytecode=True

if os.name=='nt' and os.environ.get('B7_DESKTOP_PARENT'):
    import ctypes
    import threading
    from ctypes import wintypes as w
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    class Basic(ctypes.Structure):
        _fields_=[('process_time',ctypes.c_int64),('job_time',ctypes.c_int64),('flags',w.DWORD),
                  ('minimum',ctypes.c_size_t),('maximum',ctypes.c_size_t),('active',w.DWORD),
                  ('affinity',ctypes.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
    class Limits(ctypes.Structure):
        _fields_=[('basic',Basic),('io',ctypes.c_uint64*6),('process_memory',ctypes.c_size_t),
                  ('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
    k.CreateJobObjectW.argtypes=[ctypes.c_void_p,w.LPCWSTR];k.CreateJobObjectW.restype=w.HANDLE
    k.SetInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD]
    k.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE];k.GetCurrentProcess.restype=w.HANDLE
    k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
    k.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD];k.CloseHandle.argtypes=[w.HANDLE]
    _b7_job=k.CreateJobObjectW(None,None);limits=Limits();limits.basic.flags=0x2000
    if not (_b7_job and k.SetInformationJobObject(_b7_job,9,ctypes.byref(limits),ctypes.sizeof(limits))
            and k.AssignProcessToJobObject(_b7_job,k.GetCurrentProcess())):
        raise OSError(ctypes.get_last_error(),'Cannot own packaged worker descendants')
    def monitor():
        parent=k.OpenProcess(0x100000,False,int(os.environ['B7_DESKTOP_PARENT']))
        if parent:
            k.WaitForSingleObject(parent,0xFFFFFFFF);k.CloseHandle(parent)
        os._exit(0)
    threading.Thread(target=monitor,daemon=True,name='desktop-owner').start()
