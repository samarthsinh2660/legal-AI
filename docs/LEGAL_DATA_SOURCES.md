# Indian Legal AI --- Data Sources, Searchable Corpora, APIs, Open-Source Repositories & Research

## 1. Purpose

This document is the reference catalog for the AI/data layer of the
Indian Legal Intelligence Platform.

It answers:

-   Where can we obtain Indian legal data?
-   Which sources are primary/authoritative?
-   Which sources are searchable?
-   Which sources have APIs?
-   Which sources can be wrapped as AI tools?
-   Which repositories provide bulk corpora?
-   Which datasets are useful for RAG, GraphRAG and evaluation?
-   Which research papers are closest to our architecture?
-   What should be static, dynamic and active data?

------------------------------------------------------------------------

# 2. Source-of-Truth Hierarchy

We should separate **authority** from **technical convenience**.

``` text
TIER 1 — PRIMARY / AUTHORITATIVE

Government legislation
Official court repositories
Official court orders/judgments
India Code
Supreme Court / High Court / eCourts sources
        |
        v

TIER 2 — PROGRAMMATIC ACCESS / MIRRORS

Bharat Courts
Indian Kanoon API
Open AWS court archives
Other verified data-access projects
        |
        v

TIER 3 — RESEARCH DATASETS

ILDC
LawSum
NyayaAnumana
IMLJD
InLegalBERT corpus
Other Hugging Face / academic datasets
```

A research dataset or third-party API should not automatically be
treated as the legal authority.

For every document retained in our system, preserve:

``` text
source_name
source_url
document_id
court
case_number / CNR
date
citation
retrieved_at
source_type
license / usage terms
```

------------------------------------------------------------------------

# 3. India Code --- Primary Legislation Source

**IN USE** --- 860 Acts and 35,601 sections in the corpus came from here.

## Official

-   Website: https://indiacode.gov.in/
-   REST API (DSpace 9): https://indiacode.gov.in/server/api
-   Search: `…/server/api/discover/search/objects?query=<terms>`

## The site moved, and it broke our ingestion (verified 2026-09-02)

India Code migrated from `indiacode.nic.in` to `indiacode.gov.in` and
**renumbered every handle**. Consequences, all measured:

-   The old host 404s. `scripts/ingest_india_code.py`,
    `ingestion/india_code/scraper.py`, `section_body.py` and
    `section_collection/ingest_spent_acts.py` all fail against the live
    site. Re-running any India Code ingestion today yields nothing.
-   Handles changed: the Negotiable Instruments Act was
    `123456789/2189`, its sections now sit under ids like
    `123456789/535860`. **Every provenance URL on all 35,601 stored
    sections points at a dead host**, which is why `agents/draft.py`
    withholds those links rather than showing a reader a 404.
-   The new host serves 502 to our `PramanaAI-Ingestion/0.1` User-Agent
    and 200 to a browser one. It is filtering on UA.

Repairing this means re-mapping handles through the new REST API. Until
then India Code is readable by hand and not by us.

## What it does NOT hold

The three repealed criminal codes have no section structure here. The IPC
and the Indian Evidence Act exist as **PDF only** (in the `Repeal`
community); the **Code of Criminal Procedure, 1973 is absent entirely** ---
browsing `Repeal > CENTRAL` by title returns the 1861, 1872, 1882 and 1898
Codes and 24 amendment Acts, and stops. See §9a for the source we use
instead.

## What we want

``` text
Act
Section
Subsection
Definition
Proviso
Explanation
Schedule
Rule
Regulation
Amendment
Repeal
```

## AI use

India Code should feed the **Static Knowledge Layer** and also a
controlled **Dynamic Legislation Search Tool**.

Suggested tools:

``` text
search_india_code()
get_act()
get_section()
get_amendments()
get_related_legislation()
```

## Important

India Code should be treated as the preferred source for the statute
text. Research datasets can help build schemas or benchmarks, but the
current statute should be checked against India Code.

------------------------------------------------------------------------

# 3a. The repealed criminal codes --- IPC, CrPC

