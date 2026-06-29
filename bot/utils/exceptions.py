class BotError(Exception):
    """Base class for bot exceptions"""
    pass

class AuthError(BotError):
    """Raised during authentication failures"""
    pass

class ForwardError(BotError):
    """Raised during forwarding failures"""
    pass

class PeerError(BotError):
    """Raised when peer resolution fails"""
    pass
