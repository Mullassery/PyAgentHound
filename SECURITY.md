# Security Policy

## Reporting Security Issues

**DO NOT** open public GitHub issues for security vulnerabilities.

If you discover a security vulnerability, please email: **mullassery@gmail.com**

Include:
- Description of the vulnerability
- Steps to reproduce (if applicable)
- Potential impact
- Suggested fix (if you have one)

## Current status (Phase 1)

This is a brand-new project. There has been no external security audit, no CVE
tracking history, and no certifications (SOC 2 / HIPAA / GDPR / PCI DSS / ISO 27001) —
none are planned at this stage.

Phase 1's threat surface is intentionally small: everything runs locally, storage is
a SQLite file on disk, and the only network activity is an *optional* HTTP POST from
the SDK to a `pyagenthound serve` instance the developer runs themselves — nothing is
sent anywhere unless `endpoint=` is explicitly set. There is no authentication on the
Phase-1 API server; it is meant to be run on `localhost` for local development, not
exposed on a network.

**Threat model (stated explicitly).** `pyagenthound serve` binds to `127.0.0.1` by
default and *refuses* to bind to any other host unless you pass `--allow-external`.
That flag exists so the exposure is a deliberate act, not an accident: the API serves
full read access to every stored trace (prompts, tool arguments, model outputs) with
no authn/authz, so anyone who can reach the port owns your data. Do not run
`pyagenthound serve --host <routable> --allow-external` on an untrusted network without
putting it behind your own auth/reverse proxy first.

There is no redaction/PII-scrubbing engine yet (see `ROADMAP_HONEST.md`). AI execution
traces can contain sensitive prompts, tool arguments, and model outputs — treat the
local SQLite database and anything passed to `set_attribute`/`set_input`/`set_output`
as sensitive, and do not point the SDK at an `endpoint` you don't control.

## Development Security

When contributing:
- Do not commit secrets, credentials, or API keys.
- Use environment variables for sensitive configuration.
- Never log full attribute/input/output payloads at `INFO` level or above — traces
  can contain arbitrary user/customer data.
- Write tests for security-relevant code.

## Security Updates

Security patches will be released as minor/patch versions when vulnerabilities are
discovered. There is no formal CVE tracking process beyond this document and
Dependabot/GitHub security alerts.

## Questions?

For security questions (non-vulnerability): open a GitHub Discussion.
