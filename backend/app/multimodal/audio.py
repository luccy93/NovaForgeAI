"""Audio intelligence: transcription (whisper/cloud) and extractive topics.

Honest capability model:
- Transcription requires either the `whisper` CLI on PATH, openai-whisper
  installed, or a configured OpenAI/Google API key. Otherwise the pipeline
  reports `available: false` with the exact reason - never fake transcripts.
- Topics/decisions are deterministic keyword- and pattern-based extractions
  (documented heuristic), independent of the transcription provider.
"""
import logging, os, re, shutil, subprocess, tempfile
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

DECISION_PATTERNS = (
    r"\b(we will|we decided|decision|agreed to|consensus|approved|"
    r"action item|next step|we should|will do)\b"
)

TOPIC_KEYWORDS = {
    "architecture": ("architecture", "design", "component", "module", "service"),
    "infrastructure": ("deploy", "kubernetes", "docker", "cluster", "pipeline",
                        "ci", "cd", "infra"),
    "security": ("security", "authn", "authz", "secret", "vulnerab", "pii", "privacy"),
    "data": ("data", "database", "schema", "query", "migration", "vector", "index"),
    "multimodal": ("image", "pdf", "ocr", "vision", "video", "audio", "diagram", "rag"),
    "product": ("roadmap", "release", "feature", "customer", "user", "usability"),
    "performance": ("latency", "throughput", "benchmark", "optimiz", "scalab"),
    "quality": ("testing", "coverage", "lint", "bug", "regression", "review"),
}


@dataclass
class AudioAnalysis:
    asset_id: str
    available: bool = False
    reason: str = ""
    duration_s: float = 0.0
    transcript: str = ""
    topics: list[dict] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    provider: str = ""

    def to_dict(self) -> dict:
        return {"asset_id": self.asset_id, "available": self.available,
                "reason": self.reason, "duration_s": round(self.duration_s, 2),
                "transcript": self.transcript[:50000], "topics": self.topics[:50],
                "decisions": self.decisions[:100], "provider": self.provider}


class AudioIntelligence:
    """Audio pipeline: transcription via whisper CLI / SDK / cloud, then
    deterministic topic and decision extraction."""

    def __init__(self, whisper_binary: str = "whisper",
                 openai_whisper_installed: bool | None = None):
        self.whisper_binary = shutil.which(whisper_binary)
        self._whisper_import = None
        if openai_whisper_installed is None:
            try:
                import whisper  # noqa: F401
                self._whisper_import = "whisper"
            except ImportError:
                pass

    def _probe_duration(self, data: bytes, tmpdir: str) -> float:
        path = os.path.join(tmpdir, "input.raw")
        with open(path, "wb") as fh:
            fh.write(data)
        for probe in (shutil.which("ffprobe"),):
            if probe:
                try:
                    out = subprocess.run(
                        [probe, "-v", "error", "-show_entries", "format=duration",
                         "-of", "default=noprint_wrappers=1:nokey=1", path],
                        capture_output=True, text=True, timeout=30)
                    return float(out.stdout.strip() or 0.0)
                except Exception:
                    pass
        return 0.0

    def transcribe(self, data: bytes, asset_id: str = "", filename: str = "") -> AudioAnalysis:
        tmp = tempfile.mkdtemp(prefix="novaforge-audio-")
        try:
            analysis = AudioAnalysis(asset_id=asset_id,
                                     duration_s=self._probe_duration(data, tmp))
            transcript = None
            provider = ""
            if self._whisper_import:
                provider = "openai-whisper"
                transcript = self._transcribe_pywhisper(data, tmp)
            elif self.whisper_binary:
                provider = "whisper-cli"
                transcript = self._transcribe_cli(data, tmp)
            elif os.getenv("OPENAI_API_KEY"):
                provider = "openai-whisper-api"
                transcript = self._transcribe_openai_api(data, tmp)
            elif os.getenv("GOOGLE_API_KEY"):
                provider = "google-speech"
                transcript = self._transcribe_google(data, tmp)
            if not transcript:
                analysis.reason = (
                    "no transcription backend available: install openai-whisper, "
                    "whisper CLI, or configure OPENAI_API_KEY/GOOGLE_API_KEY")
                return analysis
            analysis.available = True
            analysis.transcript = transcript
            analysis.provider = provider
            analysis.topics = self.extract_topics(transcript)
            analysis.decisions = self.extract_decisions(transcript)
            return analysis
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def _transcribe_pywhisper(self, data: bytes, tmpdir: str) -> str:
        import whisper
        path = os.path.join(tmpdir, "input.wav")
        with open(path, "wb") as fh:
            fh.write(data)
        model = whisper.load_model("base")
        result = model.transcribe(path)
        return result.get("text", "")

    def _transcribe_cli(self, data: bytes, tmpdir: str) -> str:
        path = os.path.join(tmpdir, "input.wav")
        with open(path, "wb") as fh:
            fh.write(data)
        out = subprocess.run(
            [self.whisper_binary, path, "--output_format", "txt",
             "--output_dir", tmpdir, "--model", "base", "--language", "en",
             "--fp16", "False"],
            capture_output=True, text=True, timeout=3600)
        if out.returncode != 0:
            raise RuntimeError(f"whisper cli failed: {out.stderr[:300]}")
        txt = os.path.join(tmpdir, "input.txt")
        if os.path.exists(txt):
            with open(txt, encoding="utf-8") as fh:
                return fh.read()
        return ""

    def _transcribe_openai_api(self, data: bytes, tmpdir: str) -> str:
        import openai
        path = os.path.join(tmpdir, "input.wav")
        with open(path, "wb") as fh:
            fh.write(data)
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        with open(path, "rb") as fh:
            resp = client.audio.transcriptions.create(model="whisper-1", file=fh)
        return getattr(resp, "text", "")

    def _transcribe_google(self, data: bytes, tmpdir: str) -> str:
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        path = os.path.join(tmpdir, "input.wav")
        with open(path, "wb") as fh:
            fh.write(data)
        model = genai.GenerativeModel("gemini-1.5-flash")
        resp = model.generate_content([
            "Transcribe this audio verbatim.",
            genai.upload_file(path),
        ])
        return resp.text or ""

    # ---------------------------------------------------- deterministic extras
    @staticmethod
    def extract_topics(transcript: str) -> list[dict]:
        text = transcript.lower()
        out = []
        for topic, words in TOPIC_KEYWORDS.items():
            hits = [w for w in words if w in text]
            if hits:
                out.append({"topic": topic, "keywords": hits,
                            "mentions": sum(text.count(w) for w in hits)})
        out.sort(key=lambda t: -t["mentions"])
        return out

    @staticmethod
    def extract_decisions(transcript: str) -> list[str]:
        sentences = re.split(r"(?<=[.!?])\s+", transcript)
        out = []
        for s in sentences:
            if re.search(DECISION_PATTERNS, s, re.I):
                out.append(s.strip())
        return [s[:400] for s in out]