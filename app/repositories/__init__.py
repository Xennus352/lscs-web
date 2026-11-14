"""Database access layer.

Routers should orchestrate requests and call these helpers instead of writing
SQL inline. Keeping the MySQL statements here makes it possible to change the
storage details without touching the HTTP/API layer.
"""