**INGESTED 2026-09-02** --- IPC 574 sections (`act:ipc-1860`), CrPC 525
(`act:crpc-1973`), `source_type="research"`. IPC s.304B is absent: empty
body in the source. The Indian Evidence Act is still missing.

Previously: we held only their 2023 replacements (Bharatiya Nyaya
Sanhita 358 sections, Nagarik Suraksha Sanhita 531, Sakshya Adhiniyam 170)
and none of the codes they replaced. This matters because **an offence
committed before 1 July 2024 is still charged under the old code**, so
these are live law, not history. `retrieval/coverage.py` tells a reader so
when a question names one.

## Source used

https://github.com/civictech-India/Indian-Law-Penal-Code-Json

``` text
ipc.json    575 sections   chapter · section · title · full text
crpc.json   525 sections   the CrPC, which India Code does not hold at all
```

Verified before recommending:

-   **Cross-validated against a second compilation.** devgan.in lists 575
    IPC sections; this dataset lists 575; the two agree on every section
    number, with no entry unique to either.
-   Letter-suffixed sections are handled: 498A, 376A, 120B, 153AA all
    present with correct titles.
-   Text is verbatim. s.302 reads "Whoever commits murder shall be
    punished with death, or imprisonment for life, and shall also be
    liable to fine." s.420, s.124A, s.375 and s.511 also check out.
-   1 empty body in 575; median body 323 characters.

**Two conditions before using it.** It is a community compilation, so it
is `source_type="research"` like Indian Kanoon --- never `primary`. And
**the repository carries no LICENSE file**; the statutory text itself is
free to reproduce under s.52(1)(q) of the Copyright Act, but the
compilation's terms are unstated.

## Rejected

https://devgan.in/all_sections_ipc.php --- the index returns 575 sections
with titles, but **every individual section page returns HTTP 500**
(checked s.1, s.302, s.375, s.420, s.498A, with a browser UA, referer and
gzip). Numbers and titles with no body would put retrievable stubs in the
corpus that look like law and contain none. A private aggregator, so
`research` tier at best if the pages return.

------------------------------------------------------------------------

# 4. Supreme Court of India

## Official search

-   Supreme Court Reports / Judgment Search:
    https://scr.sci.gov.in/scrsearch/

The official portal supports keyword, phrase, free-text, Act, section
and other search/filter approaches.

## What we want

``` text
Judgment
Order
Case number
CNR
Case title
Petitioner
Respondent
Bench
Judge(s)
Decision date
Neutral citation
Citation
Acts
Sections
Disposition
Document PDF
```

## Important official-source principle

The official Supreme Court/court repository is the source to verify the
final legal document.

For bulk historical ingestion, open court-data repositories can be used
as an engineering source, while retaining provenance back to the
underlying court system.

------------------------------------------------------------------------

# 5. Supreme Court Bulk Corpus --- Vanga

**IN USE** --- 13,131 judgments. Bundled year tars, so a citation gets
no direct link; see `agents/draft.py`.

## Repository

https://github.com/vanga/indian-supreme-court-judgments

## Data

The repository provides code for obtaining Indian Supreme Court
judgments and publishes a bulk AWS Open Data corpus.

Current repository documentation describes:

``` text
1950 → present
~35K English judgments
regional-language versions
PDFs
raw JSON metadata
structured Parquet metadata
```

Metadata includes fields such as:

``` text
title
petitioner
respondent
description
judge
author_judge
citation
case_id
CNR
decision_date
disposal_nature
court
available_languages
neutral citation
```

The repository states that the dataset is CC-BY-4.0.

## Best use for us

``` text
Vanga SC corpus
      |
      v
Bulk historical ingestion
      |
      v
Canonical legal document store
      |
      +--> vector index
      |
      +--> legal knowledge graph
```

Do not make this our only live-search mechanism.

------------------------------------------------------------------------

# 6. High Courts --- Official / eCourts Infrastructure

**NOT USED.** No code reaches eCourts.

## eCourts India

-   https://ecourts.gov.in/
-   https://services.ecourts.gov.in/

The eCourts Services portal supports case-status and other court
searches. Many live workflows include CAPTCHA and portal-specific
navigation.

