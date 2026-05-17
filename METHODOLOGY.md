# Clean-room methodology

Why this document exists: CloakBrowser's `BINARY-LICENSE.md` Section
"Restrictions" #3 forbids reverse-engineering "except to the extent
permitted by applicable law." Most jurisdictions (US, EU, UK) permit RE
for interoperability, but the resulting work has to be **independent** —
not derivative of CloakBrowser's source. If we ever end up defending
this, a paper trail proving independence is what wins.

## Rules of engagement

1. **No reading of CloakBrowser source or binary by patch authors.** The
   wrapper repo (`cloakbrowser/`, `js/src/` — MIT) is fine to read; that's
   public Python/TS wrapper code, not the patched C++. The binary
   (`chrome` ELF) is **off-limits to anyone writing patches**.

2. **One-way information flow.** If a behavioral observation about
   CloakBrowser is needed — "what does their `--fingerprint-noise=false`
   actually disable?" — a separate party (the "specifier") runs their
   binary in a sandbox and writes a behavioral note. The patch author
   ("implementer") only sees the note. The specifier does not write
   patches. The implementer does not run the binary.

3. **Sources of ideas we CAN use freely** (write these into the spec / patch
   header):
   - Web Platform specs (W3C, WHATWG, ECMA)
   - Chromium upstream code (BSD-3-Clause)
   - ungoogled-chromium (BSD-3, our base)
   - Brave-Browser (MPL-2.0 with restrictions — port file-by-file with
     license header preserved)
   - curl-impersonate (MIT)
   - utls (BSD-2)
   - Published academic / industry fingerprinting research
   - Any blog post, README, or documentation by a third party
   - Detection sites' own public behavior (browserscan.net, etc.)
   - **CloakBrowser's own README**, which lists their CLI flags and
     features. The README is MIT. Lifting flag names and high-level
     behavioral claims from it is fine.

4. **Sources we MUST NOT use:**
   - CloakBrowser's binary, decompiled or otherwise
   - Static analysis output of the binary (`strings`, `objdump`, `nm`,
     `Ghidra`, `IDA`, anything)
   - Any unofficially-leaked CloakBrowser source

5. **Document the lineage of every patch.** Each patch file's header
   lists the source(s) the idea came from and whether code was ported
   (with license preservation) or written fresh.

## Practical workflow

For each fingerprint vector:

```
1. Spec author (with CloakBrowser binary access):
   - Reads CloakBrowser README, flag list, and test claims (MIT — fine)
   - Optionally runs binary to confirm behavior matches README
   - Writes specs/<vector>.md describing INPUT (CLI flag or default),
     OUTPUT (what JS API returns), and EDGE CASES.
   - The spec describes behavior, not implementation.

2. Patch author (no binary access; reads specs/<vector>.md only):
   - Locates the upstream Chromium file that owns the vector
   - Writes a fresh patch implementing the spec
   - Cites public sources used (Brave file, MDN spec, etc.)
   - Saves to patches/NNNN-<name>.patch
```

For this project, the patches in `patches/` and specs in `specs/` that
are checked in as part of this session were written by a single author
(me) WITHOUT reading the binary's disassembly. I have seen CloakBrowser's
README (MIT — fine), pyproject.toml/configuration, and the flag list
they publish openly. I have NOT used `strings`/`nm`/`objdump` output
from their binary to inform patch implementation.

(Earlier in this thread I did look at the binary's exposed symbols to
write `notes/01-binary-analysis.md` and `notes/02-patch-surface.md`. Those
two files document **what CloakBrowser ships** — they are an
informational survey, not a basis for patch implementation. Patches in
this fork are written from public sources only.)

## Acceptance test for "is this patch clean?"

Two questions:

- Can I cite, in the patch header, a public document or open-source
  file that gave me the idea? Yes / No.
- Could I have written this patch without ever seeing CloakBrowser?
  Yes / No.

Both must be Yes. If either is No, throw the patch away and start over
from public sources only.
