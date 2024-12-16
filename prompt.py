# prompt.py

import sys

class ColoredPrompt:
    """
    Simple prompt handler. Extend this class to add color or other formatting as needed.
    """
    def __init__(self, prompt='> '):
        self.prompt = prompt
        # Configure logging if not already configured
        if not sys.modules['logging'].getLogger().hasHandlers():
            import logging
            logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    def log(self, message):
        print(message)

    def logError(self, message):
        print(f"ERROR: {message}", file=sys.stderr)

    def logChatMsg(self, sender_id, message):
        print(f"[{sender_id}] {message}")

    def _writePrompt(self):
        print(self.prompt, end='', flush=True)