## Searchable information

Depending on the court/service:

``` text
Case number
Filing number
Party
Advocate
CNR
Case history
Orders
Judgments
Cause lists
```

------------------------------------------------------------------------

# 7. High Court Bulk Corpus --- Vanga

**IN USE** --- part of the same 13,131.

## Repository

https://github.com/vanga/indian-high-court-judgments

## Coverage

The repository currently describes an open corpus across **25 Indian
High Courts**, with court/date partitions and public AWS storage.

Current documentation describes:

``` text
~17.8M judgments
~1.25 TiB across S3 tar archives
PDFs
raw metadata JSON
structured metadata Parquet
```

The repository says the dataset is CC-BY-4.0 and that the corpus is
scraped primarily from the eCourts judgments portal, with a growing
portion backfilled from the eCourts mobile API.

## Court coverage includes

``` text
Gujarat HC
Delhi HC
Bombay HC
Karnataka HC
Madras HC
...
```

Gujarat High Court archive code listed by the repository:

``` text
24~17
```

## Best use

For our V1:

``` text
Supreme Court
+
Gujarat High Court
```

Use the bulk corpus for static ingestion and evaluation, while retaining
the original provenance fields.

------------------------------------------------------------------------

# 8. Bharat Courts --- Programmatic Court Access

**IN USE** --- the ingestion path for judgments.

## Repository

https://github.com/iamshouvikmitra/bharat-courts

## Why this is important

Bharat Courts is an SDK rather than merely a static dataset.

It currently provides programmatic interfaces for:

``` text
Supreme Court
25 High Courts
700+ District Courts
```

The repository describes:

-   judgment search
-   case search
-   orders
-   cause lists
-   district-court discovery
-   recent Supreme Court judgments
-   historical court archives
-   PDF downloads
-   CAPTCHA/session handling

It provides a Python API and CLI and can be installed as an AI-agent
skill.

## Recommended AI abstraction

``` text
Research Agent
     |
     +--> search_court_cases()
     +--> search_judgments()
     +--> get_order()
     +--> get_judgment()
     +--> get_cause_list()
     +--> search_district_court()
```

The implementation can initially use Bharat Courts underneath these
internal tools.

## Important limitation

The repository itself says there is no single official unified API for
the Indian court system and that live portal access often requires
CAPTCHA/session handling.

Therefore:

``` text
Bharat Courts
=
programmatic access layer

NOT
=
new legal authority
```

The underlying official court/eCourts source remains the authority.

------------------------------------------------------------------------

# 9. Indian Kanoon API

**IN USE** --- `tools/judgments.discover_judgments`. `source_type="research"`,
not primary, and the only judgments that get a per-document link.

## Official API documentation

https://api.indiankanoon.org/documentation/

## Terms

https://api.indiankanoon.org/terms/

## Pricing

https://api.indiankanoon.org/pricing/

## Available operations

The API exposes:

``` text
Search
Document
Court copy / original document
Document fragments
Document metadata
```

Endpoints documented by Indian Kanoon include:

``` text
/search/
/doc/<docid>/
/origdoc/<docid>/
/docfragment/<docid>/
/docmeta/<docid>/
```

The service supports authenticated programmatic access.

## Important terms

Indian Kanoon's terms explicitly cover use in RAG/fine-tuning scenarios
and require prominent attribution when its results/documents are used in
products.

Therefore:

``` text
Indian Kanoon API
      |
      v
Dynamic Research Tool
      |
      v
Evidence
```

but we must implement its attribution and contractual requirements.

Do not silently copy the data into our permanent authoritative corpus
without checking the applicable terms.

------------------------------------------------------------------------

# 10. District Courts

**NOT USED.**

## Primary infrastructure

-   eCourts Services: https://services.ecourts.gov.in/

## Programmatic access

Bharat Courts:

https://github.com/iamshouvikmitra/bharat-courts

Its DistrictCourtClient supports court discovery and searches across
hundreds of district/subordinate courts.

Example conceptual flow:

``` text
State
  ↓
District
  ↓
Court Complex
  ↓
Establishment
  ↓
Case / Party / CNR
  ↓
Orders / Case history
```

