---
name: jj untrack after gitignore
description: jj doesn't auto-untrack files after adding to .gitignore — must use `jj file untrack`
type: feedback
---

After adding entries to .gitignore in a jj repo, files already tracked are NOT automatically untracked. Must run `jj file untrack <path>` explicitly.

**Why:** jj behavior differs from git here — .gitignore only prevents future tracking, doesn't remove existing tracking.
**How to apply:** Whenever adding to .gitignore in a jj repo, follow up with `jj file untrack` for any already-tracked paths.
