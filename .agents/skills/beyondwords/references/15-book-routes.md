# Book routes

Choose the actual reader experience. Host-assisted creation and validated export are different capabilities.

| Route | Creative records | Additional checks |
|---|---|---|
| Practical nonfiction | Reader outcome, chapter contracts, examples, sources, exercises | Support for claims, expertise, real task completion |
| Text fiction | Plot/scenes, character motivation/knowledge, timeline, viewpoint, setup/payoff | Continuity, pacing, target-reader response |
| Children's books | Age band, read-aloud text, spread plan, page turns, consistent art references | Actual age review, visual consistency, fixed-layout/device tests |
| Comics | Panels, reading order, dialogue, lettering and art layers | Visual sequence, legibility, safe areas and rendered pages |
| Workbooks | Exercise goals, examples, response space, answer guidance | Usability, writing space, age and channel classification |
| Coloring books | Original line-art briefs and page inventory | Print contrast, duplicate/rights review, bleed and blank backs |
| Puzzles | Rules, constraints, solutions and answer keys | Run an appropriate deterministic solver and uniqueness checks; otherwise validation is unrun |

Text routes use the existing reflowable EPUB/simple PDF exporter. Visual routes now have an actual image-page PDF/fixed-layout EPUB exporter and template-bound cover wrap; see [visual production](23-visual-production.md). Host image/layout tools must create and inspect the pages first. These exports do not implement every puzzle solver, semantic comic navigation, rich text layout or complex-script shaping. Do not claim a prompt is a finished illustration or an unchecked activity is solved.

Translation requires source authorization, fluent editorial review, tested font/shaping/direction support and platform language eligibility. Urdu/Roman Urdu coaching is not proof of validated Urdu book typography. Missing glyphs must fail export rather than become blank squares.