This is useful for the Dynamic Researcher.

------------------------------------------------------------------------

> **Sections 11-21 are research datasets and models nothing in this
> repository reads.** They were surveyed during planning and are kept as a
> record of what was considered and why it was not taken. Do not read them
> as a description of the system.

# 11. OpenJustice India

**NOT USED.**

## Website

https://openjustice-in.github.io/

OpenJustice India documents Indian judicial-data projects, including
case/hearing records from many High Courts and datasets used in
legal-data research.

It is useful as a **research/data-discovery directory**, but access
conditions differ by dataset. Check the current access form/contact and
terms before using data in a product.

------------------------------------------------------------------------

# 12. Indian Court Decisions --- Large Hugging Face Dataset

**NOT USED.**

## Dataset

https://huggingface.co/datasets/overthelex/indian-court-decisions

The current dataset describes:

``` text
14.6M+ court decisions
Supreme Court
25 High Courts
Full text
Metadata
Outcome labels
```

It can be valuable for:

``` text
retrieval experiments
classification
large-scale evaluation
NLP experimentation
```

However, before production use:

``` text
verify provenance
verify licensing
verify freshness
verify duplicate sources
verify whether the source text can legally be redistributed
```

This is a research/data resource, not automatically our legal authority.

------------------------------------------------------------------------

# 13. Indian Legal Records & Judgments Corpus

**NOT USED.**

## Hugging Face

https://huggingface.co/datasets/LH2-data-labs/indian-legal-records

The dataset currently describes a very large structured corpus covering:

``` text
Supreme Court
25 High Courts
600+ District/Subordinate Courts
Tribunals
```

with an AI-enrichment layer.

Potential use:

``` text
large-scale research
benchmark generation
retrieval experiments
metadata experiments
```

Again, verify provenance and licensing before using it in production.

------------------------------------------------------------------------

# 14. KanoonGPT Indian Case Laws

**NOT USED.**

## Hugging Face

https://huggingface.co/datasets/KanoonGPT/indian-case-laws

The dataset describes rolling coverage from:

``` text
1950 → 2026
Supreme Court
25 High Courts
```

It is intended for AI/legal research use.

Potential use:

``` text
research
RAG experiments
benchmarking
structured legal search
```

Before product use, verify the dataset's current license, source
provenance and redistribution terms.

------------------------------------------------------------------------

# 15. IMLJD --- Indian Legal Multi-Judgment Dataset

**NOT USED.**

The IMLJD project is relevant to our GraphRAG work because it combines
Indian judgment data with structured legal relationships/knowledge-graph
research.

Use it primarily as:

``` text
GraphRAG research
KG schema inspiration
evaluation
```

Research/reference:

Search: https://arxiv.org/ for: "IMLJD Indian legal judgments knowledge
graph"

The most important lesson from this line of research is that Indian
legal judgments can be represented as entities + relationships rather
than only vector chunks.

------------------------------------------------------------------------

# 16. ILDC --- Indian Legal Documents Corpus

**NOT USED.**

## GitHub

https://github.com/Exploration-Lab/CJPE

## ACL paper

https://aclanthology.org/2021.acl-long.313/

ILDC contains about:

``` text
35K Supreme Court cases
```

and is annotated for court judgment prediction and explanation.

The dataset/software is CC-BY-NC according to the repository, so it is
particularly useful for **research/evaluation**, not as a default
commercial production corpus.

## Best use

``` text
evaluation
legal reasoning experiments
explainability
model benchmarking
```

------------------------------------------------------------------------

# 17. NyayaAnumana / INLegalLlama

**NOT USED.**

## Paper

https://arxiv.org/abs/2412.08385

## ACL Anthology

https://aclanthology.org/2025.coling-main.738/

The paper describes **702,945 preprocessed Indian legal cases**
spanning:

``` text
Supreme Court
High Courts
Tribunals
District Courts
Daily Orders
```

It also introduces INLegalLlama, a legal-domain language model.

## Best use

``` text
model research
legal classification
judgment prediction research
large-scale evaluation
```

It should not automatically become our production knowledge source.

