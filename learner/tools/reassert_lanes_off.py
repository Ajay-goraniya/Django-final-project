#!/usr/bin/env python3
"""Re-assert every lane's manual_enabled to False on the Tokyo engine.

Exists because the pause has now been found silently reverted twice: on 09-11
14:40 and again on 09-12 20:38, both times with master OFF, all three kinds back
to True, and NO restart (uptime kept climbing across the event). Master being off
makes it harmless in the moment, but if master is turned on all three lanes fire
at once, MAIN included, which is meant to be off always.

Reads the state first, only writes the kinds that are actually True, and prints
before and after so the change is auditable. Does not touch master.
"""
import base64, json, sys, urllib.request

BASE = "/tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/b10live"
url, user, pw = [l.strip() for l in open(f"{BASE}/v11/launch/tokyo.auth")][:3]
HDR = {"Authorization": "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()}


def get(path):
    return json.load(urllib.request.urlopen(urllib.request.Request(url + path, headers=HDR), timeout=25))


def post(path, payload):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url + path, data=body, headers={**HDR, "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=25))


def kinds_of(controls):
    k = controls.get("kinds") or {}
    if isinstance(k, list):
        return {x["kind"]: x.get("manual_enabled") for x in k}
    return {a: (b.get("manual_enabled") if isinstance(b, dict) else b) for a, b in k.items()}


def main():
    c = get("/api/controls")
    before = kinds_of(c)
    print("before: master", c.get("master_enabled"), "kinds", before, flush=True)
    changed = []
    for kind, enabled in before.items():
        if enabled:
            r = post("/api/controls/signal", {"confirmed": True, "kind": kind, "manual_enabled": False})
            changed.append((kind, r.get("ok", r)))
    after = kinds_of(get("/api/controls"))
    print("after:  kinds", after, flush=True)
    print("changed:", changed or "nothing was enabled", flush=True)
    bad = [k for k, v in after.items() if v]
    if bad:
        print("STILL ENABLED:", bad, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
