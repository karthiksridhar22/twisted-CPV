# verifier_node.py

import sys
import socket
from twisted.internet import reactor, stdio
from twisted.protocols.basic import LineReceiver
from twisted.internet.protocol import DatagramProtocol
from protocols import BaseServer, BaseClient
from prompt import ColoredPrompt
from common import unpack_datagram_args
import logging


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class VerifierMessageHandler:
    """
    Handles incoming peer-to-peer messages for the verifier.
    """
    def __init__(self, verifier_node):
        self.verifier_node = verifier_node

    def handleP2PMessage(self, data, addr):
        logging.info(f"VerifierMessageHandler received data from {addr}: {data}")
        if data.startswith("HELLO from CLIENT") or data.startswith("HELLO from VERIFIER"):
            #"HELLO from CLIENT|id_client_1|Hello, Verifier!"
            # or "HELLO from VERIFIER|id_server_2|Hello, Verifier!"
            parts = data.split('|', 2)
            if len(parts) == 3:
                _, sender_id, message = parts
                self.verifier_node.prompt.logChatMsg(sender_id, message)
        elif data.startswith("MSG"):
            #MSG|sender_id|message
            parts = data.split('|', 2)
            if len(parts) == 3:
                _, sender_id, message = parts
                self.verifier_node.prompt.logChatMsg(sender_id, message)
        else:
            #other random messages
            logging.warning(f"VerifierMessageHandler: Unrecognized message format from {addr}: {data}")


class VerifierCLI(LineReceiver):
    """
    Command-Line Interface for the verifier.
    """
    delimiter = b'\n'

    def __init__(self, verifier):
        self.verifier = verifier

    def connectionMade(self):
        self.prompt = self.verifier.prompt
        self.printWelcome()

    def lineReceived(self, line):
        line = line.decode('utf-8').strip()
        if not line:
            self.verifier.prompt._writePrompt()
            return

        parts = line.split(' ', 2)
        cmd = parts[0].lower()

        if cmd == 'help':
            self.printHelp()
        elif cmd == 'list':
            self.listConnections()
        elif cmd == 'send' and len(parts) == 3:
            target_id = parts[1]
            message = parts[2]
            self.verifier.sendMessageToNode(target_id, message)
        elif cmd == 'broadcast' and len(parts) == 2:
            message = parts[1]
            self.verifier.broadcastMessage(message)
        elif cmd == 'query' and len(parts) == 2:
            target_id = parts[1]
            self.verifier.queryNode(target_id)
        elif cmd == 'exit':
            self.verifier.prompt.log("Shutting down verifier...")
            reactor.stop()
        else:
            self.verifier.prompt.logError("Unknown or incomplete command. Type 'help' for usage.")

        self.verifier.prompt._writePrompt()

    def printWelcome(self):
        welcome_text = f"Welcome to Verifier {self.verifier.verifier_id} CLI. Type 'help' to see available commands."
        self.verifier.prompt.log(welcome_text)
        self.verifier.prompt._writePrompt()

    def printHelp(self):
        help_text = """
Available commands:
  help                      - Show this help message
  list                      - List connected clients and verifiers
  send <target_id> <msg>    - Send a message to a specific connected client or verifier
  broadcast <msg>           - Broadcast a message to all connected clients and verifiers
  query <target_id>         - Query a node's info from the Signal Server
  exit                      - Shutdown this verifier node
"""
        self.verifier.prompt.log(help_text.strip())

    def listConnections(self):
        if not self.verifier.clients and not self.verifier.verifiers:
            self.verifier.prompt.log("No clients or verifiers connected.")
        else:
            if self.verifier.clients:
                self.verifier.prompt.log("Connected clients:")
                for cid, info in self.verifier.clients.items():
                    self.verifier.prompt.log(f"  {cid} ({info['name']}) at {info['ip']}:{info['port']}")
            if self.verifier.verifiers:
                self.verifier.prompt.log("Connected verifiers:")
                for vid, info in self.verifier.verifiers.items():
                    self.verifier.prompt.log(f"  {vid} ({info['name']}) at {info['ip']}:{info['port']}")


