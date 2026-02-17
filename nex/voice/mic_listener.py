"""
MicListener — Real microphone input for Nex.

Captures audio from the default microphone, detects speech using energy-based
VAD, transcribes with mlx-whisper (Apple Silicon optimized), and publishes
"system.command" so the existing CommandHandler processes it.

Wake word gated: only activates when the utterance starts with "Nex"
(e.g. "Nex go check the weather", "Nex what time is it").
All other speech is silently ignored — no Whisper, no LLM, no delay.

Mutes during TTS playback to prevent feedback loops.
Integrates voice authentication to block unauthorized speakers.
"""

import asyncio
import re
import time

import numpy as np
import sounddevice as sd

from nex.core.event_bus import EventBus
from nex.utils.logger import setup_logger

logger = setup_logger(__name__)

# Audio capture settings
SAMPLE_RATE = 16000
CHANNELS = 1
BLOCK_SIZE = 1024  # samples per callback (~64ms at 16kHz)

# Voice activity detection
SILENCE_THRESHOLD = 0.02   # RMS amplitude — tune up if too sensitive
SILENCE_DURATION = 1.5     # seconds of silence to end recording
MIN_SPEECH_DURATION = 0.5  # seconds minimum to avoid noise triggers
MAX_SPEECH_DURATION = 30   # seconds cap to prevent runaway recording

# Whisper model (small, fast on Apple Silicon)
WHISPER_MODEL = "mlx-community/whisper-base-mlx"

# Wake word — utterance must start with one of these to activate
# Regex strips the wake prefix so the LLM gets just the command
_WAKE_RE = re.compile(
    r"^\s*(?:"
    r"(?:hey[\s,.:!]*)?(?:nex|next|necks?|nix|knex|lex)[\s,.:!]*(?:go[\s,.:!]*)?"
    r")",
    re.IGNORECASE,
)


def _extract_command(text: str) -> str | None:
    """If text starts with a wake phrase, return the command part. Otherwise None."""
    m = _WAKE_RE.match(text)
    if m:
        command = text[m.end():].strip()
        return command if command else None
    return None


