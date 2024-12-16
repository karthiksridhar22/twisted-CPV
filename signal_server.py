# signal_server.py

import sys
from twisted.internet import reactor
from protocols import BaseServer
from prompt import ColoredPrompt
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class SignalServer:
    """
    The Signal Server that handles registrations and queries from clients and verifiers.
    """
    def __init__(self, port):
        self.port = port
        self.prompt = ColoredPrompt(prompt="SignalServer> ")
        self.protocol = BaseServer(self)

    def onVerifierRegistered(self, verifier_id, verifier_name, ip, port):
        self.prompt.log(f"Verifier registered: {verifier_id} ({verifier_name}) at {ip}:{port}")

    def onVerifierDisconnected(self, verifier_id):
        self.prompt.log(f"Verifier disconnected: {verifier_id}")

    def onClientRegistered(self, client_id, client_name, ip, port):
        self.prompt.log(f"Client registered: {client_id} ({client_name}) at {ip}:{port}")

    def onClientDisconnected(self, client_id):
        self.prompt.log(f"Client disconnected: {client_id}")

    def handleSignalServerMessage(self, data, addr):
        # For Signal Server, typically no additional handling
        pass  # Implement if needed

    def start(self):
        reactor.listenUDP(self.port, self.protocol)
        self.prompt.log(f"Starting Signal Server on port {self.port}")
        reactor.run()


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 signal_server.py <port>")
        sys.exit(1)
    try:
        port = int(sys.argv[1])
    except ValueError:
        print("Error: <port> must be an integer.")
        sys.exit(1)
    server = SignalServer(port)
    server.start()


if __name__ == '__main__':
    main()
