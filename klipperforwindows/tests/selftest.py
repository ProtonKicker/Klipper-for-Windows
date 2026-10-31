"""Live connection test: the exact endpoints Mainsail and Fluidd hit.

Run with the runtime venv python:
  python -m klipperforwindows.tests.selftest [--full]

--full additionally runs a real gcode round-trip through Moonraker and the
virtual_sdcard (upload -> start -> complete). Safe on a bench printer.
"""
import argparse
import json
import sys
import time
import urllib.request
import uuid

from .. import paths

WS_URL = "ws://localhost:{}/websocket".format(paths.MOONRAKER_PORT)


def _get(url, timeout=8):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.read()


def check_static(port, label):
    status, body = _get("http://127.0.0.1:{}/".format(port))
    text = body.decode(errors="replace")
    if "<html" not in text.lower():
        raise AssertionError("{} index is not HTML".format(label))
    return status, len(body)


def check_rest(port=None):
    port = port or paths.MOONRAKER_PORT
    status, body = _get("http://127.0.0.1:{}/server/info".format(port))
    data = json.loads(body)
    if not data.get("result", {}).get("klippy_connected"):
        raise AssertionError("moonraker not connected to klippy")
    return status


async def check_ws(url=None):
    import tornado.httpclient
    import tornado.websocket
    req = tornado.httpclient.HTTPRequest(url or WS_URL)
    conn = await tornado.websocket.websocket_connect(req)
    try:
        for method, ident in (("printer.info", 1), ("server.info", 2)):
            await conn.write_message(json.dumps(
                {"jsonrpc": "2.0", "method": method, "params": {}, "id": ident}))
            msg = json.loads(await conn.read_message())
            if "result" not in msg:
                raise AssertionError(method + " -> " + json.dumps(msg)[:200])
        return True
    finally:
        conn.close()


def check_full_pipeline():
    """Upload a test gcode, start it, wait for 'complete'."""
    token = uuid.uuid4().hex[:8]
    filename = "selftest-{}.gcode".format(token)
    payload = ("M117 selftest {}\nG4 P300\nM117 done\n".format(token)).encode()

    boundary = "----klfw" + token
    parts = [
        "--{}\r\nContent-Disposition: form-data; name=\"root\"\r\n"
        "\r\ngcodes\r\n".format(boundary).encode(),
        "--{}\r\nContent-Disposition: form-data; name=\"file\"; "
        "filename=\"{}\"\r\nContent-Type: application/octet-stream\r\n"
        "\r\n".format(boundary, filename).encode(),
        payload,
        "\r\n--{}--\r\n".format(boundary).encode(),
    ]
    body = b"".join(parts)
    req = urllib.request.Request(
        "http://127.0.0.1:{}/server/files/upload".format(paths.MOONRAKER_PORT),
        data=body, method="POST",
        headers={"Content-Type":
                 "multipart/form-data; boundary={}".format(boundary)})
    with urllib.request.urlopen(req, timeout=15) as r:
        json.loads(r.read())

    req = urllib.request.Request(
        "http://127.0.0.1:{}/printer/print/start?filename={}".format(
            paths.MOONRAKER_PORT, filename), method="POST", data=b"")
    with urllib.request.urlopen(req, timeout=10) as r:
        json.loads(r.read())

    deadline = time.time() + 60
    state = None
    while time.time() < deadline:
        status, body = _get(
            "http://127.0.0.1:{}/printer/objects/query?print_stats".format(
                paths.MOONRAKER_PORT))
        st = json.loads(body)["result"]["status"]["print_stats"]
        state = st.get("state")
        if state in ("complete", "error"):
            break
        time.sleep(0.5)
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:{}/server/files/delete?root=gcodes&path={}"
            .format(paths.MOONRAKER_PORT, filename), method="DELETE")
        urllib.request.urlopen(req, timeout=8)
    except Exception:
        pass
    if state != "complete":
        raise AssertionError("print ended in '{}' (expected complete)".format(
            state))
    return filename


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Live endpoint self-test (run while the stack is up)")
    ap.add_argument("--full", action="store_true",
                    help="also run a real gcode round-trip")
    args = ap.parse_args(argv)

    results = []

    def record(label, fn):
        try:
            detail = fn()
            results.append(("[ok]   {} {}".format(label, detail or ""), True))
        except Exception as e:
            results.append(("[FAIL] {}: {}".format(label, str(e)[:140]), False))

    record("mainsail static (:8080)",
           lambda: check_static(paths.WEB_PORT, "mainsail"))
    record("fluidd static (:8081)",
           lambda: check_static(paths.FLUIDD_PORT, "fluidd"))
    record("moonraker REST (:7125)", check_rest)
    record("mainsail proxy REST (browser path)",
           lambda: check_rest(paths.WEB_PORT))
    record("fluidd proxy REST (browser path)",
           lambda: check_rest(paths.FLUIDD_PORT))

    import asyncio
    loop = asyncio.new_event_loop()
    try:
        try:
            loop.run_until_complete(check_ws())
            results.append(("[ok]   websocket JSON-RPC (:7125)", True))
        except Exception as e:
            results.append(("[FAIL] websocket :7125: " + str(e)[:140], False))
        for port, name in ((paths.WEB_PORT, "mainsail"),
                           (paths.FLUIDD_PORT, "fluidd")):
            try:
                loop.run_until_complete(
                    check_ws("ws://127.0.0.1:{}/websocket".format(port)))
                results.append(("[ok]   {} proxy websocket".format(name), True))
            except Exception as e:
                results.append(("[FAIL] {} proxy websocket: ".format(name)
                                + str(e)[:120], False))
    finally:
        loop.close()

    if args.full:
        record("gcode pipeline (upload -> print -> complete)",
               check_full_pipeline)

    ok = all(r[1] for r in results)
    for desc, _ in results:
        print(desc, flush=True)
    print("SELFTEST " + ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
