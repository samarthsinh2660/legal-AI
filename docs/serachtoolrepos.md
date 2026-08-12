### 1. `bharat-courts` — best for our SEARCH TOOL

[bharat-courts GitHub](https://github.com/iamshouvikmitra/bharat-courts?utm_source=chatgpt.com)

It is not just a dataset. It is an **SDK that queries the actual Indian court/eCourts infrastructure**. It currently covers:

* Supreme Court
* 25 High Courts
* 700+ District Courts
* Case search
* Orders/judgments
* Cause lists
* CNR searches

It also has an archive backed by AWS Open Data. ([GitHub][1])

So we could wrap it as:

```text
Legal Research Agent
        │
        ▼
search_court_cases()
        │
        ▼
bharat-courts
        │
 ┌──────┼────────┐
 ▼      ▼        ▼
SC     Gujarat   District
       HC        Courts
```

**This is the one I'd investigate first for our agent tool.**

---

### 2. `vanga/indian-supreme-court-judgments` — best for BULK SC DATA

[Indian Supreme Court Judgments GitHub](https://github.com/vanga/indian-supreme-court-judgments?utm_source=chatgpt.com)

This project downloads judgments from the eCourts website and makes the bulk dataset available through AWS.

It contains:

```text
1950 → present

PDFs
+
JSON metadata
+
Parquet structured metadata
```

and the dataset is **CC-BY-4.0**. ([GitHub][2])

This is excellent for:

```text
Supreme Court
      ↓
Bulk historical corpus
      ↓
Our ingestion pipeline
      ↓
Vector + Graph
```

I would **not primarily use this as the live search tool**. I'd use it to build our local legal knowledge base.

---

### 3. The important discovery: Bharat Courts already uses BOTH approaches

This is actually great for us.

Its archive uses AWS Open Data:

```text
SCI archive
1950 → present
        +
25 High Court archive
```

The archive is **CC-BY-4.0**, with Parquet metadata + PDFs, and is maintained by Dattam Labs. ([GitHub][1])

But the archive is not real-time — Bharat Courts says it can lag **2–3 months for Supreme Court/High Court judgments**.

So:

```text
Historical / bulk
        ↓
AWS Archive
        ↓
Bharat Courts ArchiveClient


Recent / live
        ↓
Official eCourts / court portals
        ↓
Bharat Courts live clients
```

That's actually a very nice architecture for us.

---

# What I recommend

Don't choose **one**.

Use them for different purposes:

| Need                            | Use                                    |
| ------------------------------- | -------------------------------------- |
| Historical Supreme Court corpus | `vanga/indian-supreme-court-judgments` |
| Live/recent court search        | `bharat-courts`                        |
| High Court search               | `bharat-courts`                        |
| District Court search           | `bharat-courts`                        |
| Bulk HC data                    | Bharat Courts AWS archive              |
| Local RAG                       | Our own vector index                   |
| Legal KG                        | Our own graph                          |
| Official verification           | Original court source                  |

So our Phase-1 AI tool could eventually be:

```text
                    Research Agent
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
      Court Search Tool        Legal Knowledge Tool
             │                       │
             ▼                       ▼
       Bharat Courts          Our RAG + Graph
             │
      ┌──────┼────────┐
      ▼      ▼        ▼
     SC      HC      District
```

### One important distinction

**"The repo gets data from a true source" ≠ "the repo itself is the legal authority."**

For production, we'll preserve the **original court/India Code URL and document identifier** alongside every retrieved document.

So the AI response can ultimately say:

> **Source:** Supreme Court of India
> **Judgment:** XYZ v ABC
> **Paragraph:** 42
> **Original document:** [court source]

That gives us traceability.

---

### One more thing I found

There are also open research datasets such as **IMLJD**, which includes 3,613 judgments plus a knowledge graph, and **ILDC**, a 35K-case Supreme Court corpus. These are useful for **evaluation/research**, but I would not treat them as our primary production legal source. ([arXiv][3])



[1]: https://github.com/iamshouvikmitra/bharat-courts?utm_source=chatgpt.com "GitHub - iamshouvikmitra/bharat-courts: Programmatically access Indian court data. Search cases, download orders, and get cause lists across 700+ District Courts, 25 High Courts and the Supreme Court. Use Claude, ChatGPT etc. to query data directly from official sources for free. · GitHub"
[2]: https://github.com/vanga/indian-supreme-court-judgments?utm_source=chatgpt.com "GitHub - vanga/indian-supreme-court-judgments: Code for scraping Indian Supreme court judgments | Dataset is opensourced via AWS open data ecchnage · GitHub"
[3]: https://arxiv.org/abs/2605.19346?utm_source=chatgpt.com "IMLJD: A Computational Dataset for Indian Matrimonial Litigation Analysis"
