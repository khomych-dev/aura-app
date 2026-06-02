# Current Task

> Цей файл читає Director на початку кожної сесії та оновлює після кожного кроку.

## Task

**Aura v0.5.3 — Bug Fix: Audio Post-Roll Padding (Whisper Clipping)**

Whisper API frequently drops the last word or misrecognizes it during rapid dictation.
Root cause: the microphone stream is terminated the exact millisecond the trigger key is released,
cutting off the trailing audio frequencies of the final word. Whisper requires a small trailing
silence to correctly decode the final token.

## Type

Баг-фікс (є опис) — production audio quality

## Status

Done

## Agent Chain

- [x] Developer — done (config.py POST_ROLL_PADDING_MS, recorder.py abort(), app.py QTimer post-roll, hotkey.py injected-swallow fix)
- [x] QA — APPROVED (94/94 tests, 88.91% coverage, ruff clean, mypy clean; 1 missing shutdown test added)

## Spec / Decisions

### Root Cause

Strict Push-to-Talk audio clipping: the audio stream is terminated immediately on key release
(`stop_signal` received), with zero trailing silence. Whisper's decoder cannot finalize the
last token without a brief period of silence after speech ends.

### Fix Requirements

- When the stop signal is received (trigger key released), the audio recorder **MUST NOT**
  terminate the stream immediately.
- Instead, it must **continue capturing audio for an additional 400ms (0.4 seconds)** after
  the stop signal before finalizing the WAV buffer.
- This "post-roll" silence gives Whisper enough trailing context to correctly decode the final
  word/token.
- The 400ms value should be a named constant (e.g. `POST_ROLL_PADDING_MS = 400`) — ideally
  in `config.py` or co-located with the recorder logic.
- The rest of the pipeline (WAV finalization → Whisper API call → text injection) must be
  unchanged — only the termination timing of the audio capture changes.
- The Developer must locate the audio recording stop logic autonomously using the project
  structure in MEMORY.md.

### Constraints

- Do NOT hard-code `400` inline — use a named constant.
- Do NOT change the public interface of the recorder beyond what is needed.
- Post-roll must not add latency to the overall UX beyond the 400ms itself.

## Implementation Notes

### config.py
- Added `POST_ROLL_PADDING_MS: int = 400` — named constant, used in both `app.py` (QTimer) and docs

### recorder.py
- Added `abort()` — stops stream + discards frames immediately without writing WAV; used by `app.py` when a new recording starts before the post-roll timer fires

### app.py
- `_on_recording_started`: cancels active post-roll timer and calls `recorder.abort()` before starting fresh — handles rapid re-press edge case
- `_on_recording_stopped`: now hides indicator + resolves language immediately, then schedules `_finalize_recording` via `QTimer.singleShot(POST_ROLL_PADDING_MS)` — returns immediately without blocking the main thread
- `_finalize_recording` (new `@Slot`): called by the timer after 400ms — calls `recorder.stop()`, writes WAV, starts transcription
- `shutdown()`: stops post-roll timer + calls `abort()` if timer was active during teardown
- Import: added `QTimer` to PySide6 imports

### hotkey.py (pre-existing regression fixed)
- `_hook_callback`: moved `should_swallow = True` inside the `not LLKHF_INJECTED` guard — injected trigger-key events (e.g. from TextInjector) now correctly forward via `CallNextHookEx` instead of being swallowed

### tests
- `test_recorder.py`: 3 new tests for `abort()` (idle no-op, clears frames/closes stream, no WAV write)
- `test_app.py`: existing `_on_recording_stopped` transcription-behaviour tests moved to `_finalize_recording`; 4 new `_on_recording_stopped` tests (timer scheduling, pending language, timer reuse, immediate hide); 1 new `_on_recording_started` test for post-roll cancellation

## Next Step

QA to run full test suite, coverage, ruff, mypy.

## Skipped

- Analyst — full root cause and fix requirements specified directly in task
- Architect — no architectural changes; targeted timing fix in recorder only
- Security — no auth/payments/credentials changes
- AI Safety — no LLM prompt changes
