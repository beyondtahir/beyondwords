# Host capabilities and installation

Beyondwords uses ordinary skill instructions and a local Python CLI. The host model is replaceable. A successful Python test is not a successful installation test in every AI product.

## Codex / ChatGPT Work desktop

Install the Beyondwords personal plugin or the standalone skill through the distribution instructions. In Codex, select the skill/plugin or use `$beyondwords`; in Work, select the installed plugin/skill from the `@` menu. Start a new task after installing so the host loads the new resources. Do not claim Work installation solely because files exist in a Codex skill directory.

On a local task with execution, resolve the actual skill path and run `scripts/beyondwords.py doctor`. Use the reviewed runtime at `~/.local/share/beyondwords/runtime` or an explicitly configured versioned/project environment for optional export/browser dependencies. `tools/setup_runtime.py` in the source/plugin distribution explicitly installs locked open-source dependencies; `--browser` installs Chromium and `--mcp` adds the optional official MCP SDK. It refuses an existing destination. The helper has no autonomous model inference: the current host drafts/reasons and calls deterministic tools. Host search/image/browser availability must be checked separately.

A remote/cloud task cannot automatically read a local installation. It needs the package in its own environment with execution/dependencies, or a separately configured tested tool connection. No hosted MCP service is bundled. Never pretend a local file operation happened in the cloud.

## Kimi, OpenClaw and Hermes

These are intended host targets, not verified integrations. Use their current official skill/import documentation when setting up; don't invent directory conventions or configuration fields. Where local execution is actually exposed, the same CLI can be called with JSON files. Where it is not, offer the file handoff and keep runtime actions unavailable. Record host/version/date and actual smoke-test result before advertising compatibility.

## Smoke test

1. Confirm the host can discover the exact Beyondwords entry point.
2. Ask it to report actual capabilities and start a new temporary synthetic project.
3. Save a short plan and chapter, restart/resume, and retrieve the same content/revision.
4. Export a supported edition, inspect the real files and validator output.
5. Ask for an unconfigured account action; verify it requests the actual missing connection and never invents authentication or a receipt.

Only mark the steps actually performed. Independent model behavior, novice usability, all host compatibility and local inference remain separate evaluation work. The common CLI avoids a mandatory proprietary publishing service, but does not make host subscriptions or inference free.

## Official portability references checked 1 October 2026

- [Kimi Code skills](https://www.kimi.com/code/docs/en/kimi-code-cli/customization/skills.html): user skills under KIMI_CODE_HOME/skills (default ~/.kimi-code/skills) and ~/.agents/skills; project scopes are also documented. Preserve the full skill directory/resources. This documents Kimi Code, not proof of every Kimi web/work interface.
- [OpenClaw skills](https://docs.openclaw.ai/tools/skills): local-directory installation is documented as `openclaw skills install ./path/to/skill --as beyondwords`. Inspect the installed version's help; shared/global scope is optional. No registry publishing is needed for a local skill.
- [Hermes skills](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/): standard skill directories and installation/update/provenance checks are documented. Preserve resources, inspect conflicts and avoid overwrite/force shortcuts. Verify discovery and execution in the actual installation before advertising compatibility.
- [Claude custom skills](https://support.claude.com/en/articles/12512180-use-skills-in-claude): upload a ZIP containing the full skill folder through Customize > Skills. Python/file execution, dependencies and durable memory still need actual verification in the chosen Claude/Cowork environment.

For any host, start with the guide questionnaire, save answers to a private memory root, restart and confirm retrieval. Share memory only through an authorized accessible directory or intake handoff. Do not put a user's intake in the skill ZIP. File/schema portability is implemented; these documentation checks are not end-to-end host certification.