class VerifierNode:
    """
    Represents a verifier in the network.
    """
    def __init__(self, verifier_id, verifier_name, signal_server_ip, signal_server_port, p2p_port):
        self.verifier_id = verifier_id
        self.verifier_name = verifier_name
        self.signal_server_ip = signal_server_ip
        self.signal_server_port = signal_server_port
        self.p2p_port = p2p_port
        self.prompt = ColoredPrompt(prompt=verifier_id + "> ")
        self.clients = {}    # {client_id: {'name':..., 'ip':..., 'port':...}}
        self.verifiers = {}  # {verifier_id: {'name':..., 'ip':..., 'port':...}}

        #instantiate protocols
        self.message_handler = VerifierMessageHandler(self)
        self.p2p_protocol = BaseServer(self) 
        self.signal_client_protocol = BaseClient(
            message_type='CONNECT_VERIFIER',
            node_id=self.verifier_id,
            node_name=self.verifier_name,
            node_type='VERIFIER',
            node=self
        )

    def start(self):
        try:
            # (listening for incoming peer messages)
            reactor.listenUDP(self.p2p_port, self.p2p_protocol)
            logging.info(f"Verifier {self.verifier_id} P2P listening on port {self.p2p_port}")

            #Signal Server client on an ephemeral port
            self.signal_ephemeral_port = self.get_ephemeral_port()
            reactor.listenUDP(self.signal_ephemeral_port, self.signal_client_protocol)
            logging.info(f"Verifier {self.verifier_id} Signal Server client listening on port {self.signal_ephemeral_port}")

            #set endpoints for the signal server client
            private_endpoint = (self.get_local_ip(), self.signal_ephemeral_port)
            self.signal_client_protocol.set_endpoints(
                server_endpoint=(self.signal_server_ip, self.signal_server_port),
                private_endpoint=private_endpoint
            )

            #start CLI
            cli = VerifierCLI(self)
            stdio.StandardIO(cli)
            logging.info(f"Starting Verifier {self.verifier_id} CLI.")
            reactor.run()
        except Exception as e:
            logging.error(f"An error occurred while starting the Verifier Node: {e}")
            sys.exit(1)

    def get_local_ip(self):
        try:
            #this method connects to an external host to get the local IP address
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def get_ephemeral_port(self):
        #to get the ephemeral port assigned by the OS for the Signal Server client
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(('', 0))
        port = s.getsockname()[1]
        s.close()
        return port

    #allback methods invoked by BaseServer (P2P)
    def handleP2PMessage(self, data, addr):
        self.message_handler.handleP2PMessage(data, addr)

    #allback methods invoked by BaseClient (Signal Server)
    def onConnectSuccess(self, message):
        if message == "VERIFIER_REGISTERED":
            self.prompt.log("Verifier registered with Signal Server successfully.")
        else:
            self.prompt.log(f"Connected successfully: {message}")

    def onConnectError(self, message):
        self.prompt.logError(f"Connection error: {message}")

    def handleSignalServerMessage(self, data, addr):
        
        pass  #implement later

    
    def sendMessageToNode(self, target_id, message):
        #send a message to a specific client or verifier
        if target_id in self.clients:
            info = self.clients[target_id]
            addr = (info['ip'], info['port'])
            msg = f"HELLO from VERIFIER|{self.verifier_id}|{message}"
            self.p2p_protocol.sendMessage(msg, addr)
            self.prompt.log(f"Sent message to client {target_id}.")
            logging.info(f"Sent HELLO message to client {target_id}: {msg}")
        elif target_id in self.verifiers:
            info = self.verifiers[target_id]
            addr = (info['ip'], info['port'])
            msg = f"HELLO from VERIFIER|{self.verifier_id}|{message}"
            self.p2p_protocol.sendMessage(msg, addr)
            self.prompt.log(f"Sent message to verifier {target_id}.")
            logging.info(f"Sent HELLO message to verifier {target_id}: {msg}")
        else:
            self.prompt.logError(f"Target '{target_id}' not known or not connected.")

    def broadcastMessage(self, message):
        #broadcast a message to all connected clients and verifiers
        if not self.clients and not self.verifiers:
            self.prompt.log("No clients or verifiers to broadcast to.")
            return
        msg = f"MSG|{self.verifier_id}|{message}"
        for cid, info in self.clients.items():
            addr = (info['ip'], info['port'])
            self.p2p_protocol.sendMessage(msg, addr)
            logging.info(f"Broadcasted MSG to client {cid}: {msg}")
        for vid, info in self.verifiers.items():
            addr = (info['ip'], info['port'])
            self.p2p_protocol.sendMessage(msg, addr)
            logging.info(f"Broadcasted MSG to verifier {vid}: {msg}")
        self.prompt.log("Broadcasted message to all connected nodes.")

    def queryNode(self, node_id):
        #query a verifier's info from the Signal Server
        msg = f"QUERY_VERIFIER|{node_id}"
        self.signal_client_protocol.transport.write(msg.encode('utf-8'), (self.signal_server_ip, self.signal_server_port))
        self.prompt.log(f"Querying Signal Server for Node '{node_id}'...")
        logging.info(f"Sent QUERY_VERIFIER message: {msg}")

    #methods to handle registrations from Signal Server
    def onVerifierRegisteredPeer(self, verifier_id, verifier_name, ip, port):
        if verifier_id != self.verifier_id:
            self.verifiers[verifier_id] = {'name': verifier_name, 'ip': ip, 'port': port}
            self.prompt.log(f"Registered verifier: {verifier_id} ({verifier_name}) at {ip}:{port}")

    def onVerifierDisconnectedPeer(self, verifier_id):
        if verifier_id in self.verifiers:
            verifier_info = self.verifiers.pop(verifier_id)
            self.prompt.log(f"Verifier disconnected: {verifier_id} ({verifier_info['name']})")

    def onClientRegisteredPeer(self, client_id, client_name, ip, port):
        self.clients[client_id] = {'name': client_name, 'ip': ip, 'port': port}
        self.prompt.log(f"Registered client: {client_id} ({client_name}) at {ip}:{port}")

    def onClientDisconnectedPeer(self, client_id):
        if client_id in self.clients:
            client_info = self.clients.pop(client_id)
            self.prompt.log(f"Client disconnected: {client_id} ({client_info['name']})")

    #methods to be called by BaseServer (Signal Server Protocol)
    def onVerifierRegistered(self, verifier_id, verifier_name, ip, port):
        if verifier_id != self.verifier_id:
            self.onVerifierRegisteredPeer(verifier_id, verifier_name, ip, port)

    def onVerifierDisconnected(self, verifier_id):
        self.onVerifierDisconnectedPeer(verifier_id)

    def onClientRegistered(self, client_id, client_name, ip, port):
        self.onClientRegisteredPeer(client_id, client_name, ip, port)

    def onClientDisconnected(self, client_id):
        self.onClientDisconnectedPeer(client_id)


def main():
    if len(sys.argv) != 6:
        print("Usage: python3 verifier_node.py <verifier_id> <verifier_name> <signal_server_ip> <signal_server_port> <p2p_port>")
        sys.exit(1)
    
    verifier_id = sys.argv[1]
    verifier_name = sys.argv[2]
    signal_server_ip = sys.argv[3]
    
    try:
        signal_server_port = int(sys.argv[4])
        p2p_port = int(sys.argv[5])
    except ValueError:
        print("Error: <signal_server_port> and <p2p_port> must be integers.")
        sys.exit(1)

    node = VerifierNode(verifier_id, verifier_name, signal_server_ip, signal_server_port, p2p_port)
    try:
        node.start()
    except Exception as e:
        logging.error(f"An error occurred while starting the Verifier Node: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
