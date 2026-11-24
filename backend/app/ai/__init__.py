"""Provider-independent AI layer used by contract reviews.

Provider-specific code lives in its own module (currently ``groq.py``); the
rest of the application only depends on ``base.AIProvider`` and the errors in
``errors.py``.
"""
