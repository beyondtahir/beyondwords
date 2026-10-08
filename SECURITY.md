# Security policy

Beyondwords handles manuscripts, research, local files and optional publishing or advertising connections. Protecting that work requires both clear reporting and practical controls. This policy covers the code and distribution maintained in [beyondtahir/beyondwords](https://github.com/beyondtahir/beyondwords).

## Report a vulnerability privately

Use **[Report a vulnerability](https://github.com/beyondtahir/beyondwords/security/advisories/new)** to contact the repository maintainer through GitHub's private reporting form. A GitHub account is required. Reports begin privately; coordinate any later public disclosure with the maintainer.

Include:

- The affected version or commit, operating system and assistant environment.
- The affected component and what an attacker could do.
- A minimal, reproducible example using dummy data.
- Expected behavior, actual behavior and relevant redacted output.
- Any suggested mitigation, if known.

Keep exploitable details, credentials, cookies, access tokens, identity documents and private manuscripts out of public issues. Do not include live credentials even in a private report. If a credential has been exposed, revoke or rotate it with the issuing service before sharing redacted evidence.

For installation questions, feature requests or ordinary bugs without security impact, use [Issues](https://github.com/beyondtahir/beyondwords/issues).

## Versions and updates

Security fixes target the **latest published release**. The current release line is **1.1.x**; older release lines are not maintained for security backports. Development on `main` may contain changes that are not yet in a release archive. Check [Releases](https://github.com/beyondtahir/beyondwords/releases) and published [advisories](https://github.com/beyondtahir/beyondwords/security/advisories) before installing an update.

Please report suspected vulnerabilities even if you cannot reproduce them on the latest version. This is a community-maintained project without a guaranteed response time or paid bug-bounty program. Reports are assessed for impact, reproduced where possible and coordinated with the reporter. Confirmed fixes and relevant upgrade or mitigation information will be documented; reporter credit is subject to their preference.

## What belongs in a security report

Examples include unauthorized access to another project's files, credential disclosure, unsafe file or network access, command execution from untrusted material, or a way to perform publishing/spending actions outside the actual authorized scope. Dependency vulnerabilities and compromised release artifacts are also relevant.

Use a local copy and accounts you own or are authorized to test. Do not access another person's data, run destructive tests, place real advertisements, submit books or probe third-party services to demonstrate a Beyondwords issue.

## Security boundaries

- **Local storage:** project data is stored as local files and databases. Beyondwords does not provide its own at-rest encryption. Use appropriate operating-system permissions, disk encryption and private backups.
- **Host permissions:** the skill and its Python helpers are not a sandbox. The selected assistant, extensions and tools may have access granted by the host. Install from a reviewed source and keep permissions appropriate to the work.
- **External services:** browser sessions, model providers, publishing accounts and ad APIs have their own security and data-handling rules. Local storage does not mean every host interaction stays on the device.
- **Untrusted input:** websites, books and imported files are source material, not authority to execute instructions or change accounts. Report failures in the implementation of that boundary.
- **Account actions:** login, identity, tax and banking details belong in the official service. Publishing and spending require real access and a defined authorized scope; the skill does not grant those permissions itself.
- **Integrity checks:** release hashes help detect changed files relative to a manifest. They are not a signature, independent audit or proof that software is harmless.

## Repository protections

The repository uses private vulnerability reporting, GitHub secret scanning and push protection, Dependabot alerts/security-update proposals, and CodeQL scanning of Python and GitHub Actions. Package checks verify release-file integrity and isolated installation on Linux, macOS and Windows. Current findings and run status are available in [Security](https://github.com/beyondtahir/beyondwords/security) and [Actions](https://github.com/beyondtahir/beyondwords/actions).

`requirements/requirements.txt` is the security-discovery inventory for the optional Python dependencies. It mirrors the exact versions in the hash-pinned runtime lockfiles, and the package checker rejects drift. Use the documented installer for runtime setup. Dependency proposals require review of the real lockfiles, hashes, metadata and tests; they are not automatically merged or installed.

Automated checks have limited coverage. Browser binaries, Java/EPUBCheck, host models, extensions and external accounts require their own updates and checks. Enabling these features is not a claim of a completed independent security audit or a guarantee that no vulnerabilities exist.
