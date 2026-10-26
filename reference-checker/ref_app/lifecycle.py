"""OS ownership checks: PID plus creation time, never a PID alone."""
import ctypes
import os
import time
from pathlib import Path

def stamp(pid):
    if os.name!='nt':
        try:return Path(f'/proc/{pid}/stat').read_text().split(') ',1)[1].split()[19]
        except OSError:return None
    from ctypes import wintypes as w
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
    k.GetProcessTimes.argtypes=[w.HANDLE]+[ctypes.POINTER(w.FILETIME)]*4
    k.CloseHandle.argtypes=[w.HANDLE]
    h=k.OpenProcess(0x1000,False,pid)
    if not h:return None
    try:
        a,b,c,d=w.FILETIME(),w.FILETIME(),w.FILETIME(),w.FILETIME()
        if not k.GetProcessTimes(h,ctypes.byref(a),ctypes.byref(b),ctypes.byref(c),ctypes.byref(d)):return None
        if b.dwHighDateTime or b.dwLowDateTime:return None
        return str((a.dwHighDateTime<<32)|a.dwLowDateTime)
    finally:k.CloseHandle(h)

class OwnedProcess:
    def __init__(self,pid,created):self.pid=pid;self.created=created
    def poll(self):return None if self.created and stamp(self.pid)==self.created else 0
    def terminate(self):
        if self.poll() is not None:return
        if os.name!='nt':
            import signal
            os.kill(self.pid,signal.SIGTERM);return
        from ctypes import wintypes as w
        k=ctypes.WinDLL('kernel32',use_last_error=True);k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
        k.TerminateProcess.argtypes=[w.HANDLE,w.UINT];k.CloseHandle.argtypes=[w.HANDLE]
        h=k.OpenProcess(1,False,self.pid)
        if not h:raise OSError('Cannot open owned worker')
        try:
            if stamp(self.pid)!=self.created:raise OSError('Worker identity changed')
            if not k.TerminateProcess(h,1):raise OSError('Cannot stop worker')
        finally:k.CloseHandle(h)
    def wait(self,timeout=None):
        start=time.monotonic()
        while self.poll() is None:
            if timeout and time.monotonic()-start>timeout:raise TimeoutError('Worker has not stopped')
            time.sleep(.15)
        return 0

class FileLock:
    def __init__(self,path,wait=0):self.path=Path(path);self.file=None;self.wait=wait
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True);self.file=self.path.open('a+b');self.file.seek(0)
        if self.path.stat().st_size==0:self.file.write(b'0');self.file.flush()
        self.file.seek(0)
        started=time.monotonic()
        while True:
            try:
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(self.file,fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic()-started>=self.wait:
                    self.file.close();raise RuntimeError('同一应用或任务已有进程持有锁')
                time.sleep(.03)
        return self
    def __exit__(self,*args):self.file.close()
