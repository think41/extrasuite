# Heuristic Section Summaries For `index.xml`

## Goal

Let an agent choose the right section from `index.xml` without reading the full
`document.xml`, while keeping the index deterministic, cheap, and compact.

Constraints:

- no LLM in the pull / serialize path
- summary should help on prose, lists, and tables
- output budget must stay bounded
- the algorithm must be stable enough that agents can learn how to use it

## Recommendation

Start with a hybrid keyword-first approach, not a pure sentence extractor.

Recommended v1 pipeline:

1. Define each section as `current_heading_xpath .. next_heading_xpath`.
2. Extract plain text from paragraphs, list items, and table cells in that
   range, preserving block boundaries.
3. Score candidate phrases with section-level TF-IDF across the document.
4. Add structural boosts:
   - phrases appearing in the heading text
   - phrases repeated in list-item prefixes
   - phrases repeated in table headers / first column labels
   - bold / emphasized phrases when available in the XML
5. Use YAKE as a fallback for weak sections where TF-IDF has too little signal
   because the section is short or the document has too few sections.
6. Emit a compact summary string made of:
   - top 3-5 normalized keyphrases
   - optionally one short lead sentence only when the section is prose-heavy

This should be treated as a deterministic formatter, not free-form generation.

## Why This Over The Alternatives

### TextRank / LexRank

Pros:

- good for long prose sections
- easy to explain

Cons:

- weak on bullet lists and tables
- tends to produce long sentences, which hurts index budget
- often repeats generic framing instead of domain terms

Verdict:

Useful as a benchmark, but not the best default.

### RAKE

Pros:

- simple
- fast
- no document-wide corpus needed

Cons:

- often emits awkward long phrases
- duplicates overlapping phrases
- weak normalization across sections

Verdict:

Fine as a baseline, but low precision for an index that agents need to trust.

### YAKE

Pros:

- strong single-document keyword extraction
- better than RAKE on short sections
- lightweight dependency

Cons:

- still keyword-oriented, not section-aware by itself
- can overvalue formatting artifacts or rare tokens without structural cues

Verdict:

Good fallback and comparison point. Not sufficient alone.

### Noun Phrase Chunking + TF-IDF

Pros:

- interpretable output
- document-aware scoring
- tends to surface domain terms better than sentence ranking

Cons:

- full NLP chunkers add dependency and model weight
- chunking quality can be brittle on XML-ish content and lists

Verdict:

The strongest direction conceptually, but avoid a heavy parser in v1.

## Practical v1

Use a lightweight phrase candidate generator instead of full syntactic chunking.

Candidate sources:

- heading text n-grams
- paragraph/list/table text n-grams (1-3 grams)
- capitalized multi-word spans
- repeated token spans near punctuation boundaries

Filter candidates by:

- stopword ratio
- max token length
- punctuation noise
- duplicate stems / near-duplicates

Score:

`score = tfidf * structure_boost * heading_overlap_boost * repetition_boost`

Where:

- `tfidf` is computed across all sections in the pulled document
- `structure_boost` favors list prefixes, table headers, and emphasized text
- `heading_overlap_boost` favors phrases overlapping with the section heading
- `repetition_boost` favors terms that recur inside the section

## Output Shape

Prefer a compact text field over a verbose sentence summary.

Recommended future XML shape:

```xml
<h2 xpath="/tab/body/h2[3]" headingId="h.plan">
  Delivery plan
  <summary>milestones; owners; rollout sequence; launch risks.</summary>
</h2>
```

Rules:

- target 8-20 words total
- hard cap around 160 characters for v1
- no more than one sentence in v1
- prefer semicolon-separated phrases over full prose

Why:

- phrases are cheaper than extractive sentences
- agents can match user intent against phrases quickly
- this format works better on list- and table-heavy sections

## Rollout Plan

Prototype in three phases.

Phase 1:

- implement section extraction boundaries using heading XPath order
- compute top phrases with TF-IDF plus structural boosts
- emit summaries only in debug output or an experiment branch

Phase 2:

- compare against YAKE-only and TextRank-only baselines on a small corpus
- manually score for usefulness in “find the right section quickly”
- track median summary length and false-positive rate

Phase 3:

- add `summary` to `index.xml`
- enforce byte / token budgets
- keep the algorithm versioned so future changes are explicit

## Metrics To Watch

- mean and p95 summary byte size
- average phrases per section
- overlap between chosen section and human-expected section
- usefulness on:
  - long prose sections
  - checklist sections
  - table-heavy sections
  - sections with very little body text

## Bottom Line

Start with document-relative phrase extraction plus structural boosting.

If we optimize for agent navigation instead of human-readable abstracts, a
keyword-first summary beats TextRank/LexRank as the default. YAKE is a good
fallback, not the main strategy. Full noun-phrase chunking is attractive later,
but it is not the low-risk first implementation.
