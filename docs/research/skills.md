# Agent Skills vetting for Proseway

Date of review: 2026-11-21. Reviewer: Claude Code (research task). Nothing was installed or changed on this machine; all files were fetched read-only into a scratch folder and read there.

Scope: Claude Code skills that could help build Proseway (FastAPI backend + React/Vite/TypeScript frontend, local-first, Apache-2.0). Candidates: `anthropics/skills` (frontend-design, webapp-testing), `obra/superpowers`, UI/UX Pro Max (`nextlevelbuilder/ui-ux-pro-max-skill`), plus three extras for accessibility and design review: `addyosmani/web-quality-skills` (accessibility), `vercel-labs/agent-skills` (web-design-guidelines), `pbakaus/impeccable`.

Repo numbers come from `gh api repos/OWNER/REPO` on 2026-11-21. GitHub's `open_issues` count includes open pull requests.

## Summary table

| Skill | Repo | Stars | Last push | License | Verdict | Why |
|---|---|---|---|---|---|---|
| frontend-design | anthropics/skills @ `e4bb5d9` | 198,210 | 2026-11-16 | Repo: none set. Skill folder: Apache-2.0 (LICENSE.txt) | **Use** | One prompt-only SKILL.md, no scripts. Good guidance on type, line length, focus, reduced motion, and UI copy. Matches the plugin already installed here, byte for byte. |
| webapp-testing | anthropics/skills @ `e4bb5d9` | 198,210 | 2026-11-16 | Skill folder: Apache-2.0 | **Use, with fixes** | Small and readable Playwright helper. It never calls out to the network by itself. Two practical bugs (see notes). |
| superpowers (subset) | obra/superpowers @ `22f0b46` (v7.0.2) | 323,069 | 2026-11-03 | MIT | **Use a subset** | TDD, debugging and verification skills are solid and self-contained. The full plugin adds a SessionStart hook and a visual companion that loads a remote logo (a tracking beacon unless you opt out). |
| ui-ux-pro-max | nextlevelbuilder/ui-ux-pro-max-skill @ `2de1134` (v2.15.0) | 152,287 | 2026-11-19 | MIT | **Use the folder only, not the plugin** | The skill folder is stdlib-only Python over local CSV data, with no network calls. The plugin also installs sibling skills that read API keys from `~/.claude/.env` and send prompts to four third-party image APIs. |
| accessibility | addyosmani/web-quality-skills @ `afa8da9` | 3,116 | 2026-08-24 | MIT | **Use** | Clear WCAG 2.2 checklist and an evidence-led audit workflow. Docs only. One global `npm install -g` suggestion to change. |
| web-design-guidelines | vercel-labs/agent-skills @ `5a37a63` | 34,632 | 2026-11-20 | **Repo has no license** | **Use the MIT upstream instead** | Rules are bundled and pinned by SHA-256, with no runtime fetch. But the agent-skills repo has no license file, so don't commit its folder into Proseway. Use the same file from `vercel-labs/web-interface-guidelines` (MIT). |
| impeccable | pbakaus/impeccable @ `b49177d` | 114,218 | 2026-11-21 | Apache-2.0 | **Optional, not in the default set** | Strong design and audit content. But its launcher downloads and runs a prebuilt binary (checksum-verified), and its config registers hooks on SessionStart, every Edit/Write, and Stop. Too invasive to make a default for contributors. |

Maintainers:
- `anthropics`: the Anthropic GitHub org.
- `obra`: Jesse Vincent (529 of the top commits). Branding in the code says "Prime Radiant".
- `nextlevelbuilder`: org "Next Level Builder" (nextlevelbuilder.io), created 2025-11-30. Top contributors are viettranx and mrgoonie.
- `addyosmani`: Addy Osmani (personal account).
- `vercel-labs`: Vercel.
- `pbakaus`: Paul Bakaus.

## Already present on this machine (read-only check)

