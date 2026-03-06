# Adaptive `index.xml` Strategy

## Problem

`index.xml` should help an agent avoid reading full `document.xml` files, but a
fixed indexing policy does not work across all document sizes.

- On a tiny document, a rich index is overhead.
- On a large document, a flat heading dump is not enough.
- On a badly structured document, deep heading capture may still miss the real
  content boundaries.

The index must stay useful, stable, and size-bounded.

## Design Goal

Keep one stable contract across all sizes:

- tabs are always discoverable
- primary section XPaths are always trustworthy
- optional metadata is pruned in a deterministic order when budget is tight

This lets agents rely on the same navigation model even when the index is
smaller than ideal.

## Measure Size With More Than One Signal

Do not use just page count. We do not have a reliable page number during
serialization, and page count is a poor proxy for structured docs anyway.

Use these signals:

- total serialized `document.xml` bytes across all tabs
- total visible word count across all tabs
- indexed heading count by level
- tab count
- max blocks between adjacent headings

Primary budget control:

- serialized `index.xml` byte size

Secondary guards:

- indexed entry count
- estimated token count

## Recommended Tiers

### Tier 0: Tiny

Trigger:

- <= 6 indexed headings total, or
- <= 1,200 visible words total

Emit:

- tabs
- `title` / `subtitle` / `h1` XPaths only
- no summaries

Reasoning:

At this size, opening the whole target tab is cheap enough. The index should
only answer “which tab?” and “where is the heading?”.

### Tier 1: Small

Trigger:

- <= 30 indexed headings, and
- <= 8,000 visible words

Emit:

- tabs
- `title`, `subtitle`, `h1`, `h2` XPaths
- optional summaries only for top-level sections if budget permits

Reasoning:

This is where the XPath index starts paying off, but a deep multi-level summary
still risks costing more than it saves.

### Tier 2: Medium

Trigger:

- <= 120 indexed headings, and
- <= 35,000 visible words

Emit:

- tabs
- `title`, `subtitle`, `h1`, `h2`
- `h3` only when a tab is sparse enough that deeper detail still fits
- summaries for `h1` and `h2`

Reasoning:

This is the default “progressive disclosure” sweet spot. The agent can narrow
to a tab, then to an `h1`, then to an `h2`, usually without opening the full
tab.

### Tier 3: Large

Trigger:

- > 120 indexed headings, or
- > 35,000 visible words

Emit:

- tabs
- all `h1` XPaths
- selected `h2` entries under the densest or most informative `h1` groups
- summaries for `h1` only
- no `h3`

Reasoning:

At this size, exhaustive depth makes the index collapse under its own weight.
The index should become a routing layer, not a mirror of the document outline.

## Budget Rules

Use deterministic pruning so the index remains predictable.

Suggested limits:

- soft limit: 16 KB serialized `index.xml`
- hard limit: 32 KB serialized `index.xml`
- secondary cap: 200 heading entries

Pruning order when above soft limit:

1. drop summaries from the deepest headings first
2. drop `h3`
3. drop summaries from `h2`
4. thin dense `h2` sets within a tab
5. keep only `h1` plus tab metadata

Never prune:

- root document metadata
- tab folder mapping
- `h1` XPaths unless the document literally has no `h1`

If the hard limit is still exceeded after pruning, emit only tabs plus the
highest-level headings available.

## What “Selected `h2`” Means

For large docs, choose `h2` entries by utility, not by raw order alone.

Scoring factors:

- section size under the `h2`
- summary confidence / phrase density
- heading specificity
- diversity within the parent `h1` group

Simple deterministic rule for v1:

- keep the first 3 `h2` entries under each `h1`
- then keep any additional `h2` whose section is unusually large
- stop when the tab budget is reached

This is intentionally crude but stable.

## Poor Heading Structure

Some Docs are large but barely use headings. Do not immediately invent many
synthetic sections; unstable pseudo-headings are worse than a sparse index.

Fallback policy:

1. keep tab-level metadata
2. index whatever real headings exist
3. if a tab has very large gaps between headings, add at most a few synthetic
   chunks based on block count, not sentence count

Example synthetic chunk triggers:

- more than 40 body blocks without a heading, or
- more than 1,500 words between headings

Synthetic chunks should be clearly marked in a future format revision so agents
do not confuse them with author-created headings.

## Stability Rules

Agents need the index contract to feel stable across pulls.

To preserve that:

- always emit absolute XPaths for retained entries
- make pruning depend only on document content and fixed thresholds
- version summary algorithms explicitly
- avoid per-run randomness or non-deterministic tie-breaking

If two entries have equal scores, break ties by document order.

## Recommended Future Shape

One reasonable long-term shape is:

```xml
<tab id="t.0" title="Spec" folder="Spec">
  <h1 xpath="/tab/body/h1[1]">
    Overview
    <summary>scope; file layout; editable surfaces.</summary>
  </h1>
  <h2 xpath="/tab/body/h2[1]">Serialization</h2>
</tab>
```

The critical point is not the exact XML nesting. The critical point is that the
agent can always trust:

- `tab/@folder`
- heading `@xpath`
- retained entries being in document order

## Incremental Rollout

1. Ship XPath support first.
2. Add summaries behind an experiment flag.
3. Measure index size distribution across real pulled docs.
4. Introduce tiering with conservative defaults.
5. Only then consider synthetic chunking for poorly structured large docs.

## Bottom Line

Make the index adaptive by pruning optional detail, not by changing the basic
navigation contract.

For small docs, keep the index shallow. For medium docs, emit the full
progressive-disclosure structure. For large docs, keep tabs and `h1` stable,
use selective `h2`, and drop summaries and depth before the index becomes
another large document that the agent has to read.
