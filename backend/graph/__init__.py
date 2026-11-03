"""Model calls and the LangGraph turn graph (B5 to B9).

Nothing in this package imports Django (B4). The model SDKs (LangChain, google-genai) load only
when the first real model client is built, so importing it stays cheap at startup (B10).
"""
