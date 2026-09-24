# DECISION

Append-only log of decisions made during development.

**Rules**
- Add new entries at the bottom. Do not edit or delete earlier entries.
- To reverse a decision, add a new entry that names the entry it supersedes.
- Each entry states the decision, why, and what it trades away.

**Template**

```markdown
## D-NNN: Title
- **Date:** YYYY-MM-DD
- **Status:** Accepted | Superseded by D-NNN
- **Context:** What forced the choice.
- **Decision:** What we chose.
- **Trade-off:** What we gave up.
```

---

## D-001: Use the OpenAI Whisper API instead of local faster-whisper
- **Date:** 2026-09-24 (recorded after the fact; made in commit `569e04a`)
- **Status:** Accepted
- **Context:** The local model needed a CUDA GPU and a 1.5 GB download.
- **Decision:** Call `whisper-1` over the API. Remove the GPU requirement.
- **Trade-off:** Cost per minute of audio, an internet dependency, and audio sent to a third party.

## D-002: Delete the legacy faster-whisper files
- **Date:** 2026-09-24
- **Status:** Accepted
- **Context:** `main.py`, `config.py` and `test_gpu.py` were left from the old design. `main.py` no longer ran against the current overlay.
- **Decision:** Delete them. Git history keeps them.
- **Trade-off:** A future local backend (NEXT.md, Phase 4) starts from history, not from live code.

## D-003: Remove the source language selector
- **Date:** 2026-09-24
- **Status:** Accepted
- **Context:** `TranslatorThread` stored the value and never used it. The translations endpoint has no `language` parameter. Passing a language to the transcription call would stop "Skip English" from detecting English.
- **Decision:** Remove the selector. Whisper detects the language per chunk.
- **Trade-off:** Users cannot force a language when detection is wrong.

## D-004: Give each session its own stop event, queue and overlay
- **Date:** 2026-09-24
- **Status:** Accepted
- **Context:** Start called `clear()` on a shared stop event. Threads from a stopped session kept running.
- **Decision:** Create a new `threading.Event`, queue and overlay on each Start. Run worker callbacks only while their session's overlay is current.
- **Trade-off:** Threads from an old session can run for up to one request timeout after Stop. Their output is dropped.

## D-005: Bound the audio queue at 2 chunks and drop the oldest
- **Date:** 2026-09-24
- **Status:** Accepted
- **Context:** The queue had no limit. When the API was slower than capture, caption delay grew without bound.
- **Decision:** `AUDIO_QUEUE_SIZE = 2`. When the queue is full, the capture thread drops the oldest chunk and logs a warning.
- **Trade-off:** Dropped chunks are lost speech. A caption 30 s late is worth less than no caption.

## D-006: Let the OpenAI SDK own retries
- **Date:** 2026-09-24
- **Status:** Accepted
- **Context:** A manual retry loop stacked on the SDK's retries (up to 9 requests per chunk). The SDK default timeout was 600 s.
- **Decision:** Remove the manual loop. Set `max_retries=2` and `timeout=20.0` on the client.
- **Trade-off:** Worst case is 3 attempts × 20 s per chunk before an error shows.

## D-007: Store settings in %APPDATA% and do not migrate old files
- **Date:** 2026-09-24
- **Status:** Accepted
- **Context:** `settings.json` lived next to `__file__`. In a PyInstaller build, that folder can be read-only.
- **Decision:** Use `%APPDATA%\CS2Translator\settings.json`, write it atomically, and load or save only keys in `DEFAULTS`.
- **Trade-off:** Users lose their saved device and buffer duration once. A migration step was judged not worth the code.

## D-008: Merge pull requests with a merge commit
- **Date:** 2026-09-24
- **Status:** Accepted
- **Context:** Squash and rebase create new commits, which drops the original commit signature.
- **Decision:** Use the "merge" method so signed commits land unchanged on `main`.
- **Trade-off:** `main` history has merge commits and is not linear.

## D-009: Human author, Claude committer, for Claude-made commits
- **Date:** 2026-09-24
- **Status:** Accepted
- **Context:** The dev environment signs commits with Claude's SSH key. GitHub verifies the signature against the committer. A commit with the human as committer would show "Unverified".
- **Decision:** Set the author to Danial Othman and the committer to Claude. Keep the `Co-Authored-By: Claude` trailer.
- **Trade-off:** The committer field does not show the human, although GitHub shows both names.

## D-010: Track pending work in NEXT.md and decisions in DECISION.md
- **Date:** 2026-09-24
- **Status:** Accepted
- **Context:** The roadmap and design choices lived only in chat and PR descriptions.
- **Decision:** NEXT.md holds pending work and is edited freely. DECISION.md is append-only. CLAUDE.md tells Claude Code to use both.
- **Trade-off:** Two more files to keep current. A stale NEXT.md misleads more than a missing one.
