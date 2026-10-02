# Dependencies and license notices

Original Beyondwords code is MIT-licensed. The local store, command-line interface, evidence handling, action journals and advertising adapter use Python's standard library. Optional packages are pinned with hashes; package metadata records their upstream sources.

| Component | Version | License | Purpose |
|---|---|---|---|
| Python | 3.11+ | PSF | Local runtime and standard library |
| Playwright Python | 1.63.0 | Apache-2.0 | Optional browser controls |
| Chromium | Playwright-managed build | BSD-style and bundled notices | Optional browser; downloaded separately |
| pyee | 13.0.0 | MIT | Playwright dependency |
| greenlet | 3.5.6 | MIT / PSF-2.0 | Playwright dependency |
| typing-extensions | 4.16.0 | PSF-2.0 | Runtime dependency |
| Pillow | 12.3.0 | MIT-CMU and binary notices | Image inspection and composition |
| ReportLab | 4.4.9 | BSD-style | PDF production |
| charset-normalizer | 3.5.1 | MIT | ReportLab dependency |
| pypdf | 6.10.0 | BSD-3-Clause | PDF inspection |
| MCP Python SDK / mcp-types | 2.2.0 | MIT | Optional local tool protocol |
| EPUBCheck | 5.4.0 | BSD-3-Clause and bundled notices | Optional independent EPUB validator |
| Oswald / Playfair Display | Bundled font files | SIL OFL 1.1 | Typography; notices retained beside fonts |

See `requirements/optional.lock`, `requirements/dependency-metadata.json`, `requirements/mcp.lock` and [MCP dependency metadata](MCP_DEPENDENCIES.json) for exact transitive packages, hashes and declared licenses. Browser binaries, Python wheels and Java runtimes are not redistributed in this download. EPUBCheck is downloaded only by the explicit installer using `requirements/epubcheck.lock.json`; it requires a separately installed compatible Java runtime with its own license.

The bundled Sponsored Products OpenAPI is an unchanged snapshot of Amazon's [official contract](https://github.com/amzn/ads-advanced-tools-docs/tree/e25aace0ec07997c113dac48f333298472243558/unified-campaign-management-migration-skills), commit `e25aace0ec07997c113dac48f333298472243558`. Its MIT notice is beside the schema under the skill's `assets/contracts`. A schema is not account access or platform acceptance.

EPUB implementation references retain W3C attribution and licensing in the skill's visual-production reference. The project's MIT license does not relicense fonts, platform specifications or content the author does not own.

No publishing SaaS, commercial market-data service or hosted advertising manager is mandatory. Optional host integrations, model inference and image-generation services retain their own terms and costs. Beyondwords does not bundle model weights or claim a validated local-inference setup.

## Walkthrough media

The included logo, banner and edited walkthrough are supplied as Beyondwords presentation assets. Third-party interfaces and book material visible in the walkthrough retain their respective rights. The code's MIT license does not relicense external content, imply platform endorsement or grant rights to reuse a depicted book. Raw recordings and private editing files are not distributed.

## Package automation

GitHub Actions uses pinned revisions of `actions/checkout` and `actions/setup-python` to verify the clean package. Those actions are provided under their upstream MIT notices. The check installs no model or account connector and performs no publishing or advertising action.
