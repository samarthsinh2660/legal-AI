"""The process that does the work.

`src/api/` writes a job row and returns; this claims it and runs it. The
split is what makes a deploy, a crash or a closed laptop cost nothing: the
run belongs to a row in `runs`, not to an HTTP request or to one process's
memory.

The dependency runs one way, as it does for `legal_ai`: the worker imports
the API's repositories to read and write the same tables, and nothing in
`api/` imports anything here. A worker needs a connection string and a model
key -- no inbound port, no broker, no shared filesystem -- which is what
lets it live on another machine.
"""
