# Install Beyondwords

[← Back to Beyondwords](../README.md)

Install the skill in your assistant, then check which tools it can use. The skill ZIP contains instructions **and executable resources**. Keep the whole folder, not just `SKILL.md`.

**Choose your host:** [ChatGPT Work](#chatgpt-work) · [Codex](#codex) · [Claude Cowork](#claude-cowork) · [Kimi Work](#kimi-work) · [OpenClaw](#openclaw) · [Hermes](#hermes-agent)

Download the skill ZIP or complete source ZIP from the [latest published release](https://github.com/beyondtahir/beyondwords/releases/latest). Check the version there when updating an existing installation.

The skill ZIP has one `beyondwords/` folder containing `SKILL.md`, scripts, references and assets. The source ZIP also includes setup tools, dependency locks, documentation and branding. Menu names and availability depend on your host version and workspace policy. These are documented installation routes, not a claim of completed acceptance testing in every host.

## ChatGPT Work

**Compatibility under investigation.** A user reported that Work rejected the complete skill from commit `a4c1630` during upload. The service gave no file or rule and the issue closed without a recorded fix. If the scan rejects the package, record the release, exact error and host version for workspace support. A successful local package check verifies a different installation route. [Install report #12](https://github.com/beyondtahir/beyondwords/issues/12)


In an eligible workspace, open **Plugins**, choose **Skills**, then **Create** and **Upload from your computer**. Choose the complete skill ZIP and check the scan result. If uploading is unavailable, check your workspace’s skill permissions. [OpenAI’s skill upload and scan guidance](https://help.openai.com/en/articles/20001066-skills-in-chatgpt)

If your interface offers plugin creation or repository import instead, supply:

```text
Install Beyondwords from https://github.com/beyondtahir/beyondwords.
The complete skill is in .agents/skills/beyondwords.
Use this workspace's supported skill or plugin installation flow.
Preserve the scripts, references and assets; verify registration and tool access.
```

Start a fresh Work conversation and select Beyondwords from the available skill/plugin picker. Use `@Beyondwords` if that interface exposes it as a plugin, then run the [first-run check](#first-run-check).

Attaching a ZIP as ordinary chat context is not necessarily installation. A local filesystem copy does not register a cloud workspace skill. If the controls are absent, use the host's supported availability/admin route; do not treat the import as complete.

Official guidance: [Skills and plugins](https://learn.chatgpt.com/docs/skills-and-plugins), [build skills](https://learn.chatgpt.com/docs/build-skills), [workspace skills](https://learn.chatgpt.com/docs/enterprise/skills).

## Codex

For a local desktop, CLI or IDE environment, extract the source ZIP and open its `beyondwords` directory. Install the skill into the user skill directory:

```sh
python3 tools/install_skill.py
```

On Windows, use `py -3 tools/install_skill.py`. The installer copies the full skill to `~/.agents/skills/beyondwords` and refuses to overwrite an existing copy. To install only for a particular project:

```sh
python3 tools/install_skill.py --project /path/to/your/project
```

Use your actual project path. Invoke **`$beyondwords`** or choose Beyondwords in the skill picker. Restart the host if discovery has not refreshed. The repository's own `.agents/skills/beyondwords` also supports project-local discovery when that repository is the active workspace.

To use production and optional connected tools, complete [local runtime setup](#local-runtime-setup). Cloud or managed environments need their own supported repository/plugin configuration; this local command does not register them automatically.

Official guidance: [Skills and discovery](https://learn.chatgpt.com/docs/build-skills).

## Claude Cowork

1. Enable **Code execution and file creation** under Settings → Capabilities, if available and permitted.
2. Open **Customize → Skills → + → Create skill → Upload a skill**.
3. Upload the downloaded skill ZIP and enable the skill.
4. Start a new conversation or Cowork task. Ask: “Use Beyondwords as my publishing team,” then run the [first-run check](#first-run-check).

Keep the ZIP intact with its single top-level skill folder. Do not upload the full source ZIP as the skill. Local file access, browser control, persistent storage and dependencies depend on the current session; the skill cannot create those permissions itself. Organization policy may restrict uploads or execution.

Official guidance: [Use skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude), [custom skill packaging](https://support.claude.com/en/articles/12512198-how-to-create-custom-skills).

## Kimi Work

Open **Plugin Builder** using the `/` menu or the custom-plugin entry. Ask it to import this repository:

```text
Import https://github.com/beyondtahir/beyondwords as a personal publishing plugin.
Use .agents/skills/beyondwords as the skill source.
Preserve the existing code and all resources; adapt only the host packaging needed.
Check the actual tools and persistent workspace before claiming installation works.
```

Review the resulting package, register it in your personal marketplace and install it under **Plugins → Personal**. Enable it in a new task through the available plugin menu, then perform the [first-run check](#first-run-check).

Kimi's repository importer can adapt skill repositories; this is a host packaging step, not a reason to rewrite Beyondwords. If a resource or runtime is unavailable, report that limit and retain a working import/local-file route. Kimi Code's filesystem setup is a separate product route.

Official guidance: [Create plugins and import repositories](https://www.kimi.com/en/help/plugins-and-skills/create).

## OpenClaw

Extract the source ZIP and open the `beyondwords` directory. With OpenClaw already installed, use its current local-folder installer:

```sh
openclaw skills install ./.agents/skills/beyondwords --as beyondwords
openclaw skills list
openclaw skills check
```

The selected directory must contain `SKILL.md`; the repository root does not. Install into the intended active workspace, then start a new session and ask to use Beyondwords. Follow any normal trust review and dependency messages. Do not bypass a scanner or force an overwrite to make installation appear successful.

Complete [runtime setup](#local-runtime-setup) in an accessible environment if Python or production tools are missing. Check that the active agent can read and write the selected private book directory.

Official guidance: [Skills CLI](https://docs.openclaw.ai/cli/skills), [skills discovery](https://docs.openclaw.ai/skills).

## Hermes Agent

With Hermes already installed, use its GitHub subdirectory route:

```sh
hermes skills install beyondtahir/beyondwords/.agents/skills/beyondwords
```

Use the intended Hermes profile. Review the install output and any security/trust prompts, then start a fresh session and invoke `/beyondwords` or ask to use the skill.

A project-local alternative is to extract the source ZIP, open its `beyondwords` directory and use Hermes's project skill discovery. Review the project and run `hermes skills trust` when Hermes requests that trust decision. The skill is already under `.agents/skills/beyondwords`.

Perform the [first-run check](#first-run-check), then configure the [local runtime](#local-runtime-setup) if required. Installation does not establish browser, model or account access.

Official guidance: [Hermes skills](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/).

## First-run check

Ask your assistant:

```text
Use Beyondwords. Confirm you loaded its SKILL.md and can access its resources.
Check Python and the local doctor, persistent project storage, browser/search,
image generation and any account tools separately.
Tell me briefly what works and what needs setup. Then start the short intake.
Do not publish, spend money or connect an account during this check.
```

A useful result confirms the skill was loaded, identifies a private project location, distinguishes installed tools from verified connections and begins intake. If it only repeats the README, ask it to verify the actual skill registration and resource access.

## Updating an existing installation

Extract the new source to a fresh folder. Run the setup commands below from that folder to create its own runtime. Select the new project skill and runtime in your host, run `doctor`, and check that its version matches `VERSION`. For MCP, update the configured executable and script paths together. Open your existing private book workspace with the new runtime. Export revised chapters to a fresh destination and review the new files before replacing any approved publication files.

## Local runtime setup

For local helper execution, install **Python 3.11 or newer**; Python 3.12 is used in the package checks. Extract the **source ZIP** and work inside `beyondwords`. The following creates a new isolated environment and downloads hash-pinned open-source packages.

macOS/Linux:

```sh
python3 tools/setup_runtime.py --destination .beyondwords-runtime --browser --mcp
.beyondwords-runtime/bin/python .agents/skills/beyondwords/scripts/beyondwords.py doctor
```

Windows PowerShell:

```powershell
py -3 tools/setup_runtime.py --destination .beyondwords-runtime --browser --mcp
.\.beyondwords-runtime\Scripts\python.exe .agents/skills/beyondwords/scripts/beyondwords.py doctor
```

The runtime includes optional book-production libraries. `--browser` also downloads Playwright's matching Chromium binary; `--mcp` installs the optional MCP transport. Omit either option when unnecessary. In a restricted managed host, ask the assistant to use supported built-in tools and report any helper it cannot run.

The installer preserves existing runtimes. Choose a new destination for an update. On Linux, browser launch can require operating-system packages; use [Playwright's browser guidance](https://playwright.dev/python/docs/browsers) for the reported missing libraries. Installing Chromium does not authorize collection from a particular source.

`doctor` reports local detection and explicit unverified capabilities. It does not log into accounts, probe every host feature or prove a publishing connection works.

## Optional MCP connection

A host with local STDIO support can call the bundled tools through the optional MCP server. After installing with `--mcp`, inspect:

```sh
python3 tools/configure_mcp.py --help
```

Supply the real runtime executable, a **private** workspace root, project ID and new destination file. Choose JSON or TOML for the host. Review and import that configuration through the host's settings. The helper writes a configuration file; it does not modify host settings, include credentials or create a public remote endpoint.

See the [connected runtime contract](../.agents/skills/beyondwords/references/21-connected-runtime.md). Remote-only MCP clients cannot directly use a local STDIO connection.

## Optional EPUB validation

Install a compatible Java runtime, then run:

```sh
python3 tools/install_epubcheck.py --destination .epubcheck
```

The explicit download is checked against the pinned hash. Set `BEYONDWORDS_EPUBCHECK_JAR` to the extracted JAR and, if needed, `BEYONDWORDS_JAVA` to the Java executable. Missing validation remains visible; generating an EPUB does not certify retailer acceptance.

## Updates and troubleshooting

| What happens | What to do |
|---|---|
| Skill is missing from the picker | Verify host registration, enabled status, selected workspace/profile and fresh-session discovery. |
| Import rejects the ZIP | Use the skill ZIP, with one `beyondwords` folder and `SKILL.md` inside; retain all resources. |
| Python is missing or too old | Install Python 3.11+ in the execution environment, not only on another computer. |
| A production dependency is missing | Use the source ZIP's runtime installer, then select that runtime's Python. |
| A page is blocked | Use permitted normal browsing, another authorized source or supplied evidence. A block is not successful research. |
| Ads or publishing is unavailable | Verify the actual account, credentials, eligibility and connection. Use report imports or an attended handoff meanwhile. |
| “Already exists” during installation | Keep the previous copy, review the update and select a new runtime or deliberately replace the reviewed skill through your host. |
| Memory disappeared in another host | Grant access to a deliberate private handoff; memory does not sync across services automatically. |

Keep book projects outside the installation. Back them up before changing hosts or updating. Never put credentials, account sessions or private manuscripts into a shared repository. [Privacy and storage →](PRIVACY.md)
