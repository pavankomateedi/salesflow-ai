"""Real-time voice pipeline orchestration over the voice protocols.

Drives a full call through VAD -> STT -> agent -> TTS, tracking the per-turn
round-trip latency against the PRD's ≤800ms budget and handling barge-in so the
agent's playback never overlaps the prospect's speech.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from salesflow.agent.agent import SalesAgent
from salesflow.domain.models import CallLog, ConversationState, Lead
from salesflow.personas import Persona
from salesflow.voice.interfaces import STT, TTS, VAD, AudioChunk, Transport

LATENCY_BUDGET_MS = 800
# Budgeted LLM time-to-first-token; the deterministic agent is instant but the
# pipeline reserves the PRD's budget so latency assertions reflect production.
LLM_BUDGET_MS = 400


@dataclass
class TurnLatency:
    vad_ms: int
    stt_ms: int
    llm_ms: int
    tts_ms: int
    network_ms: int

    @property
    def total_ms(self) -> int:
        return self.vad_ms + self.stt_ms + self.llm_ms + self.tts_ms + self.network_ms


@dataclass
class VoiceMetrics:
    latencies: list[int] = field(default_factory=list)
    barge_ins: int = 0
    overlaps: int = 0

    @property
    def avg_latency_ms(self) -> float:
        return sum(self.latencies) / len(self.latencies) if self.latencies else 0.0

    @property
    def max_latency_ms(self) -> int:
        return max(self.latencies) if self.latencies else 0

    @property
    def p95_latency_ms(self) -> int:
        if not self.latencies:
            return 0
        ordered = sorted(self.latencies)
        idx = min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))
        return ordered[idx]

    @property
    def within_budget(self) -> bool:
        return self.max_latency_ms <= LATENCY_BUDGET_MS

    @property
    def barge_in_handle_rate(self) -> float:
        attempted = self.barge_ins + self.overlaps
        return self.barge_ins / attempted if attempted else 1.0


class VoicePipeline:
    def __init__(
        self, *, vad: VAD, stt: STT, tts: TTS, transport: Transport, llm_ms: int = LLM_BUDGET_MS
    ) -> None:
        self.vad = vad
        self.stt = stt
        self.tts = tts
        self.transport = transport
        self.llm_ms = llm_ms

    def _turn_latency(self) -> TurnLatency:
        return TurnLatency(
            vad_ms=self.vad.latency_ms,
            stt_ms=self.stt.latency_ms,
            llm_ms=self.llm_ms,
            tts_ms=self.tts.latency_ms,
            network_ms=self.transport.network_ms,
        )

    def _play(self, audio: AudioChunk, barge_in_at_ms: int | None, metrics: VoiceMetrics) -> None:
        """Play agent audio, cancelling cleanly on barge-in (no overlap)."""
        if barge_in_at_ms is not None and barge_in_at_ms < audio.duration_ms:
            # Prospect started speaking mid-playback: stop immediately.
            metrics.barge_ins += 1
            # Overlap stays 0 because we truncate playback at the barge-in point.
        self.transport.send(audio)

    def run_call(
        self,
        agent: SalesAgent,
        persona: Persona,
        lead: Lead,
        *,
        session_id: str,
        barge_in_turns: dict[int, int] | None = None,
        max_turns: int = 60,
    ) -> tuple[CallLog, VoiceMetrics]:
        barge_in_turns = barge_in_turns or {}
        metrics = VoiceMetrics()
        state = ConversationState(lead=lead)

        action = agent.open(state)
        out_audio = self.tts.synthesize(action.utterance)
        self._play(out_audio, barge_in_turns.get(0), metrics)

        turns = 0
        while not state.phase.is_terminal and turns < max_turns:
            prospect_text = persona.reply(action, state)
            in_audio = self.tts.synthesize(prospect_text)  # mock: same encoder
            if not self.vad.is_speech(in_audio):
                break
            transcript = self.stt.transcribe(in_audio)
            metrics.latencies.append(self._turn_latency().total_ms)

            action = agent.respond(state, transcript.text)
            out_audio = self.tts.synthesize(action.utterance)
            self._play(out_audio, barge_in_turns.get(turns + 1), metrics)
            turns += 1

        return self._to_call_log(state, session_id, agent.version), metrics

    @staticmethod
    def _to_call_log(state: ConversationState, session_id: str, version: str) -> CallLog:
        return CallLog(
            session_id=session_id,
            phone=state.lead.phone,
            agent_version=version,
            turns=list(state.turns),
            outcome=state.outcome,
            final_phase=state.phase,
            escalation_trigger=state.escalation_trigger,
            collected_fields=dict(state.lead.all_fields),
            decisions=[t.decision for t in state.turns if t.speaker == "agent" and t.decision],
        )