`~/.claude/plugins\installed_plugins.json` (all user scope):
- `superpowers@claude-plugins-official` v7.0.2, `gitCommitSha 22f0b463e7a5…`. This is **exactly the commit vetted below**. An older `7.0.0` cache folder also exists. The plugin's SessionStart hook is active in every session on this machine.
- `frontend-design@claude-plugins-official` v1.1.1. Its `skills/frontend-design/SKILL.md` is **identical** to `anthropics/skills@e4bb5d9` (checked with `diff` after normalising line endings).
- Also installed but out of scope: code-review, feature-dev, skill-creator, security-guidance, claude-mem (thedotmack), figma, vercel, stripe, supabase, and others. These were not vetted here.

`~/.claude/skills\` (personal skills):
- Design-related, overlapping this topic: `impeccable` (v3.8.0, skill folder only, with no hooks configured as far as this check shows), `hallmark`, `taste-skill`, `redesign-skill`, `minimalist-skill`, `stitch-skill` (DESIGN.md / design-system), `soft-skill`, `brutalist-skill`. These were not vetted in this review.
- Not present: ui-ux-pro-max, webapp-testing, accessibility, web-design-guidelines.
- Flag: `caveman` is installed. Its own description says it "cuts output tokens 65%". That is the kind of output-cutting behaviour this review was asked to flag. Keep it out of the Proseway project. (`output-skill` / full-output-enforcement does the opposite.)

---

## Per-skill vetting notes

Red-flag checklist applied to each skill:
1. Asks for credentials.
2. Sends data to remote endpoints.
3. Runs obfuscated or minified code.
4. Downloads and executes code.
5. Touches global settings or hooks without a reason.
6. Cuts output to save tokens.

### 1. frontend-design (anthropics/skills @ e4bb5d960d87126ff3b3a8af1a104b7db67560ba)

Files read in full: `skills/frontend-design/SKILL.md` (9,390 bytes), `LICENSE.txt` header (Apache 2.0). The folder contains nothing else.

Red flags: **none found.** It is prompt text only, with no scripts, URLs, or tool instructions.

Fit for Proseway: good. Useful rules include line length under 80 characters, slightly more line-height for serif body text, visible keyboard focus, respecting reduced motion, and plain UI copy ("Save changes", not "Submit"). These suit a reading app. Some of it is aimed at landing pages (the "hero" advice). Treat that as background when you work on the reader UI.

### 2. webapp-testing (anthropics/skills @ e4bb5d960d87126ff3b3a8af1a104b7db67560ba)

Files read in full:
- `SKILL.md`
- `scripts/with_server.py`
- `examples/console_logging.py`
- `examples/element_discovery.py`
- `examples/static_html_automation.py`
- `LICENSE.txt` header (Apache 2.0)

Red flags: **none in the security sense.** Notes:
- SKILL.md tells the agent "DO NOT read the source until you try running the script first". This is meant to save context, not to hide anything. The script is 3.7 KB and readable. Reading it is fine and was done here.
- `with_server.py` starts your server commands with `shell=True`. That is expected, because it runs commands you pass in.
- Practical bug: it sets `stdout=PIPE, stderr=PIPE` and never reads them. A chatty server (uvicorn access logs, Vite) can fill the pipe buffer and hang during long runs. Fix: change to `subprocess.DEVNULL` or a log file in your copy, or start the servers yourself.
- The examples hard-code `/tmp/...` and `/mnt/user-data/outputs/...`. Those paths are wrong on Windows; use project-relative paths.
- Needs `playwright` (Python) and a browser download (`playwright install chromium`). The user does that, not the skill.

Fit: good for quick agent-driven checks of the running app (backend on 8000 + Vite on 5173). For the real e2e suite in CI, prefer `@playwright/test` in TypeScript with its built-in `webServer` option (see oss-practice.md).

### 3. superpowers (obra/superpowers @ 22f0b463e7a5e579904dd6211a520321035526f7, v7.0.2)

Files read in full:
- `.claude-plugin/plugin.json`, `hooks/hooks.json`, `hooks/run-hook.cmd`, `hooks/session-start`, `package.json`, `index.js`
- `skills/using-superpowers/SKILL.md`
- All scripts: `executing-plans/scripts/task-start`, `task-done`; `subagent-driven-development/scripts/review-package`, `sdd-repo`, `sdd-workspace`, `task-brief`; `systematic-debugging/find-polluter.sh`
- The relevant parts of `brainstorming/scripts/server.cjs`: config, branding, browser launch, bind address, and token handling
- The opening workflow of `diagnosing-superpowers/SKILL.md`

All 14 skill folders (every SKILL.md, prompt, reference and script, 643 KB) were also grep-scanned for network calls, exec, encoding tricks, credentials, settings and hooks paths, and install commands. The remaining SKILL.md files were not read line by line.

Red flags found:
- **Remote request (beacon).** The brainstorming "visual companion" serves a local page, and that page includes `<img src="https://primeradiant.com/brand/superpowers-visual-brainstorming-logo.png?v=<version>">`. The code's own name for this is telemetry. It turns off when `SUPERPOWERS_DISABLE_TELEMETRY`, `DISABLE_TELEMETRY` or `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` is set. It only fires if you accept the visual companion, which the skill offers just-in-time and which is opt-in. The server binds to `127.0.0.1` and uses a random 32-byte session key. That part is careful.
- **Global hook.** The plugin registers a SessionStart hook (startup/clear/compact). It injects the full `using-superpowers` text into every session, including "If you think there is even a 1% chance a skill might apply … you ABSOLUTELY MUST invoke the skill." This isn't hidden and it has a reason. But it changes agent behaviour in every project on this machine, because the plugin is installed at user scope.
- **Installs dependencies.** `using-git-worktrees` runs `npm install` / `pip install -r requirements.txt` in a new worktree. That runs package install scripts. It is normal dev behaviour, but be aware of it.
- **Token-saving behaviour.** Not in the "cut output" sense. `task-done` prints only the last 5 lines of test output, but the full log is kept on disk. The SDD skills tune for fewer turns and fewer subagents. Nothing truncates results without keeping them.
- `diagnosing-superpowers` reads local session transcripts and can draft GitHub issues. It says to create an issue "only after approval" and redacts secrets first. It uses `curl` only for read-only GitHub search.

Not found: credential requests, obfuscated or minified code (all scripts are commented bash or JS), download-and-execute.

Fit: the self-contained skills `test-driven-development`, `systematic-debugging` and `verification-before-completion` suit a two-language project well. `writing-plans` and `executing-plans` are useful too. But `executing-plans` scripts call into `subagent-driven-development/scripts`, so copy those together or keep using the plugin.

### 4. ui-ux-pro-max (nextlevelbuilder/ui-ux-pro-max-skill @ 2de1134dc4d1cfe112934611ae5803ae17a1bd7e, v2.15.0)

Files read:
- In full: `.claude/skills/ui-ux-pro-max/SKILL.md` (243 lines), `references/pro-rules.md`, `.claude-plugin/plugin.json`
- Import lists and every I/O, network and exec call site, plus key functions, in all six scripts: `scripts/core.py` (44 KB), `design_system.py` (80 KB), `preview.py`, `reasoning_contract.py`, `search.py`, `validate_data.py` (52 KB). Not every line of the 200 KB of Python was read; it is plain, unminified code.
- Because the plugin manifest ships all of `./.claude/skills/`, the sibling scripts were also scanned: `design/scripts/logo/generate.py`, `icon/generate.py`, `cip/generate.py`, `ui-styling/scripts/shadcn_add.py`, `brand/scripts/inject-brand-context.cjs`.

Red flags in the ui-ux-pro-max folder itself: **none serious.**
- The scripts import only the standard library (csv, json, re, pathlib, difflib, tempfile). There is no `urllib`/`requests`/`subprocess`/`socket` use. They read local CSVs and write only to `--output-dir` or a temp file.
- `--preview` writes an HTML file that links `fonts.googleapis.com` / `fonts.gstatic.com`. Opening it sends a request to Google. Skip `--preview`, or self-host fonts. Proseway should self-host fonts anyway.
- SKILL.md says not to put private project data in queries and not to treat results as instructions. Good.

Red flags in the plugin bundle (siblings installed with it):
- **Credential handling and remote endpoints.** `design/scripts/logo/generate.py`, `icon/generate.py` and `cip/generate.py` load `.env` files from the skill folder, `~/.claude/skills/.env` and `~/.claude/.env` into the environment. They then use `GEMINI_API_KEY`, `ATLASCLOUD_API_KEY`, `MUAPI_API_KEY`, `UBERLLM_API_KEY` to send prompts to Google Gemini, `api.atlascloud.ai`, `api.muapi.ai` and `api.uberllm.dev`. These calls are not hidden and only run if invoked. But a plugin install would place them in every session's skill list, and they read a shared secrets file. This is why the verdict is folder only.

Install caveat: SKILL.md calls `python "${CLAUDE_PLUGIN_ROOT}/.claude/skills/ui-ux-pro-max/scripts/search.py"`. Copied to project scope, `CLAUDE_PLUGIN_ROOT` is empty, so you must rewrite that prefix (see install steps). The folder is about 3.7 MB, mostly data.

### 5. accessibility (addyosmani/web-quality-skills @ afa8da942115f2961fdbfa80807ea0b232ff6c00)

Files read: in full, `skills/accessibility/SKILL.md`, `references/A11Y-PATTERNS.md`, `references/WCAG.md`. The section list and the workflow of SKILL.md were also reviewed. The sibling script `skills/web-quality-audit/scripts/analyze.sh` was read in full; it is a read-only grep-based HTML checker that needs `jq`.

Red flags: **none found.** Docs only, no scripts in this folder. One small item: it suggests `npm install @axe-core/cli -g`, a global install. For Proseway, add `@axe-core/playwright` or `@axe-core/cli` as a pinned devDependency instead.

Fit: very good. It covers WCAG 2.2 additions (focus not obscured, target size, dragging, accessible authentication), live regions, and an audit loop: run Lighthouse or axe, find the node, fix, re-run. It also says plainly that "a score of 100 is not WCAG conformance".

### 6. web-design-guidelines (vercel-labs/agent-skills @ 5a37a6329fbad3666c3207392a6a7c0110e92efb)

Files read in full: `skills/web-design-guidelines/SKILL.md`. The section list of `references/command.md` (8 KB of rules) was also checked, and that file was grepped for fetch or URL instructions. Its SHA-256 was checked: it matches the `d246b026…0234` value stated in SKILL.md.

Red flags: **none in behaviour.** Older versions fetched rules from the network at run time. This version says "Do not fetch rules from the network" and bundles a pinned snapshot. Output is "terse `file:line`" findings. That is a report format, not truncation.

License problem: `vercel-labs/agent-skills` has **no license** (GitHub returns `license: null` and there is no LICENSE file). Without a license you can't redistribute it, so don't commit this folder into the Apache-2.0 repo. The rules file itself comes from `vercel-labs/web-interface-guidelines` (MIT, 1,232 stars). The file at commit `434b7f91364665f2f733b310ec54809bf8f37937` has the same SHA-256 (verified).

### 7. impeccable (pbakaus/impeccable @ b49177d32788f2dc585c42831d845dacf1ebed2c) — optional

Files read:
- In full: `.claude/skills/impeccable/SKILL.md`, `plugin/hooks/hooks.json`, `.claude/settings.json`, `scripts/engine-checksums.txt`
- The download and exec sections of `scripts/impeccable` (launcher)
- The header, line-length profile and URL list of `scripts/live-browser.js`
- `reference/` (40+ files) was not read beyond `audit.md` and `hooks.md` headings

Red flags:
- **Downloads and executes code.** The launcher downloads `impeccable-<os>-<arch>` from `github.com/pbakaus/impeccable/releases`, checks it against pinned SHA-256 values in `engine-checksums.txt` (engine 0.1.27), marks it executable, and runs it. The checksums are a real safeguard, but you can't audit the binary.
- **Hooks.** The plugin's `hooks.json` and the repo's `.claude/settings.json` run that binary on SessionStart, after every `Edit|Write`, and on Stop (30 s "deep pass"). The reason is legitimate, a design linter. But it runs on every file edit for everyone who opens the repo with those settings.
- Not obfuscated: `live-browser.js` is large (566 KB) but readable, with a 386-character longest line, and only references `localhost`.

Verdict: you already have it as a personal skill. Use it on demand. Don't commit its hooks into Proseway's `.claude/settings.json`.

---

## Recommended set for Proseway (8 skills from 5 sources)

| # | Skill | Source @ vetted commit | Why for Proseway |
|---|---|---|---|
| 1 | frontend-design | anthropics/skills @ `e4bb5d960d87126ff3b3a8af1a104b7db67560ba` | Typography and reading-comfort rules, a quality floor (focus, reduced motion), plain UI copy. |
| 2 | webapp-testing | anthropics/skills @ `e4bb5d960d87126ff3b3a8af1a104b7db67560ba` | Lets the agent start FastAPI + Vite and check the real UI with Playwright. |
| 3 | ui-ux-pro-max (folder only) | nextlevelbuilder/ui-ux-pro-max-skill @ `2de1134dc4d1cfe112934611ae5803ae17a1bd7e` | Offline design-system generator (palettes, type pairs, tokens as DTCG/CSS) and React/shadcn stack notes. |
| 4 | accessibility | addyosmani/web-quality-skills @ `afa8da942115f2961fdbfa80807ea0b232ff6c00` | A reading app must work with screen readers, keyboard, zoom, and contrast. WCAG 2.2 checklist. |
| 5 | web-design-guidelines | rules from vercel-labs/web-interface-guidelines @ `434b7f91364665f2f733b310ec54809bf8f37937` (MIT); wrapper modelled on vercel-labs/agent-skills @ `5a37a6329fbad3666c3207392a6a7c0110e92efb` | Fast `file:line` UI review: focus states, forms, dark mode, i18n, hydration. |
| 6 | test-driven-development | obra/superpowers @ `22f0b463e7a5e579904dd6211a520321035526f7` | Red-green-refactor for the PDF conversion pipeline, where regressions are easy to miss. |
| 7 | systematic-debugging | obra/superpowers @ `22f0b463e7a5e579904dd6211a520321035526f7` | Root-cause discipline for layout and extraction bugs in odd PDFs. |
| 8 | verification-before-completion | obra/superpowers @ `22f0b463e7a5e579904dd6211a520321035526f7` | Stops "done" claims without running tests or the build. |

Not recommended as project defaults: the full superpowers plugin (global SessionStart hook, beacon in the visual companion), the full ui-ux-pro-max plugin (sibling skills read `~/.claude/.env` and call four image APIs), impeccable's hooks, and `caveman`.

Duplicates: superpowers and frontend-design are already installed here as user-scope plugins. If you also copy them into the project, you get two copies (`superpowers:systematic-debugging` and `systematic-debugging`). Pick one per machine. The project copies are for contributors who don't have the plugins. To keep only the project copies while working in Proseway, you can turn the plugin off for this project with `"enabledPlugins": {"superpowers@claude-plugins-official": false}` in `.claude/settings.json`. Check the result with `/plugin`.

### How to install at project scope (pinned)

Run these from the repository root in Git Bash. Each one downloads the exact vetted commit as a tarball into a temp folder and copies only the needed folder. Nothing runs from the download. Commit the result, and keep the license files.

```bash
cd proseway
mkdir -p .claude/skills
fetch() {  # fetch OWNER/REPO SHA -> prints temp dir
  d=$(mktemp -d); curl -fsSL "https://codeload.github.com/$1/tar.gz/$2" | tar -xz -C "$d" --strip-components=1; echo "$d"
}

