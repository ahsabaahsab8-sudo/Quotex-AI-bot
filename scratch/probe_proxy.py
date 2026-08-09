import socket, base64, sys

HOST = "178.104.94.136"
PORT = 35069
USER = "DVS7ibIvyh"
PASS = "NQmMehp"

def http_proxy_test():
    print("=== HTTP CONNECT test ===")
    try:
        s = socket.create_connection((HOST, PORT), timeout=15)
        auth = base64.b64encode(f"{USER}:{PASS}".encode()).decode()
        req = f"CONNECT api.ipify.org:443 HTTP/1.1\r\nHost: api.ipify.org:443\r\nProxy-Authorization: Basic {auth}\r\n\r\n"
        s.sendall(req.encode())
        data = s.recv(4096).decode(errors="replace")
        print("RESP:", repr(data[:500]))
        s.close()
    except Exception as e:
        print("ERR:", e)

def http_plain_proxy_test():
    print("=== HTTP plain GET via proxy ===")
    try:
        s = socket.create_connection((HOST, PORT), timeout=15)
        auth = base64.b64encode(f"{USER}:{PASS}".encode()).decode()
        req = f"GET http://api.ipify.org/ HTTP/1.1\r\nHost: api.ipify.org\r\nProxy-Authorization: Basic {auth}\r\n\r\n"
        s.sendall(req.encode())
        data = s.recv(4096).decode(errors="replace")
        print("RESP:", repr(data[:500]))
        s.close()
    except Exception as e:
        print("ERR:", e)

def socks5_test():
    print("=== SOCKS5 auth test ===")
    try:
        s = socket.create_connection((HOST, PORT), timeout=15)
        # greeting: no auth + user/pass
        s.sendall(b"\x05\x02\x00\x02")
        resp = s.recv(2)
        print("GREETING RESP:", resp.hex())
        if resp == b"\x05\x02":
            # user/pass auth
            ul = len(USER); pl = len(PASS)
            s.sendall(b"\x01" + bytes([ul]) + USER.encode() + bytes([pl]) + PASS.encode())
            auth_resp = s.recv(2)
            print("AUTH RESP:", auth_resp.hex())
            if auth_resp == b"\x01\x00":
                print("AUTH OK - now CONNECT")
                host = b"api.ipify.org"
                s.sendall(b"\x05\x01\x00\x03" + bytes([len(host)]) + host + (443).to_bytes(2, "big"))
                print("CONNECT RESP:", s.recv(10).hex())
        elif resp == b"\x05\x00":
            print("NO AUTH REQUIRED")
        else:
            print("UNEXPECTED")
        s.close()
    except Exception as e:
        print("ERR:", e)

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("http", "all"): http_proxy_test()
    if which in ("plain", "all"): http_plain_proxy_test()
    if which in ("socks", "all"): socks5_test()
