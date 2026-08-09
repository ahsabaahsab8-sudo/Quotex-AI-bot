import socket, sys

HOST = "178.104.94.136"
PORT = 35069

CREDS = [
    ("DVS7ibIvyh", "NQmMehp"),
    ("NQmMehp", "DVS7ibIvyh"),
    ("DVS7ibIvyh", "NQmMehp "),
    ("DVS7ibIvyh ", "NQmMehp"),
    ("DVS7ibIvyh", "NQmMehp-session-1"),
    ("user-DVS7ibIvyh", "NQmMehp"),
    ("DVS7ibIvyh-region-pk", "NQmMehp"),
    ("", ""),
]

def socks_auth(USER, PASS):
    try:
        s = socket.create_connection((HOST, PORT), timeout=12)
        s.sendall(b"\x05\x02\x00\x02")
        resp = s.recv(2)
        if resp != b"\x05\x02":
            s.close()
            return f"greet={resp.hex()}"
        s.sendall(b"\x01" + bytes([len(USER)]) + USER.encode() + bytes([len(PASS)]) + PASS.encode())
        ar = s.recv(2)
        s.close()
        return "OK" if ar == b"\x01\x00" else f"authfail={ar.hex()}"
    except Exception as e:
        return f"err={e}"

for u, p in CREDS:
    print(f"{u!r}:{p!r} -> {socks_auth(u, p)}")
