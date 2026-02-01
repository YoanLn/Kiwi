
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

from PyPDF2 import PdfReader

from app.core.config import settings
from app.models.document import DocumentType, VerificationStatus
from app.services.ocr_service import get_ocr_service

logger = logging.getLogger(__name__)

# Optional image OCR deps
try:
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover
    Image = None  # type: ignore

try:
    import pytesseract  # type: ignore

    _TESSERACT_OK = True
except Exception:  # pragma: no cover
    pytesseract = None  # type: ignore
    _TESSERACT_OK = False

# Optional Vertex AI structured extraction
try:
    import vertexai  # type: ignore
    from vertexai.generative_models import GenerativeModel  # type: ignore

    _VERTEX_OK = True
except Exception:  # pragma: no cover
    vertexai = None  # type: ignore
    GenerativeModel = None  # type: ignore
    _VERTEX_OK = False


# -----------------------------
# Data structures
# -----------------------------

@dataclass
class FileMeta:
    filename: str
    mime_type: str
    is_pdf: bool
    is_image: bool


@dataclass
class ExtractedText:
    text: str
    method: str  # pdf_native | tesseract | gemini_ocr | none
    char_count: int

    @property
    def is_empty(self) -> bool:
        normalized = (self.text or "").strip().lower()
        return not normalized or "no text content extracted" in normalized


@dataclass
class Issue:
    field: str
    issue_type: str  # missing | invalid | mismatch | unreadable | suspicious | unrelated
    severity: str  # low | medium | high | critical
    description: str
    suggestion: Optional[str] = None


# -----------------------------
# Verification profiles
# -----------------------------

# Normalized types we use internally (string labels)
# We map your DocumentType enum onto these.
NORM_UNRELATED = "unrelated"
NORM_ID = "id_document"
NORM_BANK = "bank_details"
NORM_POLICY = "insurance_policy"
NORM_CLAIM = "claim_form"
NORM_INCIDENT = "incident_report"
NORM_OWNERSHIP = "proof_of_ownership"
NORM_REPAIR = "repair_estimate"
NORM_MEDICAL = "medical_report"
NORM_DAMAGE = "evidence_of_damage"


@dataclass(frozen=True)
class Profile:
    required_fields: Tuple[str, ...]
    allow_empty_text: bool = False
    must_be_image: bool = False  # for photos evidence
    good_enough_if_image: bool = False  # if image + empty text -> accept with lower confidence
    should_index: bool = True  # whether to push into Vertex Search index


PROFILES: Dict[str, Profile] = {
    NORM_ID: Profile(required_fields=("holder_name", "id_number", "date_of_birth"), allow_empty_text=False),
    NORM_BANK: Profile(required_fields=("holder_name", "bank_account"), allow_empty_text=False),
    NORM_POLICY: Profile(required_fields=("holder_name", "policy_number"), allow_empty_text=False),
    NORM_CLAIM: Profile(required_fields=("holder_name", "incident_date", "claim_number"), allow_empty_text=False),
    NORM_INCIDENT: Profile(required_fields=("incident_date", "incident_location"), allow_empty_text=False),
    NORM_OWNERSHIP: Profile(required_fields=("holder_name", "purchase_date"), allow_empty_text=False),
    NORM_REPAIR: Profile(required_fields=("provider_name", "amount_total"), allow_empty_text=False),
    NORM_MEDICAL: Profile(required_fields=("holder_name", "medical_date"), allow_empty_text=False),
    # Evidence photos: allow empty OCR and don't index (usually useless for text search)
    NORM_DAMAGE: Profile(
        required_fields=(),
        allow_empty_text=True,
        must_be_image=True,
        good_enough_if_image=True,
        should_index=False,
    ),
    NORM_UNRELATED: Profile(required_fields=(), allow_empty_text=True, should_index=False),
}


# -----------------------------
# Rule-based type detection
# -----------------------------

