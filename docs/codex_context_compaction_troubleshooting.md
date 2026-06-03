# Codex Context Compaction Troubleshooting

Date: 2026-06-03

## Symptom

Codex reports:

```text
Error running remote compact task: stream disconnected before completion: error sending request for url
(https://chatgpt.com/backend-api/codex/responses/compact)
```

## Diagnosis

This is not an Asuka application bug. The failing endpoint is a ChatGPT/Codex
backend endpoint used by Codex to summarize a long thread before continuing.
Asuka does not call this URL and has no local code path that can repair it.

The official Codex manual states that all thread information must fit inside the
model context window, and that Codex can automatically compact long threads by
summarizing relevant information and dropping less relevant details. The manual
also documents the `/compact` and `/status` CLI commands, compaction-related
configuration, and `PreCompact` / `PostCompact` hook events.

The most likely causes are:

1. Network, DNS, proxy, or TLS interruption between the local Codex client and
   `chatgpt.com`.
2. A transient ChatGPT/Codex backend stream timeout or disconnect while the
   compaction response was still streaming.
3. An expired or unhealthy ChatGPT authentication session.
4. A thread that is already too large or noisy, causing the remote summarization
   task to take too long or fail under load.

In this workspace, the first attempt to fetch the official Codex manual also
failed with `getaddrinfo EAI_AGAIN developers.openai.com` and then succeeded
after elevated network access. That points to local network/DNS/proxy
instability as the most likely explanation for this occurrence.

## Proxy Notes

This environment currently sets:

```text
ALL_PROXY=socks5://192.168.112.1:7890
HTTPS_PROXY=http://192.168.112.1:7890
HTTP_PROXY=http://192.168.112.1:7890
NO_PROXY=localhost,127.0.0.1,::1
```

That can work, but it also means different HTTP clients may choose different
proxy variables. One client may use `HTTPS_PROXY` and another may prefer
`ALL_PROXY`. For long-running streaming requests, such as Codex context
compaction, this can produce inconsistent behavior if the SOCKS proxy, DNS mode,
or host address is unstable.

If failures repeat, prefer one consistent proxy strategy:

```bash
# Option A: rely on HTTP CONNECT proxy variables only.
unset ALL_PROXY all_proxy
export HTTP_PROXY=http://192.168.112.1:7890
export HTTPS_PROXY=http://192.168.112.1:7890

# Option B: use SOCKS with remote DNS resolution where supported.
export ALL_PROXY=socks5h://192.168.112.1:7890
```

In WSL, also confirm that `192.168.112.1:7890` is reachable from the Linux
environment and that the Windows-side proxy allows LAN connections.

Observed on 2026-06-03:

- `/etc/resolv.conf` points to `systemd-resolved` stub DNS at `127.0.0.53`.
- Direct local resolution via `getent ahosts chatgpt.com` returned no result in
  this sandboxed session.
- Direct `curl --noproxy '*'` to `chatgpt.com` timed out.
- Proxied `curl --proxy socks5h://192.168.112.1:7890` to
  `https://chatgpt.com/backend-api/codex/responses/compact` returned
  `HTTP/2 405` with `Allow: POST`, proving the backend path is reachable through
  the proxy.

Conclusion: the immediate failure is more likely inconsistent proxy use or
direct-route blocking than a pure DNS outage. If changing `ALL_PROXY` does not
help, restart Codex from the same shell after exporting variables, or unset
`HTTP_PROXY` / `HTTPS_PROXY` so the runtime cannot prefer them over `ALL_PROXY`.

## Immediate Recovery

1. Retry once after the network stabilizes.
2. Run `/status` to inspect current context usage and session state.
3. Run `/compact` manually before continuing a long task.
4. If compaction fails again, start a fresh Codex thread and paste a short
   handoff summary containing only:
   - current branch
   - files changed
   - task goal
   - latest blocker
   - exact next command or next edit

## Local Checks

Run these from the same terminal environment that launches Codex:

```bash
codex --version
curl -I https://chatgpt.com/
curl -I https://developers.openai.com/codex/codex-manual.md
```

If the machine uses a corporate TLS proxy or private root CA, configure Codex
with:

```bash
export CODEX_CA_CERTIFICATE=/path/to/corporate-root-ca.pem
```

If authentication looks stale, run:

```bash
codex login
```

On a remote or headless machine, prefer:

```bash
codex login --device-auth
```

## Prevention

- Keep tool output small. Do not paste full logs unless they are needed.
- Use `rg`, targeted file reads, and short command output limits.
- Use `/compact` proactively before the context window is nearly full.
- Use `/new` for unrelated tasks instead of carrying one large transcript.
- Summarize decisions and next steps before switching tasks.
- For noisy long-running work, keep a local handoff note in the repo so a new
  thread can restart cleanly.

Optional Codex config knobs documented by the Codex manual:

```toml
model_auto_compact_token_limit = 64000
tool_output_token_limit = 12000
compact_prompt = ""
experimental_compact_prompt_file = "/absolute/or/relative/path/to/compact_prompt.txt"
```

Tune these only when repeated failures show that automatic compaction happens
too late or stores too much tool output.

## What Cannot Be Fixed In This Repo

The `chatgpt.com/backend-api/codex/responses/compact` stream is owned by
ChatGPT/Codex. Asuka source changes cannot repair:

- ChatGPT service interruptions
- local DNS/proxy/TLS failures
- Codex client authentication state
- remote compaction endpoint behavior

If the error is reproducible after network and auth checks, report it through
Codex feedback or the OpenAI Codex issue tracker with sanitized logs.
