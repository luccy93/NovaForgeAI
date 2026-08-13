"""Image intelligence: analysis, architecture diagram parsing, visual comparison.

All vision tasks are provider-independent. `ImageIntelService` uses the
HeuristicVisionProvider when no cloud key is configured (honest degraded
fallback: never invents captions) and the VisionModelGateway when available.

Diagram parsing is a purely geometric heuristic implemented with Pillow +
numpy: connected box detection, label OCR (via OCRDetector), and arrow
detection by stroke scanning between boxes. It produces a JSON structure
of components + relationships that can be merged into the knowledge graph.
"""
import io, logging
from typing import Optional
from dataclasses import dataclass, field

from app.multimodal.vision_gateway import VisionModelGateway, VisionRequest
from app.multimodal.ocr import OCRDetector

logger = logging.getLogger(__name__)

try:
    import numpy as np
    from PIL import Image
    HAVE_PIL = True
except Exception:  # pragma: no cover
    HAVE_PIL = False
    np = None
    Image = None


@dataclass
class ImageAnalysis:
    asset_id: str
    width: int = 0
    height: int = 0
    format: str = ""
    mode: str = ""
    size_bytes: int = 0
    brightness: float = 0.0
    contrast: float = 0.0
    dominant_colors: list[dict] = field(default_factory=list)
    caption: Optional[str] = None
    caption_provider: str = ""
    has_text: bool = False
    text: str = ""
    is_diagram: bool = False
    diagram: Optional[dict] = None

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()}
        return d


@dataclass
class DiagramNode:
    id: str
    label: str
    box: tuple[int, int, int, int]
    kind: str = "component"
    confidence: float = 0.6

    def to_dict(self) -> dict:
        return {"id": self.id, "label": self.label, "box": list(self.box),
                "kind": self.kind, "confidence": round(self.confidence, 3)}


@dataclass
class DiagramEdge:
    source: str
    target: str
    kind: str = "arrow"
    label: str = ""
    confidence: float = 0.5

    def to_dict(self) -> dict:
        return {"source": self.source, "target": self.target, "kind": self.kind,
                "label": self.label, "confidence": round(self.confidence, 3)}


@dataclass
class DiagramResult:
    nodes: list[DiagramNode] = field(default_factory=list)
    edges: list[DiagramEdge] = field(default_factory=list)
    parser: str = "geometric-heuristic"

    def to_dict(self) -> dict:
        return {"nodes": [n.to_dict() for n in self.nodes],
                "edges": [e.to_dict() for e in self.edges],
                "parser": self.parser}

    def as_graph(self) -> dict:
        """Compact graph form suitable for knowledge-graph ingestion."""
        return {
            "nodes": [{"id": n.id, "label": n.label, "kind": n.kind} for n in self.nodes],
            "edges": [{"source": e.source, "target": e.target, "kind": e.kind,
                       "label": e.label} for e in self.edges],
        }


