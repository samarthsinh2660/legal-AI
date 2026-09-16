# Deploying

Two machines:

    main server      postgres, neo4j, api, frontend
    uniun-server2    worker, embedder, reranker     (docker-compose.worker.yml)

The worker needs to reach Postgres and Neo4j on the main server. The API
needs to reach the embedder and reranker on uniun-server2 (`/search` embeds).
Nothing else crosses between them.

## Before anything: what changed since the server was last deployed

The server runs code from before the worker. Three things break if they are
not upgraded together:

- `POST /threads/{id}/messages` now returns a run id, not an answer. Old
  frontend + new API = no answers shown. Deploy API and frontend together.
- The API only queues a question. With no worker running, every question
  sits "queued" forever.
- The API creates the `runs` tables at startup. Start the API before the
  worker.

Deploy from a branch that has every commit. `good-law` has three commits
`main` does not (correspondence tables, which code governs, the worker crash
fix) -- merge them first:

    git log --oneline main..good-law    # must print nothing before you deploy main

## 1. Back up the main server

    docker exec legal-ai-postgres pg_dump -U legal_ai -Fc legal_ai > backups/$(date +%Y%m%d-%H%M)/postgres.dump
    docker compose stop neo4j
    docker run --rm -v legal-ai_legal_ai_neo4j_data:/data -v $PWD/backups/<dir>:/b alpine tar czf /b/neo4j_data.tar.gz -C /data .
    docker compose start neo4j

Check the volume name with `docker volume ls`. Copy both files off the box.

## 2. Open the network, narrowly

On the main server, allow uniun-server2 only:

    sudo ufw allow from <server2-ip> to any port 5433 proto tcp   # postgres
    sudo ufw allow from <server2-ip> to any port 7688 proto tcp   # neo4j bolt

On uniun-server2, allow the main server only:

    sudo ufw allow from <main-ip> to any port 8085 proto tcp      # embedder
    sudo ufw allow from <main-ip> to any port 8086 proto tcp      # reranker

Docker publishes ports past ufw's INPUT rules. If the machines share a
private network (or Tailscale), bind the published ports to that address
instead, e.g. `"10.0.0.5:5433:5432"`, so nothing is on the public interface.

Test from uniun-server2 before going further:

    pg_isready -h <main-ip> -p 5433
    nc -zv <main-ip> 7688

## 3. uniun-server2: models and worker

    git clone <repo> && cd legal-AI && git checkout <deploy branch>
    cp .env.example .env    # or write it by hand

`.env` needs:

    DB_HOST=<main-ip>
    POSTGRES_USER=... POSTGRES_PASSWORD=... POSTGRES_DB=legal_ai POSTGRES_PORT=5433
    NEO4J_PASSWORD=... NEO4J_BOLT_PORT=7688
    GEMINI_API_KEY=...

No JWT secret: the worker never sees a request.

GPU? `nvidia-smi` on the host. If there is one, install
nvidia-container-toolkit, confirm `docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi`,
then in `docker-compose.worker.yml` swap both images to the CUDA tag and
uncomment `deploy`. Reranking 50 passages measured 5.12s CPU vs 0.61s GPU.

Start the models first; the first start downloads ~1 GB of weights:

    docker compose -f docker-compose.worker.yml up -d embedder reranker
    curl -fsS localhost:8085/health && curl -fsS localhost:8086/health

Do not start the worker yet -- the API must create its tables first (step 4).

## 4. Main server: code

    git pull && git checkout <deploy branch>

Add to `.env`:

    LEGAL_AI_EMBED_URL=http://<server2-ip>:8085
    LEGAL_AI_RERANK_URL=http://<server2-ip>:8086

Start only what lives here. `--no-deps` stops compose starting local model
servers and a local worker because the api `depends_on` them:

    docker compose up -d postgres neo4j
    docker compose up -d --build --no-deps api
    curl localhost:8000/health

If an old worker/embedder/reranker container runs on this box, stop it:
two workers on one Gemini key rate-limit each other.

Rebuild and redeploy the frontend at the same moment, with
`NEXT_PUBLIC_API_BASE_URL` pointing at the API.

Now start the worker on uniun-server2:

    docker compose -f docker-compose.worker.yml up -d --build worker
    docker compose -f docker-compose.worker.yml logs -f worker

## 5. Data: bring the corpus up to date

Run these against the main server's databases, in this order. Each is safe
to stop and re-run. Run them from uniun-server2 (it already reaches both
stores) or from a laptop over an SSH tunnel:

    ssh -L 5433:localhost:5433 -L 7688:localhost:7688 <main-server>

with `DATABASE_URL` and `NEO4J_URI` exported to point at the tunnel/host.

| # | Command | Why this order | Cost |
|---|---------|----------------|------|
| 1 | `python -m scripts.section_collection.complete_missing_sections_from_pdf` | fills empty section bodies; links below need the sections to exist | Gemini calls, minutes |
| 2 | `python -m scripts.relink_section_citations --dry-run`, then without | re-resolves IPC/CrPC/etc. links from judgment text | no model, ~200 judgments/s |
| 3 | `python -m scripts.ingest_correspondence --fetch --dry-run`, then without `--dry-run` | creates `section_correspondence` (IPC↔BNS, CrPC↔BNSS, IEA↔BSA); expect ~1,256 pairs | downloads 3 PDFs |
| 4 | `python -m scripts.classify_treatments --limit 500` | treatments for good-law; repeat until it writes nothing | Gemini quota -- shares the key with the live worker, run off-peak |
| 5 | `python -m scripts.rechunk_judgments --dry-run`, then without | fixes year-as-paragraph chunks; pinpoints depend on it | re-embeds ~175k chunks |

Step 5 is the long one. Point `LEGAL_AI_EMBED_URL` at a GPU embedder, or
leave it unset on a machine whose torch sees CUDA, which loads the model
in-process. On CPU TEI expect many hours; it resumes where it stopped.

Steps 2 and 3 are needed before "which code governs" and IPC-linked
judgments work at all. 4 and 5 improve answers but nothing breaks without
them.

## 6. Check it

- `curl <api>/health` -- postgres and neo4j ok.
- Ask a question in the UI. It should go queued → running → answered in the
  progress steps. Stuck on queued means no worker is claiming: check the
  worker logs and that it reaches Postgres.
- Ask a dated IPC question ("theft in March 2023") and a post-July-2024 one;
  the answer should say which code governs.
- Stop the worker mid-answer (`docker compose -f docker-compose.worker.yml
  restart worker`): the run should be picked up again, not left "running".
- In Postgres: `SELECT status, count(*) FROM runs GROUP BY 1;`

Never run the test suite against the production database: a test fixture
queues runs, and the live worker will answer them into real threads.

## Rolling back

    docker compose stop api
    docker exec -i legal-ai-postgres pg_restore -U legal_ai -d legal_ai --clean --if-exists < postgres.dump

and untar the Neo4j backup into its volume with neo4j stopped, then deploy
the previous commit of API and frontend together.