class MicListener:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self._running = False
        self._muted = False
        self._recording = False
        self._audio_buffer: list[np.ndarray] = []
        self._silence_start: float | None = None
        self._speech_start: float | None = None
        self._stream: sd.InputStream | None = None
        self._process_lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

        # Voice authentication
        self._voice_auth = None
        self._enrolling = False
        self._enrollment_samples: list[np.ndarray] = []
        self._enrollment_count = 3  # Number of samples needed

    async def start(self):
        """Start listening on the default microphone."""
        self._loop = asyncio.get_running_loop()
        self._running = True

        # Initialize voice auth (lazy — encoder loads on first use)
        try:
            from nex.api.voice_auth import VoiceAuth
            self._voice_auth = VoiceAuth()
            if self._voice_auth.is_enrolled():
                logger.info("Voice authentication active")
            else:
                logger.info("Voice authentication available (not enrolled)")
        except ImportError:
            logger.warning("resemblyzer not installed — voice auth disabled")
            self._voice_auth = None

        # Subscribe to TTS events to mute mic during speech
        self.event_bus.subscribe("command.response", self._on_tts_start)

        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            blocksize=BLOCK_SIZE,
            dtype="float32",
            callback=self._audio_callback,
        )
        self._stream.start()
        logger.info(f"MicListener started — say 'Nex go ...' to activate (device: {sd.query_devices(kind='input')['name']})")

    async def stop(self):
        """Stop listening."""
        self._running = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        logger.info("MicListener stopped.")

    def start_enrollment(self):
        """Begin voice enrollment — next N utterances become training samples."""
        self._enrolling = True
        self._enrollment_samples = []
        logger.info("Voice enrollment started — collecting samples")

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status):
        """
        Called by sounddevice from the audio thread for each block of samples.
        Detects speech onset/offset and schedules transcription.
        """
        if not self._running or self._muted:
            return

        rms = float(np.sqrt(np.mean(indata ** 2)))
        now = time.monotonic()

        # Broadcast mic level ~10x/sec (every ~6 blocks at 16kHz/1024)
        if not hasattr(self, '_level_counter'):
            self._level_counter = 0
        self._level_counter += 1
        if self._level_counter % 6 == 0 and self._loop is not None:
            level = min(100, int(rms * 5000))  # Scale RMS to 0-100
            self._loop.call_soon_threadsafe(
                lambda lvl=level, rec=self._recording: self._loop.create_task(
                    self.event_bus.publish("mic.level", {
                        "level": lvl,
                        "recording": rec,
                        "muted": self._muted,
                    })
                )
            )

        if rms > SILENCE_THRESHOLD:
            # Speech detected
            self._silence_start = None

            if not self._recording:
                # Start a new recording
                self._recording = True
                self._speech_start = now
                self._audio_buffer = []
                logger.debug("Speech started")
                # Notify UI that speech was detected
                if self._loop is not None:
                    self._loop.call_soon_threadsafe(
                        lambda: self._loop.create_task(
                            self.event_bus.publish("mic.speech_detected", {"active": True})
                        )
                    )

            self._audio_buffer.append(indata.copy())

            # Cap recording length
            if self._speech_start and (now - self._speech_start) > MAX_SPEECH_DURATION:
                self._recording = False
                self._schedule_transcription()

        elif self._recording:
            # Below threshold but still recording — accumulate silence
            self._audio_buffer.append(indata.copy())

            if self._silence_start is None:
                self._silence_start = now
            elif (now - self._silence_start) >= SILENCE_DURATION:
                # Enough silence — end recording
                self._recording = False

                # Check minimum duration
                duration = now - (self._speech_start or now)
                if duration >= MIN_SPEECH_DURATION:
                    self._schedule_transcription()
                else:
                    self._audio_buffer = []
                    logger.debug("Speech too short, discarded")

    def _schedule_transcription(self):
        """Schedule transcription on the event loop from the audio thread."""
        audio = self._audio_buffer
        self._audio_buffer = []
        if self._loop is not None:
            self._loop.call_soon_threadsafe(
                lambda: self._loop.create_task(self._transcribe(audio))  # type: ignore
            )

    async def _transcribe(self, audio_chunks: list[np.ndarray]):
        """Transcribe captured audio, check for wake word, then publish command."""
        async with self._process_lock:
            try:
                # Concatenate audio chunks into a single array
                audio = np.concatenate(audio_chunks, axis=0).flatten()
                duration = len(audio) / SAMPLE_RATE
                logger.info(f"Transcribing {duration:.1f}s of audio...")

                # If enrolling, collect this sample (bypass wake word check)
                if self._enrolling:
                    self._enrollment_samples.append(audio.copy())
                    remaining = self._enrollment_count - len(self._enrollment_samples)
                    if remaining > 0:
                        await self.event_bus.publish("command.response", {
                            "text": f"Sample recorded. {remaining} more to go. Please say another phrase.",
                            "command": "_enrollment",
                        })
                        return
                    else:
                        self._enrolling = False
                        if self._voice_auth:
                            result = self._voice_auth.enroll(self._enrollment_samples)
                            self._enrollment_samples = []
                            await self.event_bus.publish("command.response", {
                                "text": result,
                                "command": "_enrollment",
                            })
                        return

                # Run whisper in executor to avoid blocking the event loop
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, self._run_whisper, audio)

                text = result.get("text", "").strip()
                if not text:
                    logger.debug("Whisper returned empty transcription")
                    return

                logger.info(f"Transcribed: {text}")

                # ── Wake word gate ────────────────────────────
                command = _extract_command(text)
                if command is None:
                    # No wake word — ignore silently
                    logger.debug(f"No wake word, ignoring: {text}")
                    return

                logger.info(f"Wake word detected — command: {command}")

                # Voice authentication check (only after wake word matches)
                if self._voice_auth and self._voice_auth.is_enrolled():
                    is_match, confidence = self._voice_auth.verify(audio)
                    if not is_match:
                        logger.warning(f"Voice auth failed (confidence={confidence:.3f})")
                        await self.event_bus.publish("command.response", {
                            "text": "I don't recognise your voice. Please identify yourself.",
                            "command": "_voice_auth_failed",
                        })
                        await self.event_bus.publish("mic.transcribed", {
                            "text": "[unrecognised speaker]",
                            "duration": round(duration, 1),
                            "voice_auth": False,
                        })
                        return

                # Publish to UI so it can show what was heard
                await self.event_bus.publish("mic.transcribed", {
                    "text": command,
                    "duration": round(duration, 1),
                })

                # Feed into command pipeline
                await self.event_bus.publish("system.command", {
                    "command": command,
                    "source": "microphone",
                })

            except Exception as e:
                logger.error(f"Transcription error: {e}", exc_info=True)

    @staticmethod
    def _run_whisper(audio: np.ndarray) -> dict:
        """Run mlx-whisper transcription (blocking — called in executor)."""
        import mlx_whisper
        return mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=WHISPER_MODEL,
            language="en",
            fp16=True,
        )

    async def _on_tts_start(self, data: dict):
        """Mute mic when Nex starts speaking to prevent feedback."""
        self._muted = True
        text = data.get("text", "")
        # Estimate TTS duration: ~150 words/min for macOS say
        words = len(text.split())
        tts_duration = max(1.0, words / 2.5)  # seconds
        mute_duration = tts_duration + 0.5     # extra buffer

        logger.debug(f"Muting mic for {mute_duration:.1f}s during TTS")
        await asyncio.sleep(mute_duration)
        self._muted = False
        logger.debug("Mic unmuted")
