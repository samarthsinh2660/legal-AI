"""Talking to a model server instead of loading the model.

A worker that loads the embedder and the cross-encoder itself is 1453 MB
resident, of which 1290 MB is the model stack and 163 MB is the actual
work. Every extra worker pays for an identical copy, and 684 MB of that
copy is torch and sentence-transformers rather than weights.

Loaded once behind HTTP, a worker is 163 MB and the GPU that makes
reranking eight times faster is bought once rather than per worker.
"""