------------------------------------------------------------------------

# 18. InLegalBERT

**NOT USED.**

## Hugging Face

https://huggingface.co/law-ai/InLegalBERT

## GitHub

https://github.com/Law-AI/pretraining-bert

The project describes a corpus of roughly:

``` text
5.4M Indian legal documents
1950 → 2019
~27GB raw text
```

from Supreme Court and High Court sources.

The pretrained model is useful for:

``` text
legal embeddings experiments
classification
reranking experiments
legal NLP
semantic similarity
```

We should benchmark it rather than assume that a legal-domain encoder
automatically beats modern general embeddings.

------------------------------------------------------------------------

# 19. LawSum

**NOT USED.**

LawSum is an Indian Supreme Court judgment dataset intended for legal
summarization research.

Use it for:

``` text
summarization evaluation
judgment-structure experiments
legal NLP
```

Search/reference: https://aclanthology.org/

Query: "LawSum Indian Supreme Court judgments"

------------------------------------------------------------------------

# 20. Existing Legal Knowledge-Graph Research

## IBM --- Constructing a Knowledge Graph from Indian Legal Domain Corpus

https://research.ibm.com/publications/constructing-a-knowledge-graph-from-indian-legal-domain-corpus

Published at ESWC 2022.

The work uses:

``` text
Indian legal judgments
+
NyOn / Nyaya Ontology
+
Entity extraction
+
Relation extraction
+
Triple construction
+
RDF knowledge graph
```

This is highly relevant to our **Static Knowledge Graph**.

------------------------------------------------------------------------

# 21. Indian Legal Ontology --- NyOn

The IBM work uses the Nyaya Ontology (NyOn) to conceptualize Indian
legal entities/relationships.

This is useful when designing our graph schema:

``` text
Case
Court
Judge
Party
Statute
Section
Legal concept
Citation
```

We should study the ontology before inventing our own graph vocabulary.

------------------------------------------------------------------------

# 22. Hybrid RAG + Knowledge Graph + Agentic Orchestration

## Paper

https://arxiv.org/abs/2602.23371

Title:

**Domain-Partitioned Hybrid RAG for Legal Reasoning: Toward Modular and
Explainable Legal AI for India**

The architecture described in the paper combines:

``` text
Specialized RAG pipelines
+
Legal Knowledge Graph
+
LLM-driven agentic routing
```

The knowledge graph contains relationships among:

``` text
cases
statutes
IPC sections
judges
citations
```

The reported proof-of-concept benchmark showed stronger results for the
hybrid architecture than its RAG-only baseline.

This paper is one of the closest references to our intended
architecture.

------------------------------------------------------------------------

# 23. Falkor-IRAC

## Paper

https://arxiv.org/abs/2605.14665

Title:

**Falkor-IRAC: Graph-Constrained Generation for Verified Legal Reasoning
in Indian Judicial AI**

This work is particularly relevant to our:

``` text
Analyst
+
Verification
+
Knowledge Graph
```

architecture.

It represents judgments using:

``` text
Issue
Rule
Analysis
Conclusion
```

plus:

``` text
precedent relationships
statutory references
procedural state
```

It introduces a Verifier Agent that checks whether generated claims have
supporting paths in the graph.

The key concept for us:

``` text
Generated claim
      |
      v
Can supporting legal path be found?
      |
   +--+--+
   |     |
  yes    no
   |     |
 accept  reject / research again
```

This is an excellent reference for our Verification Agent.

------------------------------------------------------------------------

# 24. Research Themes We Should Follow

The research landscape around Indian legal AI can be grouped into:

``` text
1. Legal document retrieval
2. Legal semantic search
3. Legal summarization
4. Legal entity extraction
5. Legal relation extraction
6. Legal knowledge graphs
7. RAG
8. Hybrid RAG
9. GraphRAG
10. Legal reasoning
11. Judgment prediction
12. Citation prediction / citation retrieval
13. Precedent analysis
14. Explainability
15. Verification / grounded generation
16. Agentic legal research
```

Our project mainly belongs to:

