import multiprocessing
import tempfile
import time
import unittest
from pathlib import Path


def contender(folder, queue):
    from b7_shared.http_policy import ServiceGate
    with ServiceGate('https://api.crossref.org/works?query=x', root=folder, interval=.12):
        start=time.time()
        time.sleep(.15)
        queue.put((start,time.time()))


class HttpPolicyTests(unittest.TestCase):
    def test_workers_never_overlap_and_respect_interval(self):
        # A mere thread lock or start-time sleep cannot pass this process test.
        with tempfile.TemporaryDirectory() as d:
            ctx=multiprocessing.get_context('spawn');q=ctx.Queue()
            ps=[ctx.Process(target=contender,args=(d,q)) for _ in range(3)]
            for p in ps:p.start()
            spans=sorted(q.get(timeout=10) for _ in ps)
            for p in ps:p.join(10);self.assertEqual(p.exitcode,0)
            for a,b in zip(spans,spans[1:]):self.assertGreaterEqual(b[0]-a[1],.10)

    def test_cooldown_survives_new_gate_and_retry_after_is_not_shortened(self):
        from b7_shared.http_policy import ServiceGate
        with tempfile.TemporaryDirectory() as d:
            with ServiceGate('https://api.crossref.org/works',root=d,interval=0) as g:
                g.feedback(429,{'Retry-After':'0.2'},attempt=1)
            start=time.monotonic()
            with ServiceGate('https://api.crossref.org/works/x',root=d,interval=0):pass
            self.assertGreaterEqual(time.monotonic()-start,.17)

    def test_server_reported_slow_rate_is_honored(self):
        from b7_shared.http_policy import ServiceGate
        with tempfile.TemporaryDirectory() as d:
            with ServiceGate('https://api.crossref.org/works',root=d,interval=0) as g:
                g.feedback(200,{'x-rate-limit-limit':'1','x-rate-limit-interval':'0.2s'})
            start=time.monotonic()
            with ServiceGate('https://api.crossref.org/works',root=d,interval=0):pass
            self.assertGreaterEqual(time.monotonic()-start,.18)

    def test_crossref_search_is_conservative_and_arxiv_hosts_share_budget(self):
        from b7_shared.http_policy import service_policy
        self.assertGreaterEqual(service_policy('https://api.crossref.org/works?query=x')[1],1)
        a=service_policy('https://export.arxiv.org/api/query')
        b=service_policy('https://arxiv.org/abs/1234.5678')
        self.assertEqual(a[0],b[0]);self.assertGreaterEqual(a[1],3)

    def test_retry_after_http_date_and_long_cooldown(self):
        from b7_shared.http_policy import retry_seconds,ServiceGate,CooldownPending
        self.assertEqual(retry_seconds({'Retry-After':'Thu, 01 Jan 1970 00:02:00 GMT'},now=100),20)
        with tempfile.TemporaryDirectory() as d:
            with ServiceGate('https://api.crossref.org/works',root=d,interval=0) as g:
                g.feedback(429,{'Retry-After':'300'},attempt=1)
            with self.assertRaises(CooldownPending):
                with ServiceGate('https://api.crossref.org/works',root=d,max_wait=.1):pass

    def test_repeated_429_cannot_poison_future_requests_permanently(self):
        from b7_shared.http_policy import ServiceGate
        with tempfile.TemporaryDirectory() as d:
            with ServiceGate('https://api.crossref.org/works',root=d) as g:
                for i in range(20):g.feedback(429,{'Retry-After':'0'},attempt=1)
                self.assertLessEqual(g.state['interval'],60)
                g.feedback(200,{})
                self.assertEqual(g.state['interval'],g.interval)


if __name__=='__main__':unittest.main()
