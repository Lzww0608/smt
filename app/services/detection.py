import re

from app.models.schemas import ContentType


SMT_HINT_PATTERNS = (
    r"\(declare-[a-z-]+",
    r"\(assert\b",
    r"\(check-sat\b",
    r"\(set-logic\b",
    r"\(define-fun\b",
    r"\bSMT-LIB\b",
)


def detect_content_type(content: str) -> ContentType:
    stripped = content.strip()
    if stripped.startswith("(") and ")" in stripped:
        return ContentType.SMT_CODE

    for pattern in SMT_HINT_PATTERNS:
        if re.search(pattern, stripped, flags=re.IGNORECASE):
            return ContentType.SMT_CODE

    return ContentType.NATURAL_LANGUAGE
