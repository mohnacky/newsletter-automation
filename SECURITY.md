# Security

## Reporting a vulnerability

Please report security issues privately through
[GitHub's private vulnerability reporting](https://github.com/mohnacky/newsletter-automation/security/advisories/new)
rather than in a public issue.

Include what you did, what happened, and what you expected. A proof of concept
helps. You will get an acknowledgement, and credit in the fix unless you would
rather not have it.

## What this project touches

It is worth being explicit, because this tool sits near two sensitive things.

**API keys.** The pipeline reads keys for Anthropic and, optionally, Exa, xAI
and SendGrid from the environment or a local `.env`. `.env` is gitignored. Keys
are never written to `output/`, never logged, and never sent anywhere except
the provider they belong to.

If you are wiring this into CI or a scheduler, note that a `.env` line written
as `KEY= value` with a space is read correctly by python-dotenv but is parsed
by a shell as "set KEY empty, then execute the value as a command" — which can
print the key into a log. Write `KEY=value` with no space.

**A subscriber list.** The SendGrid adapter can read your list id and create
drafts against it. It cannot send, and it cannot export contacts. If you write
an adapter for another provider, scope its credential to the narrowest
permission that will create a draft.

## What is out of scope

- Content the model writes. The pipeline constrains the model with a schema and
  lint rules, and every issue ships with a `sources.json` mapping each claim to
  its URL, but nothing here is a substitute for a person reading the draft.
  That review step is the security model, not an inconvenience around it.
- Third-party API behaviour. Report those to the provider.
