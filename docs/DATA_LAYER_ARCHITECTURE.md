# Indian Legal AI --- Data Layer Architecture

## 1. Purpose

The data layer is the foundation of the Indian Legal AI system.

It is divided into three flows:

``` text
                    LEGAL DATA LAYER
                           |
        +------------------+------------------+
        |                  |                  |
        v                  v                  v
     STATIC             DYNAMIC             ACTIVE
     DATA               DATA                DATA
        |                  |                  |
        v                  v                  v
  Trusted corpus       Query-time         Usage-derived
  + knowledge graph    research            evidence
        |                  |                  |
        +------------------+------------------+
                           |
                           v
                    ANALYST / AI LAYER
```

The three flows solve different problems.

------------------------------------------------------------------------

# 2. Static Data

## Definition

Static data is high-confidence legal knowledge that we deliberately
pre-build and maintain.

It should be useful across many legal questions.

### Initial sources

``` text
Constitution of India
India Code
Acts
Sections
Rules
Regulations
Amendments
Selected Supreme Court judgments
Selected High Court judgments
Verified legal relationships
```

### Why static?

Some legal knowledge is repeatedly required.

For example:

``` text
Act
  |
  +--> Section
  |
  +--> Definition
  |
  +--> Exception
  |
  +--> Amendment
```

Building this once allows every research query to start from a trusted
foundation.

------------------------------------------------------------------------

# 3. Static Data Pipeline

``` text
                 PRIMARY SOURCES
                       |
       +---------------+---------------+
       |               |               |
       v               v               v
   India Code     Supreme Court    High Courts
       |               |               |
       +---------------+---------------+
                       |
                       v
                Data Ingestion
                       |
                       v
             Parse / Normalize
                       |
                       v
              Legal Extraction
                       |
          +------------+------------+
          |                         |
          v                         v
   Structured Documents       Legal Entities
          |                         |
          |                         v
          |                   Relationship
          |                    Extraction
          |                         |
          +------------+------------+
                       |
              +--------+--------+
              |                 |
              v                 v
          Vector Index      Knowledge Graph
```

------------------------------------------------------------------------

# 4. Static Knowledge Graph

The graph should represent legal entities and relationships.

### Entities

``` text
Act
Section
Subsection
Rule
Regulation
Amendment
Judgment
Order
Court
Judge
Case
Party
Legal Principle
Citation
Topic
```

### Relationships

``` text
Act
  |
  +-- contains --> Section
  |
  +-- amended_by --> Amendment

Section
  |
  +-- interpreted_by --> Judgment
  |
  +-- cross_references --> Section

Judgment
  |
  +-- cites --> Judgment
  +-- follows --> Judgment
  +-- distinguishes --> Judgment
  +-- overrules --> Judgment
  +-- refers_to --> Section
  +-- decided_by --> Court
```

------------------------------------------------------------------------

# 5. Dynamic Data

## Definition

Dynamic data is retrieved at query time.

It answers:

> What is relevant to this specific question right now?

Examples:

``` text
Recent judgments
Recent orders
Current court material
Current legislation
Specific case searches
Specific citations
```

Dynamic data does not need to be permanently inserted into the static KG
immediately.

------------------------------------------------------------------------

# 6. Dynamic Research Pipeline

``` text
                  USER QUERY
                       |
                       v
                Dynamic Researcher
                       |
       +---------------+---------------+
       |               |               |
       v               v               v
 Supreme Court      High Courts     India Code
       |               |               |
       +---------------+---------------+
                       |
                       v
                Search Results
                       |
                       v
                  Reranking
                       |
                       v
                   Evidence
                       |
                       v
                  ANALYST AGENT
```

------------------------------------------------------------------------

# 7. Dynamic Tools

The AI should access data through tools rather than directly knowing the
source implementation.

Example tool interface:

``` text
search_legislation()
get_act()
get_section()

search_supreme_court()
search_high_court()
search_district_court()

get_judgment()
get_order()

find_citations()
find_precedents()
```

Potential underlying implementations:

``` text
Official court repositories
India Code
Bharat Courts
Indian Kanoon API where permitted
```

The source adapter should preserve:

-   Original source
-   Document URL
-   Court
-   Document ID
-   Date
-   Case number
-   Citation
-   Retrieved timestamp
-   Source type

------------------------------------------------------------------------

# 8. Active Data

## Definition

Active data is generated from the system's continued use.

It is the layer that allows the platform to improve over time.

Possible signals:

``` text
Repeatedly retrieved cases
Frequently cited authorities
Repeated research paths
User corrections
User feedback
Verification results
Frequently associated sections
Frequently successful searches
```

------------------------------------------------------------------------

# 9. Active Knowledge Pipeline

``` text
                  USER / AGENT
                       |
                       v
                  Interaction
                       |
                       v
                  Observation
                       |
                       v
               Candidate Knowledge
                       |
                       v
                Validation Agent
                       |
                       v
               Confidence Score
                       |
              +--------+--------+
              |                 |
              v                 v
          Approved           Rejected
              |
              v
       Active Knowledge Store
              |
              v
       Periodic Promotion
              |
              v
       Static Knowledge Graph
```