TYPE_KEYWORDS: Dict[str, List[str]] = {
    NORM_POLICY: [
        "policy number",
        "insurance policy",
        "police d'assurance",
        "numero de police",
        "num\u00e9ro de police",
        "coverage",
        "couverture",
        "premium",
        "prime",
    ],
    NORM_CLAIM: [
        "claim number",
        "claim form",
        "declaration de sinistre",
        "d\u00e9claration de sinistre",
        "formulaire de reclamation",
        "formulaire de r\u00e9clamation",
        "numero de sinistre",
        "num\u00e9ro de sinistre",
        "declaration of loss",
    ],
    NORM_INCIDENT: [
        "police report",
        "rapport de police",
        "accident report",
        "incident report",
        "constat",
        "proces verbal",
        "proc\u00e8s verbal",
        "proc\u00e8s-verbal",
    ],
    NORM_OWNERSHIP: [
        "invoice",
        "facture",
        "receipt",
        "recu",
        "re\u00e7u",
        "bill of sale",
        "acte de vente",
        "proof of ownership",
        "preuve de propriete",
        "preuve de propri\u00e9t\u00e9",
    ],
    NORM_REPAIR: [
        "repair estimate",
        "devis",
        "quote",
        "repair invoice",
        "facture de reparation",
        "facture de r\u00e9paration",
        "atelier",
        "garage",
    ],
    NORM_MEDICAL: [
        "medical report",
        "rapport medical",
        "rapport m\u00e9dical",
        "diagnosis",
        "diagnostic",
        "hospital",
        "hopital",
        "h\u00f4pital",
        "doctor",
        "medecin",
        "m\u00e9decin",
        "patient",
        "facture medicale",
        "facture m\u00e9dicale",
    ],
    NORM_ID: [
        "passport",
        "passeport",
        "identity card",
        "carte d'identite",
        "carte d'identit\u00e9",
        "carte nationale",
        "driver license",
        "permis de conduire",
        "national id",
        "republique francaise",
        "r\u00e9publique fran\u00e7aise",
    ],
    NORM_BANK: [
        "iban",
        "bic",
        "rib",
        "bank details",
        "coordonnees bancaires",
        "coordonn\u00e9es bancaires",
        "account number",
        "numero de compte",
        "num\u00e9ro de compte",
        "bank account",
    ],
    NORM_DAMAGE: [
        "damage",
        "dommage",
        "photo",
        "evidence",
        "degat",
        "d\u00e9g\u00e2t",
        "sinistre",
        "bris",
    ],
}


def detect_type_rule_based(text: str) -> Tuple[str, float, Dict[str, int]]:
    """
    Returns: (detected_norm_type, confidence_0_1, keyword_hits_by_type)
    """
    t = (text or "").lower()
    hits: Dict[str, int] = {}
    for dtype, kws in TYPE_KEYWORDS.items():
        count = 0
        for kw in kws:
            if kw in t:
                count += 1
        if count:
            hits[dtype] = count

    if not hits:
        return (NORM_UNRELATED, 0.35, {})

    best_type = max(hits, key=hits.get)
    best = hits[best_type]
    second = sorted(hits.values(), reverse=True)[1] if len(hits) > 1 else 0

    # A simple confidence heuristic
    gap = best - second
    conf = 0.55 + 0.10 * min(best, 4) + 0.10 * min(gap, 3)
    conf = max(0.0, min(0.95, conf))
    return (best_type, conf, hits)

# -----------------------------
# Regex field extraction
# -----------------------------

_IBAN_RE = re.compile(r"\b([A-Z]{2}\d{2}[A-Z0-9]{11,30})\b")
_BIC_RE = re.compile(r"\b([A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?)\b")
_DATE_RE = re.compile(
    r"\b(\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4}|\d{4}[\/\-.]\d{1,2}[\/\-.]\d{1,2})\b"
)
_AMOUNT_RE = re.compile(
    r"\b(\d{1,3}(?:[ ,]\d{3})*(?:[.,]\d{2})?)\s?(\u20ac|eur|usd|\$)?\b", re.IGNORECASE
)

