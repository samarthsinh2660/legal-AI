"""The HTTP service. Deliberately thin -- the reasoning lives in the graph.

`app` is imported lazily by the caller rather than re-exported here, so
importing `api` does not pull FastAPI into a process that only
wanted the package.
"""
