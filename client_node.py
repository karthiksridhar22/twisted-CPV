# client_node.py

import sys
import time
import socket
from twisted.internet import reactor, stdio
from twisted.protocols.basic import LineReceiver
from twisted.internet.protocol import DatagramProtocol
from protocols import BaseClient, BaseServer
from prompt import ColoredPrompt
from common import unpack_datagram_args
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class ClientMessageHandler:
    """
    Handles incoming peer-to-peer messages for the client.
    """
    def __init__(self, client_node):
        self.client_node = client_node

    def handleP2PMessage(self, data, addr):
        logging.info(f"ClientMessageHandler received data from {addr}: {data}")
        if data.startswith("HELLO from VERIFIER") or data.startswith("HELLO from CLIENT"):
            # Example: "HELLO from VERIFIER|id_server_1|Hello, Client!"
            # or "HELLO from CLIENT|id_client_2|Hello, Client!"
            parts = data.split('|', 2)
            if len(parts) == 3:
                _, sender_id, message = parts
                self.client_node.prompt.logChatMsg(sender_id, message)
        elif data.startswith("MSG"):
            # MSG|sender_id|message
            parts = data.split('|', 2)
            if len(parts) == 3:
                _, sender_id, message = parts
                self.client_node.prompt.logChatMsg(sender_id, message)
        else:
            # Handle other messages if necessary
            logging.warning(f"ClientMessageHandler: Unrecognized message format from {addr}: {data}")


class ClientCLI(LineReceiver):
    """
    Command-Line Interface for the client.
    """
    delimiter = b'\n'

    def __init__(self, client):
        self.client = client

    def connectionMade(self):
        self.prompt = self.client.prompt
        self.printWelcome()

    def lineReceived(self, line):
        line = line.decode('utf-8').strip()
        if not line:
            self.client.prompt._writePrompt()
            return

        parts = line.split(' ', 2)
        cmd = parts[0].lower()

        if cmd == 'help':
            self.printHelp()
        elif cmd == 'query' and len(parts) == 2:
            verifier_id = parts[1]
            self.client.queryVerifier(verifier_id)
        elif cmd == 'list':
            self.listConnections()
        elif cmd == 'send' and len(parts) == 3:
            verifier_id = parts[1]
            message = parts[2]
            self.client.sendMessageToVerifier(verifier_id, message)
        elif cmd == 'broadcast' and len(parts) == 2:
            message = parts[1]
            self.client.broadcastMessage(message)
        elif cmd == 'exit':
            self.client.prompt.log("Closing client...")
            reactor.stop()
        else:
            self.client.prompt.logError("Unknown or incomplete command. Type 'help' for usage.")

        self.client.prompt._writePrompt()

    def printWelcome(self):
        welcome_text = f"Welcome to Client {self.client.client_id} CLI. Type 'help' to see available commands."
        self.client.prompt.log(welcome_text)
        self.client.prompt._writePrompt()

    def printHelp(self):
        help_text = """
Available commands:
  help                      - Show this help message
  query <verifier_id>       - Query info about a verifier and connect if found
  list                      - List currently connected verifiers
  send <verifier_id> <msg>  - Send a message to a specific connected verifier
  broadcast <msg>           - Broadcast a message to all connected verifiers
  exit                      - Exit the client application
"""
        self.client.prompt.log(help_text.strip())

    def listConnections(self):
        if not self.client.verifiers:
            self.client.prompt.log("No verifiers connected.")
        else:
            self.client.prompt.log("Connected verifiers:")
            for vid, info in self.client.verifiers.items():
                self.client.prompt.log(f"  {vid} ({info['name']}) at {info['ip']}:{info['port']}")


