import random
import struct
from socket import socket
from typing import List, Union

from .mock_socket import socket as mock_socket


def imitate_controller_send(sock: Union[mock_socket, socket], l_data: List[bytes]):
    # explicit byte format here for sanity check
    # placeholder flag, should be discarded by receiver
    header = struct.pack("!H", 0) + struct.pack("!H", len(l_data))
    body = b""
    sent_ids = []
    sent_payloads = []
    for data in l_data:
        tid = struct.pack("!I", random.randint(1, 100))
        sent_ids.append(tid)
        sent_payloads.append(data)
        length = struct.pack("!I", len(data))
        body += tid + length + data

    sock.sendall(header + body)  # type: ignore
    return sent_ids, sent_payloads