## Critical rule

**Active data is not automatically authoritative.**

A frequently used citation does not become legally correct simply
because users use it often.

Promotion requires evidence and validation.

------------------------------------------------------------------------

# 10. Provenance

Every piece of knowledge should preserve its origin.

Example:

``` json
{
  "entity": "Section 103",
  "source": "India Code",
  "source_url": "...",
  "document_id": "...",
  "retrieved_at": "...",
  "confidence": 1.0,
  "status": "authoritative"
}
```

For a judgment:

``` json
{
  "case": "...",
  "court": "Supreme Court of India",
  "citation": "...",
  "source_url": "...",
  "paragraph": 42,
  "relationship": "interprets",
  "target": "Section X"
}
```

This allows the Verification Agent to trace a generated claim back to
its source.

------------------------------------------------------------------------

# 11. Confidence Model

We should distinguish different kinds of confidence.

``` text
Source confidence
      +
Extraction confidence
      +
Relationship confidence
      +
Verification confidence
      +
User-feedback signal
```

For example:

``` text
Official statute
    -> very high source confidence

LLM-extracted relationship
    -> requires verification

User says relationship is useful
    -> feedback signal only
```

Feedback should never be treated as legal authority.

------------------------------------------------------------------------

# 12. Static vs Dynamic vs Active

  ------------------------------------------------------------------------------
  Layer             Purpose                  Lifetime          Authority
  ----------------- ------------------------ ----------------- -----------------
  Static            Trusted reusable         Long-term         High
                    knowledge                                  

  Dynamic           Query-specific/current   Short-term        Depends on source
                    research                                   

  Active            Learning/evidence from   Long-term         Not authoritative
                    usage                    candidate store   until validated
  ------------------------------------------------------------------------------

------------------------------------------------------------------------

# 13. One Global Knowledge Graph

For Phase 1:

``` text
                 GLOBAL LEGAL KG
                       |
        +--------------+--------------+
        |              |              |
     Statutes       Judgments      Principles
        |              |              |
        +--------------+--------------+
                       |
                 All users/query
```

Do **not** create one graph per user initially.

Per-user knowledge graphs can be considered later for:

-   Private case history
-   Firm-specific research
-   User-uploaded documents
-   Personalized research memory

But they are outside the first architecture.

------------------------------------------------------------------------

# 14. Data + Agent Architecture

``` text
                         USER QUERY
                              |
                              v
                       SUPERVISOR AGENT
                              |
         +--------------------+--------------------+
         |                    |                    |
         v                    v                    v
  STATIC RESEARCHER    DYNAMIC RESEARCHER    ACTIVE RESEARCHER
         |                    |                    |
         v                    v                    v
   Knowledge Graph      Court/API Tools      Active Store
         |                    |                    |
         +--------------------+--------------------+
                              |
                              v
                        ANALYST AGENT
                              |
                              v
                         DRAFT AGENT
                              |
                              v
                    VERIFICATION AGENT
                              |
                              v
                         FINAL ANSWER
```

------------------------------------------------------------------------

# 15. Feedback Loop

The complete system should eventually form a continuous improvement
loop:

``` text
Query
  |
  v
Research
  |
  v
Analysis
  |
  v
Answer
  |
  v
Verification
  |
  v
User Feedback
  |
  v
Active Evidence
  |
  v
Validation
  |
  v
Knowledge Improvement
  |
  +----------------------+
                         |
                         v
                     Next Query
```

The system therefore improves its retrieval and knowledge coverage over
time without allowing uncontrolled feedback to rewrite trusted law.

------------------------------------------------------------------------

# 16. Phase 1 Data Sources

### Primary

-   India Code
-   Supreme Court of India
-   High Court repositories
-   District Court/eCourts infrastructure where available

### Programmatic/open-source infrastructure to evaluate

-   Bharat Courts
-   Indian Supreme Court Judgments dataset
-   Indian Kanoon API where its terms permit the intended use

### Research/evaluation datasets

These should primarily be used for benchmarking and experimentation, not
automatically treated as the production source of truth.

------------------------------------------------------------------------

# 17. Target Data Architecture

``` text
                         LEGAL SOURCES
                              |
            +-----------------+-----------------+
            |                 |                 |
            v                 v                 v
       Primary Data      Research Data      Live Search
            |                 |                 |
            v                 v                 v
        Ingestion          Evaluation        Tools
            |                 |                 |
            v                 |                 |
      Canonical Store         |                 |
            |                 |                 |
       +----+----+             |                 |
       |         |             |                 |
       v         v             |                 |
    Vector      Graph          |                 |
       |         |             |                 |
       +----+----+             |                 |
            |                  |                 |
            +------------------+-----------------+
                               |
                               v
                       LEGAL AI AGENTS
```

------------------------------------------------------------------------

# 18. Core Principle

The data architecture should enforce:

> **Static knowledge gives the AI a trusted foundation. Dynamic research
> gives it current and query-specific evidence. Active knowledge lets
> the system learn from usage without automatically turning user
> behavior into legal truth.**

This three-layer architecture is the foundation for later GraphRAG,
multi-agent research, legal drafting, and advanced verification.