class ClientNode:
    """
    Represents a client in the network.
    """
    def __init__(self, client_id, client_name, signal_server_ip, signal_server_port, p2p_port):
        self.client_id = client_id
        self.client_name = client_name
        self.signal_server_ip = signal_server_ip
        self.signal_server_port = signal_server_port
        self.p2p_port = p2p_port
        self.prompt = ColoredPrompt(prompt=client_id + "> ")
        self.verifiers = {}  # {verifier_id: {'name':..., 'ip':..., 'port':...}}

        # Instantiate protocols
        self.message_handler = ClientMessageHandler(self)
        self.p2p_protocol = BaseServer(self)  # P2P Protocol
        self.signal_client_protocol = BaseClient(
            message_type='CONNECT_CLIENT',
            node_id=self.client_id,
            node_name=self.client_name,
            node_type='CLIENT',
            node=self
        )
        self.query_times = {}  # For Communication Performance Validation (CPV)

    def start(self):
        try:
            # Start the P2P server (listening for incoming peer messages)
            reactor.listenUDP(self.p2p_port, self.p2p_protocol)
            logging.info(f"Client {self.client_id} P2P listening on port {self.p2p_port}")

            # Start the Signal Server client on an ephemeral port
            self.signal_ephemeral_port = self.get_ephemeral_port()
            reactor.listenUDP(self.signal_ephemeral_port, self.signal_client_protocol)
            logging.info(f"Client {self.client_id} Signal Server client listening on port {self.signal_ephemeral_port}")

            # Set endpoints for the Signal Server client
            private_endpoint = (self.get_local_ip(), self.signal_ephemeral_port)
            self.signal_client_protocol.set_endpoints(
                server_endpoint=(self.signal_server_ip, self.signal_server_port),
                private_endpoint=private_endpoint
            )

            # Start CLI
            cli = ClientCLI(self)
            stdio.StandardIO(cli)
            logging.info(f"Starting Client {self.client_id} CLI.")
            reactor.run()
        except Exception as e:
            logging.error(f"An error occurred while starting the Client Node: {e}")
            sys.exit(1)

    def get_local_ip(self):
        try:
            # This method connects to an external host to get the local IP address
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def get_ephemeral_port(self):
        # To get the ephemeral port assigned by the OS for the Signal Server client
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(('', 0))
        port = s.getsockname()[1]
        s.close()
        return port

    # Callback methods invoked by BaseServer (P2P)
    def handleP2PMessage(self, data, addr):
        self.message_handler.handleP2PMessage(data, addr)

    # Callback methods invoked by BaseClient (Signal Server)
    def onConnectSuccess(self, message):
        if message == "CLIENT_REGISTERED":
            self.prompt.log("Client registered with Signal Server successfully.")
        else:
            self.prompt.log(f"Connected successfully: {message}")

    def onConnectError(self, message):
        self.prompt.logError(f"Connection error: {message}")

    def handleSignalServerMessage(self, data, addr):
        # Handle any additional messages from the Signal Server if necessary
        pass  # Implement if needed

    # Methods invoked by CLI
    def queryVerifier(self, verifier_id):
        # Query a verifier's info from the Signal Server
        msg = f"QUERY_VERIFIER|{verifier_id}"
        self.signal_client_protocol.transport.write(msg.encode('utf-8'), (self.signal_server_ip, self.signal_server_port))
        self.prompt.log(f"Querying Signal Server for Verifier '{verifier_id}'...")
        logging.info(f"Sent QUERY_VERIFIER message: {msg}")
        # Record the time when the query was sent for CPV
        self.query_times[verifier_id] = time.time()

    def sendMessageToVerifier(self, verifier_id, message):
        # Send a message to a specific connected verifier
        info = self.verifiers.get(verifier_id)
        if not info:
            self.prompt.logError("Verifier not known or not connected. Try 'query <verifier_id>' first.")
            return
        addr = (info['ip'], info['port'])
        msg = f"HELLO from CLIENT|{self.client_id}|{message}"
        self.p2p_protocol.sendMessage(msg, addr)
        self.prompt.log(f"Sent message to {verifier_id}.")
        logging.info(f"Sent HELLO message to {verifier_id}: {msg}")

    def broadcastMessage(self, message):
        # Broadcast a message to all connected verifiers
        if not self.verifiers:
            self.prompt.log("No verifiers to broadcast to.")
            return
        msg = f"MSG|{self.client_id}|{message}"
        for vid, info in self.verifiers.items():
            addr = (info['ip'], info['port'])
            self.p2p_protocol.sendMessage(msg, addr)
            logging.info(f"Broadcasted MSG to {vid}: {msg}")
        self.prompt.log("Broadcasted message to all verifiers.")

    # Methods to handle registrations from Signal Server
    def onVerifierRegisteredPeer(self, verifier_id, verifier_name, ip, port):
        if verifier_id != self.client_id:
            self.verifiers[verifier_id] = {'name': verifier_name, 'ip': ip, 'port': port}
            self.prompt.log(f"Registered verifier: {verifier_id} ({verifier_name}) at {ip}:{port}")

    def onVerifierDisconnectedPeer(self, verifier_id):
        if verifier_id in self.verifiers:
            verifier_info = self.verifiers.pop(verifier_id)
            self.prompt.log(f"Verifier disconnected: {verifier_id} ({verifier_info['name']})")

    # Methods to be called by BaseServer (Signal Server Protocol)
    def onVerifierRegistered(self, verifier_id, verifier_name, ip, port):
        if verifier_id != self.client_id:
            self.onVerifierRegisteredPeer(verifier_id, verifier_name, ip, port)

    def onVerifierDisconnected(self, verifier_id):
        self.onVerifierDisconnectedPeer(verifier_id)

def main():
    if len(sys.argv) != 6:
        print("Usage: python3 client_node.py <client_id> <client_name> <signal_server_ip> <signal_server_port> <server_port>")
        sys.exit(1)
    
    client_id = sys.argv[1]
    client_name = sys.argv[2]
    signal_server_ip = sys.argv[3]
    
    try:
        signal_server_port = int(sys.argv[4])
        server_port = int(sys.argv[5])
    except ValueError:
        print("Error: <signal_server_port> and <server_port> must be integers.")
        sys.exit(1)

    node = ClientNode(client_id, client_name, signal_server_ip, signal_server_port, server_port)
    try:
        node.start()
    except Exception as e:
        logging.error(f"An error occurred while starting the Client Node: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()