# Simple "label: value" patterns (FR/EN)
_LABEL_PATTERNS = {
    "holder_name": [
        r"(?:name|nom)\s*[:\-]\s*(.+)",
        r"(?:account holder|titulaire)\s*[:\-]\s*(.+)",
    ],
    "policy_number": [
        r"(?:policy number|num(?:e|\u00e9)ro de police)\s*[:\-]\s*([A-Z0-9\-\/]+)",
    ],
    "claim_number": [
        r"(?:claim number|num(?:e|\u00e9)ro de sinistre)\s*[:\-]\s*([A-Z0-9\-\/]+)",
    ],
    "incident_location": [
        r"(?:location|lieu)\s*[:\-]\s*(.+)",
    ],
}


def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def parse_date_loose(s: str) -> Optional[date]:
    """
    Tries a few common formats; returns a date or None.
    """
    s = (s or "").strip()
    if not s:
        return None

    fmts = [
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%d/%m/%y",
        "%d-%m-%y",
        "%d.%m.%y",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    return None


def iban_is_valid(iban: str) -> bool:
    iban = re.sub(r"\s+", "", (iban or "").upper())
    if not (15 <= len(iban) <= 34):
        return False
    if not re.match(r"^[A-Z0-9]+$", iban):
        return False

    rearranged = iban[4:] + iban[:4]
    digits = []
    for ch in rearranged:
        if ch.isdigit():
            digits.append(ch)
        else:
            digits.append(str(ord(ch) - 55))  # A=10 ... Z=35
    num = "".join(digits)

    # mod-97 iteratively (avoid huge ints)
    rem = 0
    for c in num:
        rem = (rem * 10 + int(c)) % 97
    return rem == 1


def extract_fields_regex(text: str) -> Dict[str, Any]:
    t = text or ""
    out: Dict[str, Any] = {}

    # IBAN
    iban_match = None
    for m in _IBAN_RE.finditer(re.sub(r"\s+", "", t.upper())):
        iban_match = m.group(1)
        break
    if iban_match:
        out["bank_account"] = iban_match

    # BIC
    bic = None
    for m in _BIC_RE.finditer(t.upper()):
        bic = m.group(1)
        break
    if bic:
        out["bank_bic"] = bic

    # Dates list
    dates = []
    for m in _DATE_RE.finditer(t):
        d = parse_date_loose(m.group(1))
        if d:
            dates.append(d.isoformat())
    if dates:
        out["dates_found"] = sorted(set(dates))

    # Amounts list
    amounts = []
    for m in _AMOUNT_RE.finditer(t):
        raw = m.group(1)
        currency = (m.group(2) or "").lower()
        # Filter out tiny false positives
        if raw and len(raw) >= 3:
            amounts.append({"raw": raw, "currency": currency or None})
    if amounts:
        out["amounts_found"] = amounts[:10]

    # Label patterns
    for field, patterns in _LABEL_PATTERNS.items():
        for pat in patterns:
            m = re.search(pat, t, flags=re.IGNORECASE)
            if m:
                val = normalize_spaces(m.group(1))
                # Avoid swallowing whole paragraphs
                if len(val) > 2 and len(val) < 120:
                    out[field] = val
                    break
        if field in out:
            continue

    return out

# -----------------------------
# Gemini structured extraction (optional)
# -----------------------------

def _json_snip(text: str) -> Optional[dict]:
    """
    Extract a JSON object from a model response safely.
    """
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    blob = text[start : end + 1]
    try:
        import json

        return json.loads(blob)
    except Exception:
        return None


class GeminiFieldExtractor:
    """
    Uses Vertex AI Gemini TEXT model to extract structured fields from OCR text.
    This does NOT do OCR. It only reads the extracted text.
    """

    def __init__(self) -> None:
        if not _VERTEX_OK:
            raise RuntimeError("vertexai not available")

        # Vertex init can throw if creds/project not configured
        vertexai.init(project=settings.GOOGLE_CLOUD_PROJECT, location=settings.VERTEX_AI_LOCATION)
        self.model = GenerativeModel(settings.VERTEX_AI_MODEL_TEXT)

    async def extract(self, ocr_text: str, selected_norm_type: str) -> Dict[str, Any]:
        """
        Returns dict:
        {
          "document_type_detected": "...",
          "type_confidence": 0..1,
          "extracted_fields": {...},
          "field_confidences": {...}
        }
        """
        system = (
            "You are an information extraction engine.\n"
            "Extract ONLY what is explicitly present in the text.\n"
            "If a field is not present, output null.\n"
            "Do NOT guess.\n"
            "Return valid JSON ONLY.\n"
        )

        # Keep the schema stable; keep it small.
        user = f"""
Allowed types:
- {NORM_POLICY}
- {NORM_CLAIM}
- {NORM_INCIDENT}
- {NORM_OWNERSHIP}
- {NORM_REPAIR}
- {NORM_MEDICAL}
- {NORM_ID}
- {NORM_BANK}
- {NORM_DAMAGE}
- {NORM_UNRELATED}

Selected type hint: {selected_norm_type}

Text:
---
{ocr_text[:9000]}
---

Return JSON with exactly:
{{
  "document_type_detected": "<one allowed type>",
  "type_confidence": <0.0-1.0>,
  "extracted_fields": {{
    "holder_name": <string|null>,
    "date_of_birth": <YYYY-MM-DD|null>,
    "expiry_date": <YYYY-MM-DD|null>,
    "id_number": <string|null>,
    "address": <string|null>,
    "bank_account": <string|null>,
    "bank_name": <string|null>,
    "bank_bic": <string|null>,
    "policy_number": <string|null>,
    "claim_number": <string|null>,
    "incident_date": <YYYY-MM-DD|null>,
    "incident_location": <string|null>,
    "purchase_date": <YYYY-MM-DD|null>,
    "provider_name": <string|null>,
    "medical_date": <YYYY-MM-DD|null>,
    "amount_total": <string|null>
  }},
  "field_confidences": {{
    "holder_name": <0.0-1.0>,
    "date_of_birth": <0.0-1.0>,
    "expiry_date": <0.0-1.0>,
    "id_number": <0.0-1.0>,
    "bank_account": <0.0-1.0>,
    "policy_number": <0.0-1.0>,
    "claim_number": <0.0-1.0>,
    "incident_date": <0.0-1.0>,
    "purchase_date": <0.0-1.0>,
    "provider_name": <0.0-1.0>,
    "medical_date": <0.0-1.0>,
    "amount_total": <0.0-1.0>
  }}
}}
"""

        resp = await asyncio.to_thread(
            self.model.generate_content,
            [system, user],
            generation_config={"temperature": 0.0, "max_output_tokens": 1200, "top_p": 0.8},
        )

        text = getattr(resp, "text", None) or str(resp)
        parsed = _json_snip(text)
        return parsed or {}


# -----------------------------
# Core service
# -----------------------------


class DocumentVerificationService:
    """
    Verification pipeline from scratch:

    1) Inspect file
    2) Extract text (PDF native -> Tesseract -> Gemini OCR fallback)
    3) Detect type (rule-based; optional Gemini can help but not required)
    4) Extract fields (regex + optional Gemini structured extraction)
    5) Validate deterministically
    6) Score confidence (never 100 by default)
    """

    def __init__(self) -> None:
        self.ocr_service = get_ocr_service()
        self._gemini_extractor: Optional[GeminiFieldExtractor] = None

        # Lazy-init the Gemini extractor (so local dev still works without creds)
        if _VERTEX_OK and settings.GOOGLE_CLOUD_PROJECT and settings.VERTEX_AI_LOCATION:
            try:
                self._gemini_extractor = GeminiFieldExtractor()
            except Exception as exc:
                logger.warning("GeminiFieldExtractor disabled: %s", exc)
                self._gemini_extractor = None

    async def verify_document(
        self,
        file_content: bytes,
        document_type: DocumentType,
        mime_type: str,
        document_id: Optional[str | int] = None,
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        doc_id = str(document_id or "unknown")
        filename = filename or "upload"

        meta = self._inspect_file(file_content=file_content, mime_type=mime_type, filename=filename)
        selected_norm = self._normalize_document_type(document_type)
        profile = PROFILES.get(selected_norm, PROFILES[NORM_UNRELATED])

        # 1) Extract text
        extracted = await self._extract_text(file_content, meta)

        # 2) Detect type from text (rule-based)
        detected_norm, detected_conf, keyword_hits = detect_type_rule_based(extracted.text)

        # 3) Extract fields from regex
        fields = extract_fields_regex(extracted.text)

        # 4) Optional Gemini structured extraction (merge if present)
        gemini_payload: Dict[str, Any] = {}
        if self._gemini_extractor and not extracted.is_empty:
            try:
                gemini_payload = await self._gemini_extractor.extract(extracted.text, selected_norm)
                g_fields = (gemini_payload.get("extracted_fields") or {}) if isinstance(gemini_payload, dict) else {}
                if isinstance(g_fields, dict):
                    # Merge: Gemini fills holes; regex stays if Gemini is null/empty.
                    for k, v in g_fields.items():
                        if v is None:
                            continue
                        if k not in fields or fields.get(k) in (None, "", []):
                            fields[k] = v
            except Exception as exc:
                logger.warning("Gemini structured extraction failed for %s: %s", doc_id, exc)

        # If Gemini provides detected type, optionally use it as a soft signal
        if isinstance(gemini_payload, dict):
            g_detected = gemini_payload.get("document_type_detected")
            g_conf = gemini_payload.get("type_confidence")
            if isinstance(g_detected, str) and g_detected in PROFILES:
                # Combine with rule-based if rule-based is weak
                try:
                    g_conf_f = float(g_conf) if g_conf is not None else 0.0
                except Exception:
                    g_conf_f = 0.0

                if detected_conf < 0.65 and g_conf_f >= detected_conf:
                    detected_norm, detected_conf = g_detected, min(0.95, g_conf_f)

        # 5) Validate
        issues: List[Issue] = []
        issues.extend(self._validate_format(meta, selected_norm, extracted))
        issues.extend(self._validate_type(selected_norm, detected_norm, extracted))
        issues.extend(self._validate_required_fields(profile, fields, extracted))
        issues.extend(self._validate_semantics(selected_norm, fields))

        # 6) Decide final status + compliance
        status, is_compliant = self._decide(profile, selected_norm, detected_norm, extracted, issues)

        # 7) Confidence score (0..98; never 100 by default)
        confidence = self._score_confidence(
            profile=profile,
            selected_norm=selected_norm,
            detected_norm=detected_norm,
            detected_conf=detected_conf,
            extracted=extracted,
            fields=fields,
            issues=issues,
        )

        # 8) Build analysis + summary strings
        compliance_issues = self._issue_summary(issues, max_items=8)
        analysis = self._analysis_report(
            doc_id=doc_id,
            selected_norm=selected_norm,
            detected_norm=detected_norm,
            detected_conf=detected_conf,
            extracted=extracted,
            fields=fields,
            issues=issues,
            keyword_hits=keyword_hits,
        )

        return {
            "status": status,
            "analysis": analysis,
            "confidence_score": confidence,
            "is_compliant": is_compliant,
            "compliance_issues": compliance_issues,
            "should_index": profile.should_index and is_compliant,
            "extracted_fields": fields,
        }

    # -----------------------------
    # Helpers
    # -----------------------------

    def _inspect_file(self, file_content: bytes, mime_type: str, filename: str) -> FileMeta:
        mt = (mime_type or "").lower()
        name = filename or "upload"

        is_pdf = ("pdf" in mt) or (file_content[:4] == b"%PDF")
        is_image = ("image/" in mt) or self._looks_like_image(file_content)

        return FileMeta(
            filename=name,
            mime_type=mt or "application/octet-stream",
            is_pdf=is_pdf,
            is_image=is_image,
        )

    def _looks_like_image(self, content: bytes) -> bool:
        if not content:
            return False
        sigs = [
            b"\xff\xd8\xff",  # jpeg
            b"\x89PNG",  # png
            b"GIF8",  # gif
            b"BM",  # bmp
        ]
        for s in sigs:
            if content.startswith(s):
                return True
        if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
            return True
        return False

    def _normalize_document_type(self, dt: DocumentType) -> str:
        mapping = {
            DocumentType.INSURANCE_POLICY: NORM_POLICY,
            DocumentType.CLAIM_FORM: NORM_CLAIM,
            DocumentType.INCIDENT_REPORT: NORM_INCIDENT,
            DocumentType.PROOF_OF_OWNERSHIP: NORM_OWNERSHIP,
            DocumentType.REPAIR_ESTIMATE: NORM_REPAIR,
            DocumentType.MEDICAL_REPORT: NORM_MEDICAL,
            DocumentType.ID_DOCUMENT: NORM_ID,
            DocumentType.BANK_DETAILS: NORM_BANK,
            DocumentType.EVIDENCE_OF_DAMAGE: NORM_DAMAGE,
            # legacy aliases:
            DocumentType.IDENTITY: NORM_ID,
            DocumentType.INVOICE: NORM_OWNERSHIP,
            DocumentType.POLICE_REPORT: NORM_INCIDENT,
            DocumentType.PHOTOS: NORM_DAMAGE,
            DocumentType.UNRELATED: NORM_UNRELATED,
            DocumentType.OTHER: NORM_UNRELATED,
        }
        return mapping.get(dt, NORM_UNRELATED)

    async def _extract_text(self, file_content: bytes, meta: FileMeta) -> ExtractedText:
        if not file_content:
            return ExtractedText(text="[No text content extracted from document]", method="none", char_count=0)

        # PDF native extraction first
        if meta.is_pdf:
            native = self._extract_pdf_native(file_content)
            if native and len(native.strip()) >= 80:
                return ExtractedText(text=native, method="pdf_native", char_count=len(native))
            # fallback: Gemini OCR on PDF bytes
            text = await self._extract_with_gemini_ocr(file_content, meta)
            return ExtractedText(text=text, method="gemini_ocr", char_count=len(text or ""))

        # Image: try Tesseract if installed
        if meta.is_image and _TESSERACT_OK and Image is not None:
            try:
                img = Image.open(BytesIO(file_content))
                txt = (pytesseract.image_to_string(img) or "").strip()
                if txt:
                    return ExtractedText(text=txt, method="tesseract", char_count=len(txt))
            except Exception as exc:
                logger.debug("Tesseract OCR failed: %s", exc)

        # fallback: Gemini OCR for images/unknown
        text = await self._extract_with_gemini_ocr(file_content, meta)
        return ExtractedText(text=text, method="gemini_ocr", char_count=len(text or ""))

    def _extract_pdf_native(self, file_content: bytes) -> str:
        try:
            reader = PdfReader(BytesIO(file_content))
            parts = []
            for p in reader.pages:
                parts.append(p.extract_text() or "")
            return "\n\n".join([x for x in parts if x.strip()]).strip()
        except Exception as exc:
            logger.debug("PDF native text extraction failed: %s", exc)
            return ""

    async def _extract_with_gemini_ocr(self, file_content: bytes, meta: FileMeta) -> str:
        try:
            # Use your existing OCRService (Gemini Vision via Vertex AI)
            # Needs filename extension to route MIME properly.
            filename = meta.filename
            if meta.is_pdf and not filename.lower().endswith(".pdf"):
                filename = filename + ".pdf"
            if meta.is_image and not re.search(r"\.(png|jpg|jpeg|webp|bmp|tiff)$", filename.lower()):
                filename = filename + ".png"

            result = await self.ocr_service.process_document_bytes(
                file_content=file_content,
                filename=filename,
                document_id="verification",
                mime_type=meta.mime_type,
                include_tables=False,
                include_images=False,
            )
            txt = (result.raw_text or "").strip()
            return txt if txt else "[No text content extracted from document]"
        except Exception as exc:
            logger.warning("Gemini OCR failed: %s", exc)
            return "[No text content extracted from document]"

    # -----------------------------
    # Validation
    # -----------------------------

    def _validate_format(self, meta: FileMeta, selected_norm: str, extracted: ExtractedText) -> List[Issue]:
        issues: List[Issue] = []
        profile = PROFILES.get(selected_norm, PROFILES[NORM_UNRELATED])

        if profile.must_be_image and not meta.is_image:
            issues.append(
                Issue(
                    field="file",
                    issue_type="invalid",
                    severity="high",
                    description="Expected an image file for photo evidence, but received a non-image document.",
                    suggestion="Upload a JPG/PNG/WebP photo.",
                )
            )

        # OCR empty where not allowed
        if extracted.is_empty and not profile.allow_empty_text:
            issues.append(
                Issue(
                    field="ocr_text",
                    issue_type="unreadable",
                    severity="high",
                    description="OCR extracted no usable text from this document.",
                    suggestion="Upload a clearer scan/photo or a digital PDF.",
                )
            )

        return issues

    def _validate_type(self, selected_norm: str, detected_norm: str, extracted: ExtractedText) -> List[Issue]:
        issues: List[Issue] = []
        # Hard reject only when we have non-empty OCR and it's clearly unrelated
        if detected_norm == NORM_UNRELATED and not extracted.is_empty and selected_norm != NORM_UNRELATED:
            issues.append(
                Issue(
                    field="document_type",
                    issue_type="unrelated",
                    severity="critical",
                    description="Document content appears unrelated to insurance documents.",
                    suggestion="Upload the correct document type.",
                )
            )
            return issues

        # Mismatch: flag for review (not hard reject)
        if selected_norm != NORM_UNRELATED and detected_norm not in (selected_norm, NORM_UNRELATED):
            issues.append(
                Issue(
                    field="document_type",
                    issue_type="mismatch",
                    severity="medium",
                    description=f"Detected type looks like '{detected_norm}' but user selected '{selected_norm}'.",
                    suggestion="Confirm the selected document type or upload the right document.",
                )
            )
        return issues

    def _validate_required_fields(self, profile: Profile, fields: Dict[str, Any], extracted: ExtractedText) -> List[Issue]:
        issues: List[Issue] = []
        if not profile.required_fields:
            return issues

        for f in profile.required_fields:
            val = fields.get(f)
            missing = val is None or (isinstance(val, str) and not val.strip())
            if missing:
                issues.append(
                    Issue(
                        field=f,
                        issue_type="missing",
                        severity="high",
                        description=f"Required field '{f}' not found in the document text.",
                        suggestion="Upload a clearer document where this field is visible.",
                    )
                )
        return issues

    def _validate_semantics(self, selected_norm: str, fields: Dict[str, Any]) -> List[Issue]:
        issues: List[Issue] = []

        # Bank validation
        if selected_norm == NORM_BANK:
            iban = fields.get("bank_account")
            if isinstance(iban, str) and iban.strip():
                if not iban_is_valid(iban):
                    issues.append(
                        Issue(
                            field="bank_account",
                            issue_type="invalid",
                            severity="high",
                            description="IBAN format/check digits look invalid.",
                            suggestion="Upload a bank document that clearly shows the IBAN.",
                        )
                    )

        # Date sanity checks
        today = datetime.utcnow().date()
        dob = parse_date_loose(fields.get("date_of_birth") or "")
        if dob:
            if dob > today:
                issues.append(
                    Issue(
                        field="date_of_birth",
                        issue_type="invalid",
                        severity="high",
                        description="Date of birth is in the future.",
                    )
                )
            # 120 years sanity
            if (today.year - dob.year) > 120:
                issues.append(
                    Issue(
                        field="date_of_birth",
                        issue_type="suspicious",
                        severity="medium",
                        description="Date of birth looks unusually old; may be OCR error.",
                    )
                )

        exp = parse_date_loose(fields.get("expiry_date") or "")
        if exp and exp < today and selected_norm == NORM_ID:
            issues.append(
                Issue(
                    field="expiry_date",
                    issue_type="invalid",
                    severity="medium",
                    description="ID document appears expired.",
                    suggestion="Upload a valid, unexpired ID if required.",
                )
            )

        return issues

    # -----------------------------
    # Decision + scoring
    # -----------------------------

    def _decide(
        self,
        profile: Profile,
        selected_norm: str,
        detected_norm: str,
        extracted: ExtractedText,
        issues: List[Issue],
    ) -> Tuple[VerificationStatus, bool]:
        """
        Map issues to a verification status + is_compliant.
        """
        # Critical -> rejected
        if any(i.severity == "critical" for i in issues):
            return (VerificationStatus.REJECTED, False)

        # Evidence photos: if image and empty OCR, accept but low confidence
        if selected_norm == NORM_DAMAGE and profile.good_enough_if_image:
            # If file format is wrong => high issue already -> needs review/reject.
            high = any(i.severity == "high" for i in issues)
            if not high:
                return (VerificationStatus.VERIFIED, True)

        # High issues -> needs review
        if any(i.severity == "high" for i in issues):
            return (VerificationStatus.PARTIALLY_COMPLIANT, False)

        # Medium issues -> partially compliant
        if any(i.severity == "medium" for i in issues):
            return (VerificationStatus.PARTIALLY_COMPLIANT, True)

        # Otherwise verified
        return (VerificationStatus.VERIFIED, True)

    def _score_confidence(
        self,
        profile: Profile,
        selected_norm: str,
        detected_norm: str,
        detected_conf: float,
        extracted: ExtractedText,
        fields: Dict[str, Any],
        issues: List[Issue],
    ) -> int:
        """
        Confidence in [0..98]. Never returns 100 by default.
        """
        # Base from type confidence + OCR quality + completeness
        ocr_quality = min(1.0, extracted.char_count / 1200.0)  # saturate around 1200 chars

        required = list(profile.required_fields)
        if required:
            found = 0
            for f in required:
                v = fields.get(f)
                if v is not None and (not isinstance(v, str) or v.strip()):
                    found += 1
            completeness = found / max(1, len(required))
        else:
            completeness = 1.0

        score = 25 + 35 * detected_conf + 25 * completeness + 15 * ocr_quality

        # Penalties
        sev_pen = {"critical": 35, "high": 18, "medium": 8, "low": 3}
        for i in issues:
            score -= sev_pen.get(i.severity, 6)

        # Extra penalties for mismatch
        if selected_norm != NORM_UNRELATED and detected_norm not in (selected_norm, NORM_UNRELATED):
            score -= 10

        if extracted.is_empty and not profile.allow_empty_text:
            score -= 15

        # Clamp and cap (no 100)
        score = max(0.0, min(98.0, score))
        return int(round(score))

    # -----------------------------
    # Reporting
    # -----------------------------

    def _issue_summary(self, issues: List[Issue], max_items: int = 6) -> Optional[str]:
        if not issues:
            return None
        parts = []
        for i in issues[:max_items]:
            parts.append(f"{i.severity.upper()} {i.field}: {i.description}")
        return "; ".join(parts)

    def _analysis_report(
        self,
        doc_id: str,
        selected_norm: str,
        detected_norm: str,
        detected_conf: float,
        extracted: ExtractedText,
        fields: Dict[str, Any],
        issues: List[Issue],
        keyword_hits: Dict[str, int],
    ) -> str:
        lines = []
        lines.append(f"Document {doc_id} verification report")
        lines.append(f"- Selected type: {selected_norm}")
        lines.append(f"- Detected type: {detected_norm} (conf={detected_conf:.2f})")
        lines.append(f"- OCR method: {extracted.method}, chars={extracted.char_count}, empty={extracted.is_empty}")

        # show a small preview of extracted fields
        interesting = [
            "holder_name",
            "id_number",
            "date_of_birth",
            "bank_account",
            "policy_number",
            "claim_number",
            "incident_date",
        ]
        previews = []
        for k in interesting:
            v = fields.get(k)
            if v:
                previews.append(f"{k}={v}")
        if previews:
            lines.append("- Extracted: " + ", ".join(previews[:6]))

        if keyword_hits:
            top = sorted(keyword_hits.items(), key=lambda x: x[1], reverse=True)[:4]
            lines.append("- Keyword hits: " + ", ".join([f"{k}:{v}" for k, v in top]))

        if issues:
            lines.append("- Issues:")
            for i in issues[:10]:
                sug = f" | suggestion: {i.suggestion}" if i.suggestion else ""
                lines.append(f"  * [{i.severity}] {i.field} ({i.issue_type}) {i.description}{sug}")
        else:
            lines.append("- Issues: none")

        return "\n".join(lines)
