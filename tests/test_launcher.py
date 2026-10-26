import unittest
import subprocess
from unittest.mock import patch
import launch


class LauncherTests(unittest.TestCase):
    def test_backend_wait_returns_regularly_to_dispatch_windows_signals(self):
        class Child:
            def __init__(self):self.calls=0
            def wait(self,timeout=None):
                if timeout is None:raise AssertionError('Unbounded native wait prevents timely signal dispatch')
                self.calls+=1
                if self.calls==1:raise subprocess.TimeoutExpired('backend',timeout)
                return 0
        self.assertEqual(launch.wait_for_exit(Child()),0)

    def test_shutdown_cancels_active_job_before_stopping_backend(self):
        events=[]
        class Child:
            def poll(self):return None
            def terminate(self):events.append('terminate')
            def wait(self,timeout=None):events.append('wait')
        def request(url,body=None,headers=None):
            events.append(url)
            return [{'id':'abc','state':'running'},{'id':'old','state':'completed'}] if body is None else {}
        with patch('launch.local_json',side_effect=request):launch.stop_service(Child(),'http://127.0.0.1:1')
        self.assertEqual(events,['http://127.0.0.1:1/api/jobs','http://127.0.0.1:1/api/jobs/abc/cancel','terminate','wait'])

    def test_shutdown_does_not_request_or_stop_an_already_exited_backend(self):
        class Child:
            def poll(self):return 1
            def terminate(self):raise AssertionError('Already stopped')
        with patch('launch.local_json') as request:launch.stop_service(Child(),'http://127.0.0.1:1')
        request.assert_not_called()


if __name__=='__main__':unittest.main()
