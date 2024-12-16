# common.py

def unpack_datagram_args(func):
    """
    Decorator to unpack datagram arguments before passing to the handler.
    Passes the message type as the first argument.
    """
    def wrapper(self, addr, data):
        parts = data.split('|')
        msgtype = parts[0]
        return func(self, addr, msgtype, *parts[1:])
    return wrapper
