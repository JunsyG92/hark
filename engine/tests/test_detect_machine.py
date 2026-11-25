from __future__ import annotations

from hark_engine.detect import DetectionMachine
from hark_engine.models import DetectionPhase, DetectionSettings, PromptAction

LOUD = -25.0
QUIET = -70.0


def run(machine: DetectionMachine, seconds: float, level: float, mic: bool | None, start=0.0):
    """Feed one level per 0.25 s. Returns (first prompt, time of prompt)."""
    t = start
    while t < start + seconds:
        p = machine.feed(t, level, mic, app="teams")
        if p:
            return p, t
        t += 0.25
    return None, t


def test_youtube_alone_never_prompts():
    m = DetectionMachine(DetectionSettings())
    prompt, _ = run(m, 600, LOUD, mic=False)  # 10 minutes of loud audio, mic unused
    assert prompt is None and m.phase == DetectionPhase.IDLE


def test_call_prompts_after_min_seconds():
    m = DetectionMachine(DetectionSettings(min_seconds=8))
    prompt, at = run(m, 30, LOUD, mic=True)
    assert prompt is not None and prompt.app == "teams"
    assert 8.0 <= at <= 8.5
    assert m.phase == DetectionPhase.PROMPTED


def test_short_pauses_do_not_reset_but_long_silence_does():
    m = DetectionMachine(DetectionSettings(min_seconds=8))
    t = 0.0
    for _ in range(3):  # 3 s loud + 1.5 s pause, repeated: pauses ≤ tolerance
        _, t = run(m, 3, LOUD, True, t)
        _, t = run(m, 1.5, QUIET, True, t)
    assert m.phase in (DetectionPhase.PROMPTED, DetectionPhase.IDLE)
    m2 = DetectionMachine(DetectionSettings(min_seconds=8))
    run(m2, 6, LOUD, True, 0)
    run(m2, 5, QUIET, True, 6)  # > 2 s gap resets the counter
    prompt, _ = run(m2, 5, LOUD, True, 11)  # only 5 s more: not enough
    assert prompt is None


def test_mic_signal_required_only_when_configured():
    audio_only = DetectionMachine(DetectionSettings(require_mic_in_use=False))
    assert run(audio_only, 20, LOUD, mic=None)[0] is not None
    strict = DetectionMachine(DetectionSettings(require_mic_in_use=True))
    assert run(strict, 20, LOUD, mic=None)[0] is None  # unsupported OS probe -> no prompt


def test_timeout_is_ignore_with_cooldown():
    s = DetectionSettings(prompt_seconds=20, cooldown_ignore_minutes=10)
    m = DetectionMachine(s)
    _, t = run(m, 30, LOUD, True)
    m.poll(t + 21)
    assert m.phase == DetectionPhase.COOLDOWN
    # still loud and mic used, but cooldown: no new prompt for 10 minutes
    assert run(m, 500, LOUD, True, t + 21)[0] is None
    prompt, _ = run(m, 200, LOUD, True, t + 21 + 500)
    assert prompt is not None


def test_decline_uses_longer_cooldown():
    s = DetectionSettings(cooldown_ignore_minutes=1, cooldown_decline_minutes=30)
    m = DetectionMachine(s)
    prompt, t = run(m, 30, LOUD, True)
    assert prompt and m.respond(t, prompt.id, PromptAction.DECLINE)
    assert run(m, 25 * 60, LOUD, True, t)[0] is None
    assert run(m, 10 * 60, LOUD, True, t + 25 * 60)[0] is not None


def test_record_stops_prompts_until_recorder_releases():
    m = DetectionMachine(DetectionSettings())
    prompt, t = run(m, 30, LOUD, True)
    assert prompt and m.respond(t, prompt.id, PromptAction.RECORD)
    assert m.phase == DetectionPhase.RECORDING
    assert run(m, 3600, LOUD, True, t)[0] is None


def test_wrong_or_stale_prompt_id_is_rejected():
    m = DetectionMachine(DetectionSettings())
    prompt, t = run(m, 30, LOUD, True)
    assert prompt
    assert not m.respond(t, "other", PromptAction.RECORD)
    assert m.phase == DetectionPhase.PROMPTED
    assert m.respond(t, prompt.id, PromptAction.IGNORE)
    assert not m.respond(t, prompt.id, PromptAction.RECORD)  # already answered


def test_disabled_never_prompts_and_force_prompt_works():
    m = DetectionMachine(DetectionSettings(enabled=False))
    assert m.phase == DetectionPhase.DISABLED
    assert run(m, 60, LOUD, True)[0] is None
    m2 = DetectionMachine(DetectionSettings())
    assert m2.force_prompt(0.0) is not None
    assert m2.force_prompt(1.0) is None  # one prompt at a time
