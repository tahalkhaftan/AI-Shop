"""AI-Shop: a reusable local-model assistant without bundled website data."""
from .assistant import Assistant, resolve_answer
from .knowledge import KnowledgeBase
from .engine import LocalEngine, get_engine
from .errors import AIShopError

__version__ = '0.1.0'
__all__ = ['Assistant', 'KnowledgeBase', 'LocalEngine', 'get_engine', 'AIShopError', 'resolve_answer']
