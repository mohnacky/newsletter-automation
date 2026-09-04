# Contributing

Thanks for looking. Two things to know before you spend time on a change.

## Scope

**This project does one thing: it turns a week of sources into a draft issue a
person then reads and sends.** It is small on purpose and it is close to
finished. A quiet repo here means the tool works, not that it is abandoned.

Very likely to be merged:

- **A new gather source.** One module with a `run(**options) -> dict`
  function. This is the best place to contribute.
- **A new delivery adapter**, as long as it stages a draft.
- Bug fixes, with a test that fails without the fix.
- Documentation that corrects something wrong or genuinely unclear.

Likely to be declined, with thanks:

- **Anything that sends email.** See below.
- A web UI, a dashboard, a scheduler, a database, or a hosted service.
- Support for a second LLM provider in this repo. Fork it: the seam is one
  function in `editor.py` and you will be happier owning it.
- A dependency added for something the standard library does adequately.
- Broad refactors, reformatting, or type-annotation sweeps that touch many
  files without changing behaviour.

If you are unsure, open an issue before writing the code. "Would you take a
patch that does X" is a welcome issue and costs you nothing.

## The one rule that is not up for discussion

**No code in this repository may send email.** Every delivery adapter stops at
a draft that a human opens, reads, and sends.

This is not an unfinished feature. A newsletter pipeline holds a language model
at one end and a list of real people at the other, and the gap between "the
draft is usually good" and "the draft is always safe to send unread" is where
the entire risk of the project lives. A pull request that adds an auto-send
flag, a scheduled send, or a `--yes` that skips review will be declined no
matter how well written it is.

Adapters that create drafts, queue for approval, or stage into a provider's UI
are all welcome.

## Adding a gather source

```python
# src/newsletter/gather/my_source.py
from ..common import log, stub

def run(**options) -> dict:
    if not have_what_i_need():
        return stub("my_source", "why it could not run")
    return {"items": [...]}
```

Register it in `src/newsletter/gather/__init__.py` and add it to the table in
the README.

**A source must never raise.** No key, a dead endpoint, an empty week: return
`stub(...)`. The run continues and the editorial prompt is told the section is
thin. Someone is going to run this at 6am on send day, and a crash then is a
worse outcome than a short issue.

## Development

```bash
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -e .
./.venv/bin/python -m unittest discover -s tests -v
./.venv/bin/newsletter --demo
```

Tests use only the standard library and must pass with no API keys and no
network. If your change needs a live service to be tested, mock it or test the
parsing separately.

Match the surrounding style: standard library first, comments that explain why
rather than what, and no new dependency without a reason in the PR description.
