# Host capability boundaries

Use Python 3.11+ and the documented locked optional dependencies. The source code is portable; host adapters are not automatically verified. Kimi, Codex, ChatGPT, OpenClaw and Hermes must each pass file-access, execution, path discovery, status/error and artifact tests. No host is assumed to provide images, browsing or free inference. Local inference is a future tested-release requirement.

Use the read-only permission-scoped Playwright adapter for permitted collection, or authorized imports. Legacy impersonation, challenge handling and automatic package installation were removed. A chat-only environment can explain steps but must not claim executed tools.
