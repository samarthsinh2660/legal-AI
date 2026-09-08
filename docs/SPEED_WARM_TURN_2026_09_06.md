# What a warm turn spends, and on what

The earlier study on this date fixed the cold start — the first question
after a worker boots went from 108s to 32s. This one asks the next
question: where do the remaining **18–40 seconds** go?

Measured in-process against the real corpus and the real model API, by
wrapping the seams rather than editing `src/`.

## The three-way split

    question                          research   plan   retrieval   analyst   total
    punishment under s.138              18.0s    6.8s     11.2s     12.5s    30.4s
    what does s.139 presume             15.2s    3.6s     11.5s      4.1s    19.3s
    can a company be prosecuted, s.141  21.3s   11.4s      9.9s      4.6s    25.9s
    ─────────────────────────────────────────────────────────────────────────────
    mean                                         7.3s     10.9s      7.1s    25.2s
                                                  29%       43%       28%

**Retrieval is the largest share, and it is not a model call.** That
corrects what I said earlier in the day — I had assumed the remainder was
"two model calls" without measuring it.

## Inside the 11 seconds of retrieval

    search_metadata      0.0s
    search_keyword       0.0s
    search_vector        0.0s
    best_passages        0.1s
    rerank_candidates    3.9s   <- 97%
    apply_type_floor     0.0s
    build_evidence       0.0s
    ─────────────────────────
    hybrid_search        4.0s

Postgres is not the problem: keyword, vector and metadata search together
are under a tenth of a second against 35,601 sections and 332,025 chunks.

`hybrid_search` runs **twice** per angle — the statutory rewrite and the
reader's own words are searched separately and fused, which is what took
retrieval MRR from 0.311 to 0.469. So the turn pays the reranker twice:
**~8 seconds of a ~25 second turn is one CPU cross-encoder.**

## What drives the reranker

50 real passages, mean 1761 characters, `ms-marco-MiniLM-L-12-v2`:

    shipped: n=50, max_len=512, CPU            5.16s

    n=30                                       3.17s
    n=20                                       2.06s
    n=10                                       0.95s

    max_len=256                                2.48s
    max_len=128                                1.13s

    MiniLM-L-6  (half the layers)              2.74s
    TinyBERT-L-2                               0.22s

Cost is roughly linear in each of layers × candidates × sequence length.
Every one of those trades against retrieval quality, and `evals/` is what
would have to settle the trade.

## Except one, which trades against nothing

    MiniLM-L-12, 50 passages, cpu     5.12s
    MiniLM-L-12, 50 passages, cuda    0.61s     8.4x, using 142 MB of VRAM

Same model, same shortlist, same shipped configuration:

    largest score difference: 1.14e-05
    ranking identical:        True
    top-10 identical:         True

The difference is float precision, not judgement. **This is the only lever
here that costs no accuracy at all**, and it would take ~8s out of a ~25s
turn — call it 25s to 18s, or a 28% cut, for a configuration change.

### The model server was built for this, and it is now the place to put a GPU

Putting CUDA in the worker image would mean a GPU per worker and ~2.7 GB of
driver libraries back in an image just cut from 5.77 GB to 1.53. The models
went behind two TEI containers instead (2026-09-06), so a worker is 148 MB
and there is one place a GPU has to go.

That move is roughly latency-neutral on CPU -- 4.73s in-process against
5.07s over HTTP -- and it is what makes the 0.61s reachable at all.

### What it needs

This machine has an RTX 3050 Laptop (compute 8.6, 4 GB), and 142 MB is all
the reranker wants. Two things stand between that and the container:

1. `docker run --gpus all` fails here — `nvidia-container-toolkit` is not
   installed. That is a host package and a deployment decision.
2. The worker image is built CPU-only on purpose. The Dockerfile already
   takes `--build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu121`,
   which is the whole change — at the cost of the ~2.7 GB of CUDA
   libraries that were deliberately cut out of it.

A worker run directly on a host with a GPU needs neither: the development
virtualenv already reports `cuda=True`.

The embedder would benefit too, and it is the larger of the two models in
memory — but it is only called once or twice per turn, so it is not where
the seconds are.

## What is left after that

Roughly 14 seconds of model API: ~7s planning and ~7s analysing. Both are
single calls on a free-tier key, and neither has an obvious structural fix
that does not change what the answer is made of. The rate-limit backoff on
that key is a separate and larger cost when the quota is out; see the
companion note from the same date.