``` text
Legal Retrieval
+
Knowledge Graphs
+
Hybrid RAG
+
Agentic Research
+
Claim/Citation Verification
```

------------------------------------------------------------------------

# 25. Source-to-Layer Mapping

  ---------------------------------------------------------------------------------------------------------
  Source                       Static       Dynamic        Active Primary/Research   Main use
  ------------------ ---------------- ------------- ------------- ------------------ ----------------------
  India Code                      Yes           Yes            No Primary            Legislation

  Supreme Court                   Yes           Yes            No Primary            Judgments/orders
  official                                                                           

  High Court                      Yes           Yes            No Primary            Judgments/orders
  official/eCourts                                                                   

  District/eCourts            Limited           Yes            No Primary            Case/order research

  Vanga SC corpus                 Yes            No            No Open data          Historical ingestion

  Vanga HC corpus                 Yes            No            No Open data          Historical ingestion

  Bharat Courts                    No           Yes            No Access layer       Live court search

  Indian Kanoon API                No           Yes            No Third-party API    Search/document
                                                                                     retrieval

  ILDC                       Research      Research            No Research           Evaluation

  NyayaAnumana               Research      Research            No Research           Model/evaluation

  InLegalBERT          Model/research            No            No Research           Legal NLP

  IMLJD                      Research      Research            No Research           KG/GraphRAG

  Large HF court             Research      Research            No Research/data      Retrieval/evaluation
  corpora                                                                            
  ---------------------------------------------------------------------------------------------------------

------------------------------------------------------------------------

# 26. Recommended Phase-1 Data Stack

Do NOT use every dataset.

Use a small, trustworthy combination first:

``` text
                         PHASE 1
                            |
        +-------------------+-------------------+
        |                   |                   |
        v                   v                   v
      STATIC             DYNAMIC             ACTIVE
        |                   |                   |
        |                   |             usage/feedback
        |                   |
   +----+----+        +-----+------------------+
   |         |        |                        |
   v         v        v                        v
India Code  Vanga   Bharat Courts       Indian Kanoon
            SC/HC      / official        if permitted
            corpus      court search
   |         |        |                        |
   +---------+--------+------------------------+
                         |
                         v
                  Legal Evidence
                         |
                         v
                     Analyst
```

For V1, prioritize:

### Static

1.  India Code
2.  Vanga Supreme Court corpus
3.  Vanga High Court corpus, starting with Gujarat

### Dynamic

1.  Bharat Courts
2.  Official court search where accessible
3.  India Code search
4.  Indian Kanoon API where terms/attribution are acceptable

### Research/Evaluation

1.  ILDC
2.  NyayaAnumana
3.  IMLJD
4.  InLegalBERT
5.  other large open legal corpora

------------------------------------------------------------------------

# 27. AI Tool Contracts

The agent should not know whether the implementation is Bharat Courts, a
crawler, a database or an API.

Expose stable internal tools:

``` text
search_statutes(query, jurisdiction?)
get_statute(act_id)
get_section(act_id, section_id)

search_supreme_court(query, date_range?, judge?, citation?)
search_high_court(query, court?, date_range?, judge?)
search_district_court(query, state?, district?, court?)
get_judgment(document_id)
get_order(document_id)

find_citations(document_id)
find_precedent_relationships(document_id)

search_static_knowledge(query)
graph_lookup(entity_or_relationship)
```

This lets us replace a source later without changing the agent
prompt/workflow.

------------------------------------------------------------------------

# 28. Provenance Contract

Every tool response should include:

``` json
{
  "source": {
    "name": "Supreme Court of India",
    "url": "https://indiacode.gov.in/handle/123456789/535860",
    "document_id": "...",
    "source_type": "primary"
  },
  "document": {
    "title": "...",
    "court": "...",
    "date": "...",
    "citation": "...",
    "case_number": "...",
    "cnr": "..."
  },
  "content": "...",
  "location": {
    "page": 12,
    "paragraph": 42
  },
  "retrieved_at": "..."
}
```

This is critical for citation verification and auditability.

------------------------------------------------------------------------

# 29. What We Should NOT Do

### Do not

``` text
Dump every open dataset into one vector database.
```