class ImageIntelService:
    """Image analysis + architecture diagram parsing with honest fallbacks."""

    def __init__(self, gateway: Optional[VisionModelGateway] = None,
                 ocr: Optional[OCRDetector] = None,
                 max_pixels: int = 8_000_000):
        self.gateway = gateway or VisionModelGateway()
        self.ocr = ocr or OCRDetector()
        self.max_pixels = max_pixels

    # ---------------------------------------------------------------- analysis
    def analyze(self, asset_id: str, data: bytes, filename: str = "") -> ImageAnalysis:
        """Full analysis of one image blob."""
        stats = self._stats(data)
        analysis = ImageAnalysis(
            asset_id=asset_id,
            size_bytes=len(data),
            width=stats.get("width", 0),
            height=stats.get("height", 0),
            format=stats.get("format", ""),
            mode=stats.get("mode", ""),
            brightness=stats.get("brightness", 0.0),
            contrast=stats.get("contrast", 0.0),
            dominant_colors=stats.get("colors", []),
        )
        if not analysis.width:
            return analysis
        # OCR for embedded text (diagram labels, screenshots, slides)
        ocr_boxes: list[dict] = []
        try:
            ocr_result = self.ocr.ocr(data, organization_id="", asset_id=asset_id)
            if ocr_result and ocr_result.text:
                analysis.has_text = True
                analysis.text = ocr_result.text
                ocr_boxes = ocr_result.boxes or []
        except Exception as e:
            logger.warning("OCR failed for %s: %s", asset_id, e)
        # caption via the vision gateway (may be heuristic = no caption)
        try:
            kwargs = {"prompt": "Describe this image in one short sentence.",
                      "image_data": data, "image_mime": "image/png"}
            result = self.gateway.analyze(VisionRequest(**kwargs), task="caption")
            if result and result.text and result.provider != "local_heuristic":
                analysis.caption = result.text
                analysis.caption_provider = result.provider
        except Exception as e:
            logger.warning("Caption failed for %s: %s", asset_id, e)
        # diagram detection + parsing
        if (analysis.has_text or stats.get("is_line_heavy", False)):
            try:
                diagram = self.parse_diagram(data, ocr_text=analysis.text,
                                             ocr_boxes=ocr_boxes)
                if diagram.nodes:
                    analysis.is_diagram = True
                    analysis.diagram = diagram.to_dict()
            except Exception as e:
                logger.warning("Diagram parse failed for %s: %s", asset_id, e)
        return analysis

    def _stats(self, data: bytes) -> dict:
        if not HAVE_PIL:
            return {}
        try:
            img = Image.open(io.BytesIO(data))
            img.load()
        except Exception:
            return {}
        w, h = img.size
        if w * h > self.max_pixels:
            img = img.convert("RGB")
            img.thumbnail((1024, 1024))
            w, h = img.size
        gray = img.convert("L")
        arr = np.asarray(gray, dtype=np.float32)
        brightness = float(arr.mean()) / 255.0
        contrast = float(arr.std()) / 255.0 if arr.size else 0.0
        # spatial edges proxy: fraction of pixels differing from local blur
        small = arr[::4, ::4]
        if small.size > 100:
            blurred = np.asarray(
                gray.resize((max(1, w // 8), max(1, h // 8))).resize((w, h)), dtype=np.float32)
            diff = np.abs(arr - blurred)
            line_heavy = float((diff > 40).mean()) > 0.05
        else:
            line_heavy = False
        colors = self._dominant_colors(img)
        return {"width": w, "height": h, "format": img.format or "",
                "mode": img.mode, "brightness": brightness, "contrast": contrast,
                "colors": colors, "is_line_heavy": line_heavy}

    def _dominant_colors(self, img, n: int = 4) -> list[dict]:
        try:
            small = img.convert("RGB").resize((64, 64))
            arr = np.asarray(small, dtype=np.uint8)
            flat = arr.reshape(-1, 3)
            # simple k-cluster via rounding to palette buckets
            keys = (flat // 32).astype(np.int64)
            order = np.lexsort(keys.T)
            keys = keys[order]
            flat = flat[order]
            uniq, counts = np.unique(keys, axis=0, return_counts=True)
            top = np.argsort(counts)[::-1][:n]
            return [{"rgb": [int(x) for x in flat[uniq[i]].tolist()],
                     "share": round(float(counts[i]) / len(flat), 3)} for i in top]
        except Exception:
            return []

    # -------------------------------------------------------------- diagrams
    def detect_boxes(self, data: bytes) -> list[tuple[int, int, int, int]]:
        """Detect rectangular boxes (component cards) via luminance edges."""
        if not HAVE_PIL:
            return []
        try:
            img = Image.open(io.BytesIO(data)).convert("L")
        except Exception:
            return []
        w, h = img.size
        if w * h > self.max_pixels:
            img.thumbnail((1024, 1024))
        arr = np.asarray(img)
        # binarize: dark strokes
        dark = (arr < 128).astype(np.uint8)
        # morphological dilation (3x3 max-pool) to bridge dashed borders
        from numpy.lib.stride_tricks import sliding_window_view
        pad = np.pad(dark, 1, mode="constant")
        win = sliding_window_view(pad, (3, 3)).reshape(h, w, 9)
        dil = win.max(axis=2)
        # vertical extent of boxes: runs of rows holding any stroke
        rows = self._runs((dil.sum(axis=1) > 0).astype(int), min_len=8)
        boxes = []
        for r0, r1 in rows:
            col_counts = dil[r0:r1, :].sum(axis=0)
            hgt = max(1, r1 - r0)
            # full-height border columns (arrows/labels are short strokes)
            border_cols = np.where(col_counts >= max(8, 0.7 * hgt))[0]
            if border_cols.size == 0:
                continue
            # cluster adjacent border columns into left/right borders
            clusters = []
            start = int(border_cols[0])
            prev = start
            for c in border_cols[1:]:
                if c - prev > 4:
                    clusters.append((start, prev))
                    start = int(c)
                prev = int(c)
            clusters.append((start, int(prev)))
            for ci in range(0, len(clusters) - 1):
                c0 = clusters[ci][1]
                c1 = clusters[ci + 1][0]
                if c1 - c0 < 20:
                    continue
                region = arr[r0:r1, c0:c1]
                if region.size == 0:
                    continue
                interior = region < 128
                row_frac = interior.mean(axis=1)
                title_rows = int((row_frac > 0.02).sum())
                max_run = self._max_run(row_frac > 0.3)
                w = c1 - c0
                # accept: wide empty/annotated boxes, or narrow dense label boxes
                if not ((w >= 60 and (max_run == 0 or title_rows >= 4)) or
                        (w >= 30 and max_run >= 4)):
                    continue
                boxes.append((c0, r0, c1, r1))
        # dedupe nested/overlapping boxes, keep outermost
        boxes.sort(key=lambda b: -(b[2] - b[0]) * (b[3] - b[1]))
        kept = []
        for b in boxes:
            if any(self._contains(o, b) for o in kept):
                continue
            kept.append(b)
        return kept[:24]

    @staticmethod
    def _runs(vals, min_len: int = 1) -> list[tuple[int, int]]:
        runs, start = [], None
        for i, v in enumerate(vals):
            if v and start is None:
                start = i
            elif not v and start is not None:
                if i - start >= min_len:
                    runs.append((start, i))
                start = None
        if start is not None and len(vals) - start >= min_len:
            runs.append((start, len(vals)))
        return runs

    @staticmethod
    def _max_run(vals) -> int:
        best = cur = 0
        for v in vals:
            cur = cur + 1 if v else 0
            best = max(best, cur)
        return best

    @staticmethod
    def _contains(outer, inner) -> bool:
        o0, o1, o2, o3 = outer
        i0, i1, i2, i3 = inner
        return o0 <= i0 and o1 <= i1 and o2 >= i2 and o3 >= i3

    def _label_for_box(self, box, ocr_text: str, ocr_boxes: list[dict]) -> str:
        """Pick the OCR line whose centroid sits inside the box."""
        x0, y0, x1, y1 = box
        best, best_d = "", 1e18
        for entry in ocr_boxes:
            cx = (entry["left"] + entry["right"]) / 2
            cy = (entry["top"] + entry["bottom"]) / 2
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                d = abs(cy - (y0 + y1) / 2)
                if d < best_d:
                    best_d, best = d, entry["text"]
        if best:
            return best
        return ""

    def parse_diagram(self, data: bytes, ocr_text: str = "",
                      ocr_boxes: Optional[list[dict]] = None) -> DiagramResult:
        """Geometric diagram parser: boxes -> components, strokes -> arrows."""
        result = DiagramResult(parser="geometric-heuristic")
        if not HAVE_PIL:
            return result
        boxes = self.detect_boxes(data)
        if not boxes:
            return result
        ocr_boxes = ocr_boxes or []
        if not ocr_boxes and ocr_text:
            result.nodes = [DiagramNode(id=f"n{i}", label=ln, box=list(b))
                            for i, (b, ln) in enumerate(zip(boxes, [""] * len(boxes)))]
        else:
            by_label = {}
            for i, b in enumerate(boxes):
                label = self._label_for_box(b, ocr_text, ocr_boxes)
                if label and label in by_label:
                    continue
                by_label[label or f"n{i}"] = DiagramNode(
                    id=f"n{i}", label=label or f"component {i + 1}", box=list(b))
            result.nodes = list(by_label.values())
        # arrows: scan horizontal strips between box centroid rows for strokes
        edges = self._detect_arrows(data, boxes)
        result.edges = edges
        return result

    def _detect_arrows(self, data: bytes, boxes) -> list[DiagramEdge]:
        if not HAVE_PIL or len(boxes) < 2:
            return []
        try:
            img = Image.open(io.BytesIO(data)).convert("L")
        except Exception:
            return []
        w, h = img.size
        if w * h > self.max_pixels:
            img.thumbnail((1024, 1024))
        arr = np.asarray(img)
        dark = arr < 128
        edges: list[DiagramEdge] = []
        cy = [(b[1] + b[3]) / 2 for b in boxes]
        for i in range(len(boxes)):
            for j in range(len(boxes)):
                if j <= i:
                    continue
                bx0, by0, bx1, by1 = boxes[i]
                cx0, cy0, cx1, cy1 = boxes[j]
                if abs(cy[i] - cy[j]) > max(30, (by1 - by0 + bx1 - bx0) / 4):
                    continue  # not roughly same row (simplified)
                x_lo, x_hi = (bx1, cx0) if cx0 > bx1 else (cx1, bx0)
                if x_hi - x_lo < 20:
                    continue
                # crop the ~3px box borders (with dilation) from the gap interior
                x_lo += 4
                x_hi -= 4
                if x_hi - x_lo < 12:
                    continue
                gap = dark[:, x_lo:x_hi]
                fill = float(gap.mean())
                col_cov = float(gap.any(axis=0).mean())
                if fill <= 0.002 or col_cov <= 0.4:
                    continue
                half = max(1, gap.shape[1] // 2)
                left_mean = float(gap[:, :half].mean())
                right_mean = float(gap[:, half:].mean())
                # arrowhead: densest stroke column sits at the pen end
                col_sum = gap.sum(axis=0)
                tail_max = int(col_sum[:8].max()) if gap.shape[1] > 16 else 0
                head_max = int(col_sum[-8:].max()) if gap.shape[1] > 16 else 0
                head_right = (col_sum[-4:].sum() > col_sum[:4].sum() + 2 and
                              head_max > max(4, tail_max + 1))
                head_left = (col_sum[:4].sum() > col_sum[-4:].sum() + 2 and
                             tail_max > max(4, head_max + 1))
                j_right = cx0 > bx1
                if head_right == head_left:
                    kind, direction = "connector", None
                elif (head_right and j_right) or (head_left and not j_right):
                    kind, direction = "arrow", (i, j)
                else:
                    kind, direction = "arrow", (j, i)
                edges.append(DiagramEdge(
                    source=f"n{direction[0] if direction else i}",
                    target=f"n{direction[1] if direction else j}",
                    kind=kind, confidence=round(0.5 + min(0.4, fill * 24), 3)))
        return edges[:64]

    # ------------------------------------------------------- visual compare
    def compare(self, baseline: bytes, candidate: bytes) -> dict:
        """Perceptual difference for visual regression testing."""
        if not HAVE_PIL:
            return {"supported": False, "reason": "Pillow unavailable"}
        try:
            from PIL import ImageChops, ImageStat
        except Exception:
            return {"supported": False, "reason": "Pillow unavailable"}
        try:
            a = Image.open(io.BytesIO(baseline)).convert("RGB")
            b = Image.open(io.BytesIO(candidate)).convert("RGB")
        except Exception as e:
            return {"supported": False, "reason": f"decode failed: {e}"}
        if a.size != b.size:
            b = b.resize(a.size)
        diff = ImageChops.difference(a, b)
        stat = ImageStat.Stat(diff)
        mean = sum(stat.mean) / 3.0
        bbox = diff.getbbox()
        diff_pixels = 0
        if bbox:
            region = diff.crop(bbox)
            arr = np.asarray(region.convert("L"))
            diff_pixels = int((arr > 16).sum())
        total = a.size[0] * a.size[1]
        ratio = diff_pixels / total if total else 0.0
        if ratio == 0.0 and mean < 0.5:
            verdict = "identical"
        elif ratio < 0.02:
            verdict = "similar"
        else:
            verdict = "different"
        return {"supported": True, "mean_delta": round(mean, 3),
                "diff_ratio": round(ratio, 5), "diff_pixels": diff_pixels,
                "verdict": verdict, "changed_bbox": list(bbox) if bbox else None}