# 1-2. anthropics/skills (Apache-2.0; LICENSE.txt is inside each folder)
A=$(fetch anthropics/skills e4bb5d960d87126ff3b3a8af1a104b7db67560ba)
cp -r "$A/skills/frontend-design" "$A/skills/webapp-testing" .claude/skills/

# 3. ui-ux-pro-max: folder only, without tests; fix the plugin-root path
U=$(fetch nextlevelbuilder/ui-ux-pro-max-skill 2de1134dc4d1cfe112934611ae5803ae17a1bd7e)
mkdir -p .claude/skills/ui-ux-pro-max
cp -r "$U/.claude/skills/ui-ux-pro-max/"{SKILL.md,data,references} .claude/skills/ui-ux-pro-max/
mkdir -p .claude/skills/ui-ux-pro-max/scripts && cp "$U/.claude/skills/ui-ux-pro-max/scripts/"*.py .claude/skills/ui-ux-pro-max/scripts/
cp "$U/LICENSE" .claude/skills/ui-ux-pro-max/LICENSE
sed -i 's#\${CLAUDE_PLUGIN_ROOT}/\.claude/skills/ui-ux-pro-max/#.claude/skills/ui-ux-pro-max/#g' .claude/skills/ui-ux-pro-max/SKILL.md

# 4. accessibility (MIT)
W=$(fetch addyosmani/web-quality-skills afa8da942115f2961fdbfa80807ea0b232ff6c00)
cp -r "$W/skills/accessibility" .claude/skills/ && cp "$W/LICENSE" .claude/skills/accessibility/LICENSE