### Do not

``` text
Treat a Hugging Face dataset as authoritative law.
```

### Do not

``` text
Automatically promote user feedback to the legal KG.
```

### Do not

``` text
Let an LLM invent citations if retrieval fails.
```

### Do not

``` text
Build 25 court-specific agents if one court-search abstraction works.
```

### Do not

``` text
Couple the agents directly to one scraping repository.
```

------------------------------------------------------------------------

# 30. Recommended Initial Repository Strategy

## Use directly

### Bharat Courts

For Dynamic Court Research.

https://github.com/iamshouvikmitra/bharat-courts

### Vanga Supreme Court

For historical Supreme Court ingestion.

https://github.com/vanga/indian-supreme-court-judgments

### Vanga High Court

For historical High Court ingestion.

https://github.com/vanga/indian-high-court-judgments

------------------------------------------------------------------------

## Study / benchmark

### IMLJD / Indian KG work

For graph schema and GraphRAG research.

### ILDC

For explainability/evaluation.

### NyayaAnumana

For large-scale Indian legal model/data research.

### InLegalBERT

For legal retrieval/NLP experiments.

------------------------------------------------------------------------

# 31. Research Papers to Read First

## Priority 1 --- Closest to our architecture

1.  Domain-Partitioned Hybrid RAG for Legal Reasoning\
    https://arxiv.org/abs/2602.23371

2.  Falkor-IRAC\
    https://arxiv.org/abs/2605.14665

3.  Constructing a Knowledge Graph from Indian Legal Domain Corpus\
    https://research.ibm.com/publications/constructing-a-knowledge-graph-from-indian-legal-domain-corpus

## Priority 2 --- Indian legal NLP/data

4.  ILDC for CJPE\
    https://aclanthology.org/2021.acl-long.313/

5.  NyayaAnumana & INLegalLlama\
    https://arxiv.org/abs/2412.08385

6.  InLegalBERT\
    https://huggingface.co/law-ai/InLegalBERT

------------------------------------------------------------------------

# 32. Final Architecture Reference

``` text
                         INDIAN LEGAL SOURCES
                                  |
         +------------------------+------------------------+
         |                        |                        |
         v                        v                        v
      PRIMARY                OPEN DATA                RESEARCH
         |                        |                        |
         |                        |                        |
    India Code             Vanga SC/HC              ILDC
    Supreme Court          AWS archives             IMLJD
    High Courts            Bharat Courts             NyayaAnumana
    eCourts                other corpora             InLegalBERT
         |                        |                        |
         +------------------------+------------------------+
                                  |
                                  v
                           DATA NORMALIZATION
                                  |
                 +----------------+----------------+
                 |                                 |
                 v                                 v
          STATIC KNOWLEDGE                  DYNAMIC TOOLS
                 |                                 |
          +------+-------+                 +-------+--------+
          |              |                 |       |        |
          v              v                 v       v        v
       Vector          Graph           SC/HC   District  India Code
       Index            KG            Search   Search    Search
          |              |
          +------+-------+
                 |
                 v
              ANALYST
                 ^
                 |
        +--------+--------+
        |                 |
   Active Evidence   Dynamic Evidence
        |                 |
        +--------+--------+
                 |
                 v
             DRAFT AGENT
                 |
                 v
         VERIFICATION AGENT
                 |
                 v
          CLAIM + CITATION
             VALIDATION
                 |
                 v
            FINAL ANSWER
```

------------------------------------------------------------------------

# 33. Bottom Line

For our project, the most important principle is:

> **Use primary legal sources as the authority, open-source repositories
> as programmatic/bulk-access infrastructure, research datasets as
> experimentation/evaluation resources, and preserve provenance at every
> step.**

The strongest starting combination is:

``` text
India Code
+
Official Court Sources
+
Vanga SC/HC historical corpora
+
Bharat Courts dynamic search
+
Optional Indian Kanoon API
+
Our own normalized knowledge graph
+
Our own vector/hybrid retrieval
```

This gives us enough data infrastructure to build the **Static +
Dynamic + Active** architecture without depending entirely on any one
third-party project.
