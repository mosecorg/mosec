# Copyright 2022 MOSEC Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Mock socket interface."""


class MockSocket:
    """Mock socket object used to test protocol."""

    def __init__(self, family=None):
        self.family = family
        self.buffer = b""
        self.timeout = None

    def recv(self, bufsize, flags=None) -> bytes:
        """Receive data from buffer with size=bufsize."""
        data = self.buffer[:bufsize]
        self.buffer = self.buffer[bufsize:]
        return data

    def recv_into(self, buf: memoryview, nbytes=1):
        """Set nbytes=1 to avoid boundary condition."""
        chunk = self.buffer[:nbytes]
        buf[:nbytes] = chunk
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

    # pylint: disable=no-self-use
    def getpeername(self):
        return ("peer-address", "peer-port")

    def close(self):
        pass

    def connect(self, host):
        pass


class Socket:
    AF_UNIX = "AF_UNIX"
    SOCK_STREAM = "SOCK_STREAM"

    @staticmethod
    def socket(family=None, typ=None, protocol=None):
        return MockSocket(family)