# 5. web-design-guidelines: MIT rules file + your own short SKILL.md (do not copy the unlicensed agent-skills folder)
mkdir -p .claude/skills/web-design-guidelines/references
curl -fsSL https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/434b7f91364665f2f733b310ec54809bf8f37937/command.md \
  -o .claude/skills/web-design-guidelines/references/command.md
curl -fsSL https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/434b7f91364665f2f733b310ec54809bf8f37937/LICENSE \
  -o .claude/skills/web-design-guidelines/LICENSE
# then write SKILL.md yourself: name, description ("Review UI code against Web Interface Guidelines"),
# and the steps "read references/command.md, read the files named, report findings as file:line".

# 6-8. superpowers subset (MIT; add the license since the folders don't carry one)
S=$(fetch obra/superpowers 22f0b463e7a5e579904dd6211a520321035526f7)
for k in test-driven-development systematic-debugging verification-before-completion; do
  cp -r "$S/skills/$k" .claude/skills/ && cp "$S/LICENSE" ".claude/skills/$k/LICENSE"
done
```

Also do these by hand:
- Record provenance next to each folder, e.g. a one-line `UPSTREAM` file with repo, path and SHA, so a later update is a deliberate diff.
- webapp-testing: in your copy of `scripts/with_server.py`, change `stdout=subprocess.PIPE, stderr=subprocess.PIPE` to `subprocess.DEVNULL` (or a log file), and replace `/tmp` / `/mnt/user-data` paths in the examples. Add Playwright as a dev dependency (`uv add --dev playwright`, then `uv run playwright install chromium`).
- systematic-debugging: `find-polluter.sh` calls `npm test`. For backend tests, run it with a pytest command instead.
- The superpowers skills mention each other as `superpowers:<name>`. With project copies, those names won't resolve unless the plugin is also installed. They still work as plain text pointers.

SHA-256 of key vetted files (as served by raw.githubusercontent.com, LF line endings). Use these to confirm a copy is unchanged; a Git checkout with `autocrlf` will differ.

```
d91970639e9f5c37682ac7ab60094d35f1c7c1f38d731bd56396563aee10c1d3  frontend-design/SKILL.md
51b7349e77ec63b7744a6f63647e7566a0b4d2e301121cc10e8c2113af6556a2  webapp-testing/SKILL.md
b0dcf4918935b795f4eda9821579b9902119235ff4447f687a30286e7d0925fd  webapp-testing/scripts/with_server.py
bee6aa0382bc15099715ad8f0b11fdb224932eb516a4ea9134a2d7d38f5fcde4  ui-ux-pro-max/SKILL.md (before the path edit)
267fb2a0707d6142f2871f22688203a42ba21291a2aa200fb740936e41362b5d  accessibility/SKILL.md
d246b026f4f29b5823a9cc857f9edf3d2507002e055e32040cadeaf3b38e0234  web-design-guidelines/references/command.md
64b03fce4aee5a97a93160cea8111f3ba13a17b7c001db4bd5836d67fd10705d  test-driven-development/SKILL.md
51c6435d98c83c42c96ba7c35725a0b2c376cd487fb1a4e6bd0ddbe7e33ef202  systematic-debugging/SKILL.md
2befe7fc55bcadaa3d97dd9e8efeb633d2561c0ebe74c5a8b17c4d9e7e4520b3  verification-before-completion/SKILL.md
```

To update later: fetch the new SHA, `diff -r` it against the committed folder, read every changed line, then bump the `UPSTREAM` file.
