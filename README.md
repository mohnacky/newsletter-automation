# newsletter-automation

[![ci](https://github.com/mohnacky/newsletter-automation/actions/workflows/ci.yml/badge.svg)](https://github.com/mohnacky/newsletter-automation/actions/workflows/ci.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](pyproject.toml)

Newsletter tools automate the sending. The expensive part is the ninety minutes
before that: reading the week, deciding what matters, and writing it down in the
same shape every time.

This automates the reading and the first draft, and deliberately stops there.
It gathers your sources, drafts a structured issue with Claude, renders email
HTML, and stages a draft. **Then you read it and press send.** Nothing here can
send email on its own, and that is the feature.

Bring your own keys and your own voice. Nothing about any particular newsletter
is in the code: what you publish is one YAML file.

```
sources ──▶ gather ──▶ draft ──▶ lint ──▶ render ──▶ staged draft ──▶ you press send
             │           │        │                                      ▲
        cached per   one Claude  house rules                        the only
          issue        call      in code                          step that is
                                                                  never automatic
```

**Why a pipeline that cannot send.** A language model sits at one end of this
and a list of real people sits at the other. The distance between "the draft is
usually good" and "the draft is always safe to send unread" is the entire risk
of the project, and no amount of prompt engineering closes it. So every
delivery path stops at a draft, and every run writes a `sources.json` mapping
each claim in the issue to the URL behind it, which turns review from an hour
into a few minutes.

Three more constraints follow from the same idea:

- **Numbers in tables never pass through the model.** It writes the caption;
  the figures are inserted from your data afterwards. A figure in a table
  cannot be a hallucination because the model never sees one.
- **Human-only sections stay empty unless you write them.** No note supplied,
  no section.
- **House rules are lint, not prompt text.** Banned phrases, section counts,
  label order, "the lead must carry its counter-argument", every claim needs a
  real source URL. A violation fails the run instead of shipping.

## Try it with no keys at all

```bash
git clone https://github.com/mohnacky/newsletter-automation
cd newsletter-automation
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip   # editable installs need pip 21.3+
./.venv/bin/pip install -e .
./.venv/bin/newsletter --demo
```

That runs the whole pipeline on bundled fixtures and writes a complete issue to
`output/issue-001/` — open `preview.html` in a browser. No API key, no account,
no network. The demo content is invented; every link in it points at
`example.com`.

## One config file, three jobs

The section list in `config/newsletter.yaml` drives three things that usually
drift apart:

- **the schema** the model must fill in,
- **the brief** it is given,
- **the layout** that gets rendered.

Add a section and all three follow. There is no second place to update, which
is what stops a newsletter's structure quietly diverging from what its prompt
claims it is.

## Define your newsletter

```yaml
brand:
  name: The Example Brief
  tagline: A weekly read on one industry
  from_email: hello@example.com
  address: 123 Example Street, Anytown, ST 00000   # required by CAN-SPAM
  colors: { ink: "#1F2430", accent: "#2563EB" }

sections:
  - id: lead
    type: story
    kicker: Lead
    required: true
    both_sides: true      # the lead must carry its own counter-argument
    guidance: >
      Pick the story with the widest consequence, not the loudest one.

  - id: research
    type: items
    min: 2
    max: 3

  - id: signals
    type: bullets
    labels: [Policy, Industry, Research]   # exact set and order, one each
```

### Section types

| type | shape | use it for |
|---|---|---|
| `story` | headline, what happened, why it matters, source, optional counter-case | the lead item |
| `items` | a list of headline / what's new / why it matters / source | papers, launches, links |
| `debate` | named positions with links, a pull quote, a bottom line | what people are arguing about |
| `bullets` | label, fact, implication, source | short roundups, grouped by label |
| `note` | scene, why it matters | human-written colour (see below) |
| `table` | a caption over rows the model never sees | numbers |

Two of those carry a rule worth stating plainly:

- **`note` sections are human-only.** They are written from a file you pass with
  `--notes`. With no note supplied, the section is set to null. The model is
  told, in the schema and in the prompt, that it may not invent one.
- **`table` rows come from data, not from the model.** It writes the caption;
  the figures are inserted afterwards from a gather stage. A number in a table
  cannot be a hallucination because the model never touches it.

## Sources

Each entry names a source module and passes it options.

| source | key needed | what it does |
|---|---|---|
| `rss` | none | any RSS/Atom feeds |
| `arxiv` | none to fetch, Anthropic to rank | a category window, optionally ranked for your audience |
| `rows` | none | tabular figures from a local CSV or JSON you maintain |
| `web_search` | `EXA_API_KEY` | scoped searches with per-bucket domain allow-lists |
| `x_search` | `XAI_API_KEY` | discourse on X, via Grok's server-side search |

```yaml
gather:
  - id: headlines
    source: rss
    feeds: [https://example.com/feed.xml]
  - id: metrics
    source: rows
    path: data/this-week.csv
```

**No source can break your run.** A missing key, a dead feed, an empty week: the
stage writes a stub, the run continues, and the editorial prompt is told that
section is thin this week. A pipeline that crashes on send morning is worse than
one that reports less material.

Gather output is cached per issue, so reruns while you tune the prompt cost
nothing. `--fresh` refetches.

### Adding your own source

Write a function, name it in YAML:

```python
# src/newsletter/gather/my_source.py
def run(**options) -> dict:
    return {"items": [...]}          # or stub("my_source", "why not")
```

## Delivery

| adapter | what it does |
|---|---|
| `file` (default) | writes `email.html`. Paste into any provider. |
| `sendgrid` | creates a **draft** Single Send. |

**Neither can send.** That is a design constraint, not a missing feature. A
pipeline with send permission is one bad gather away from mailing your entire
list something wrong, and no amount of prompt care substitutes for a person
reading the thing first.

For SendGrid, `python -m newsletter.setup_sendgrid` provisions the sender,
list, and unsubscribe group idempotently and prints the three ids for `.env`.

## Guardrails

Prompts ask. These enforce. Any violation fails the run instead of shipping:

```yaml
style:
  banned_characters: ["—"]        # e.g. if your house style bans em dashes
  banned_phrases: [game changer, delve into]
  max_subject_chars: 65
  require_urls: true              # every claim carries a real source URL
```

Plus, from your section definitions: required sections must be present, item
counts must fall within `min`/`max`, `labels` must appear in exactly that order,
and a `both_sides` section must carry its counter-argument.

Every run also writes `sources.json` — every claim in the issue mapped to the
URL behind it. Open it beside the draft and review becomes minutes instead of an
hour.

## The weekly loop

```bash
newsletter --issue auto --notes notes/this-week.md   # gather + draft + render
open output/issue-042/preview.html                   # read it
newsletter --issue 42 --deliver                      # stage the draft
```

Then open the draft, check the copy against `sources.json`, and send it
yourself.

Editing the prompt is the main tuning loop. `prompts/editorial.md` is your house
style; the section briefs and hard rules are appended to it automatically from
config, so the prompt never falls out of step with the schema.

## A note on measuring it

Every outbound link is UTM-tagged, and it is worth counting arrivals at the
destination rather than trusting click counts from your provider. Corporate
email security appliances follow links in email to scan them, and each follow is
recorded as a click. On lists with many corporate addresses this is not a small
correction: published measurements put non-human clicks anywhere from 20% to
well over half of the total, and it is not stable week to week, so provider click
rates are often not comparable between sends. Counting sessions at the other end
of the link is the honest number.

## Cost

One issue is one Claude call, plus one optional cheap call to rank papers. The
gather sources that charge (Exa, xAI) bill per search, and xAI bills per tool
invocation on top of tokens, so set a spend limit before enabling it. `rss`,
`arxiv` and `rows` cost nothing.

Model, token ceiling, and effort are config: `model: claude-opus-5`.

## Tests

```bash
python -m unittest discover -s tests -v
```

No keys, no network, no fixtures to download.

## Contributing

New gather sources are the most useful thing you could add, and the easiest:
one function, one line in a registry. Read [CONTRIBUTING.md](CONTRIBUTING.md)
first — it has a scope section, and one rule that is not up for discussion.

## License

MIT. See [LICENSE](LICENSE).
