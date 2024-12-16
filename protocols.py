# protocols.py

from twisted.internet.protocol import DatagramProtocol
from twisted.internet import task
from common import unpack_datagram_args
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class BaseServer(DatagramProtocol):
    """
    BaseServer handles peer-to-peer (P2P) communication.
    """
    def __init__(self, node):
        super().__init__()
        self.node = node  #reference to VerifierNode or ClientNode
        self.peers = {}    #key: peer_id, Value: peer info dict

    def datagramReceived(self, data, addr):
        data = data.decode('utf-8').strip()
        logger.info(f"BaseServer received data from {addr}: {data}")
        self.node.handleP2PMessage(data, addr)

    def sendMessage(self, message, addr):
        self.transport.write(message.encode('utf-8'), addr)
        logger.info(f"BaseServer sent message to {addr}: {message}")


class BaseClient(DatagramProtocol):
    """
    BaseClient handles communication with the Signal Server.
    """
    def __init__(self, message_type='CONNECT_CLIENT', node_id=None, node_name=None, node_type='CLIENT', node=None):
        super().__init__()
        self.message_type = message_type  #'CONNECT_CLIENT' or 'CONNECT_VERIFIER'
        self.node_id = node_id
        self.node_name = node_name
        self.node_type = node_type  #'CLIENT' or 'VERIFIER'
        self.node = node  #reference to VerifierNode or ClientNode
        self.server_ip = None
        self.server_port = None
        self.private_ip = None
        self.private_port = None

    def set_endpoints(self, server_endpoint, private_endpoint):
        self.server_ip, self.server_port = server_endpoint
        self.private_ip, self.private_port = private_endpoint
        #now, send the connect message
        self.sendConnectMessage()

    def sendConnectMessage(self):
        if self.message_type == 'CONNECT_CLIENT':
            if not self.node_id or not self.node_name:
                logging.error("BaseClient: node_id and node_name must be provided for CONNECT_CLIENT")
                return
            msg = f'CONNECT_CLIENT|{self.node_id}|{self.node_name}'
        elif self.message_type == 'CONNECT_VERIFIER':
            if not self.node_id or not self.node_name:
                logging.error("BaseClient: node_id and node_name must be provided for CONNECT_VERIFIER")
                return
            msg = f'CONNECT_VERIFIER|{self.node_id}|{self.node_name}'
        else:
            logging.error(f"BaseClient: Unknown message type {self.message_type}")
            return

        self.transport.write(msg.encode('utf-8'), (self.server_ip, self.server_port))
        logger.info(f"BaseClient: Sent {self.message_type} message to {(self.server_ip, self.server_port)}: {msg}")

    def datagramReceived(self, data, addr):
        data = data.decode('utf-8').strip()
        logger.info(f"BaseClient received data from {addr}: {data}")
        if data.startswith('RESP'):
            self.handleResponse(addr, data)
        elif data.startswith('HEART'):
            self.handleHeartbeat(addr)
        else:
            #pass other messages to the node for handling
            self.node.handleSignalServerMessage(data, addr)

    @unpack_datagram_args
    def handleResponse(self, addr, msgtype, *args):
        if msgtype != 'RESP':
            logger.error(f"BaseClient: Unexpected message type {msgtype} in handleResponse.")
            return

        #handle RESP messages: RESP|<status>|<message>
        if len(args) < 2:
            logging.error(f"BaseClient: Invalid RESP message from {addr}: {args}")
            return
        status, detailed_message = args[0], args[1]
        if status == 'SUCCESS':
            #handle success
            logging.info(f"BaseClient: Successfully connected. Server response: {detailed_message}")
            if self.node:
                self.node.onConnectSuccess(detailed_message)
        elif status == 'ERROR':
            #handle error
            logging.error(f"BaseClient: Error connecting. Server response: {detailed_message}")
            if self.node:
                self.node.onConnectError(detailed_message)
        else:
            logging.error(f"BaseClient: Unknown status {status} in response.")

    def handleHeartbeat(self, addr):
        #respond to heartbeat to maintain connection
        self.transport.write('HEART'.encode('utf-8'), addr)
        logger.info(f"BaseClient: Responded with HEART to {addr}")
