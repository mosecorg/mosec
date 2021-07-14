class MockSocket:
    """Mock socket object used to test protocol."""

    def __init__(self, family=None):
        self.family = family
        self.buffer = b""
        self.timeout = None

    def recv(self, bufsize, flags=None) -> bytes:
        data = self.buffer[:bufsize]
        self.buffer = self.buffer[bufsize:]
        return data

    def recv_into(self, mv: memoryview, nbytes=1):
        """nbytes=1 to avoid boundary condition"""
        chunk = self.buffer[:nbytes]
        mv[:nbytes] = chunk
        self.buffer = self.buffer[nbytes:]
        return nbytes

    def settimeout(self, timeout):
        self.timeout = timeout

    def setblocking(self, flag):
        pass

    def listen(self, backlog):
        pass

    def sendall(self, data, flags=None):
        self.buffer += data
        return len(data)

    def getpeername(self):
        return ("peer-address", "peer-port")

    def close(self):
        pass

    def connect(self, host):
        pass


class socket:
    AF_UNIX = "AF_UNIX"
    SOCK_STREAM = "SOCK_STREAM"

    @staticmethod
    def socket(family=None, type=None, proto=None):
        return MockSocket(family)
