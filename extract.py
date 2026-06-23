import sys
import fitz
import re
import json
import argparse
from collections import Counter


## ===== 1. SETUP ===== ##

parser = argparse.ArgumentParser(
    description="Extract candidate information, links and claims from a CV PDF."
)
parser.add_argument("pdf_path", help="Path to CV PDF file")
args = parser.parse_args()
pdf_path = args.pdf_path

doc = fitz.open(pdf_path)


## ===== 2. HELPER FUNCTIONS ===== ##

# PyMuPDF sometimes misreads fancy quote/apostrophe glyphs as raw control
# characters (e.g. \u0010 for ", \u0013 for '). sanitize_text swaps them
# back to real punctuation and strips any remaining stray control chars so
# downstream regex never trips on invisible garbage bytes.
def sanitize_text(text):
    replacements = {
        "\u0010": '"', "\u0011": '"', "\u0013": "'", "\u0014": "'",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return text


def clean_start(line):
    line = sanitize_text(line)
    return re.sub(r"^[^A-Za-z0-9]+", "", line).strip()


def find_links_in_line(line):
    found = re.findall(
        r"(?:https?://|www\.)?[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s,;)]*)?",
        line
    )
    return [u for u in found if u.startswith("http") or u.startswith("www.") or "/" in u]


def starts_with_bullet(line):
    return not line[:1].isalnum()


## ===== 2A. SECTION-HEADING -> CLAIM-TYPE MAP ===== ## 

ALLOWED_CLAIM_TYPES = {
    "experience", "education", "project", "certification", "publication", "hackathon"
}

SECTION_TYPE_PATTERNS = [
    (re.compile(r"\bhackathons?\b|\bcompetitions?\b", re.IGNORECASE), "hackathon"),
    (re.compile(
        r"\bcertifications?\b|\blicens(e|ing)s?\b|\bcredentials?\b",
        re.IGNORECASE), "certification"),
    (re.compile(
        r"\bpublications?\b|\bresearch\s+papers?\b|\bpapers?\b",
        re.IGNORECASE), "publication"),
    (re.compile(r"\bprojects?\b", re.IGNORECASE), "project"),
    (re.compile(
        r"\b(work\s+|professional\s+|relevant\s+)?experience\b|\bemployment\b|"
        r"\bwork\s+history\b|\bcareer\s+(history|summary)?\b|"
        r"\bprofessional\s+background\b|\bpositions?\s+held\b|\binternships?\b",
        re.IGNORECASE), "experience"),
    (re.compile(
        r"\beducation\b|\bacademic\s+(background|qualifications?|record|details|history)\b|"
        r"\bqualifications?\b|\bscholastic\s+(record|background)?\b",
        re.IGNORECASE), "education"),
    (re.compile(
        r"\bskills?\b|\btools?\b|\btechnolog(y|ies)\b|\bcompetenc(y|ies)\b",
        re.IGNORECASE), "skills"),
]


def classify_heading_text(text):
    cleaned = clean_start(text)
    for pattern, claim_type in SECTION_TYPE_PATTERNS:
        if pattern.search(cleaned):
            return claim_type
    return None


## ===== 2B. CONTENT-BASED PATTERNS (fallback only) ===== ##

DEGREE_LEVEL_PATTERN = re.compile(
    r"\bbachelor'?s?\b|\bmaster'?s?\b|\bdoctorate\b|\bdiploma\b|"
    r"\bundergraduate\b|\bpostgraduate\b|\bhsc\b|\bssc\b|"
    r"\bhigher secondary\b|\bsecondary education\b|\bcgpa\b|\bpercentage\s*:",
    re.IGNORECASE
)
DEGREE_ABBR_DOTTED_PATTERN = re.compile(
    r"\bph\.?\s?d\.?\b"
    r"|\bll\.?\s?[bm]\.?\b"
    r"|\b[bm]\.\s?[a-z]{1,6}\.?\b",
    re.IGNORECASE
)
DEGREE_ABBR_CAPS_PATTERN = re.compile(r"\b[BM][A-Z]{1,4}\b")


def has_degree_signal_in(original_case_text):
    return bool(
        DEGREE_LEVEL_PATTERN.search(original_case_text)
        or DEGREE_ABBR_DOTTED_PATTERN.search(original_case_text)
        or DEGREE_ABBR_CAPS_PATTERN.search(original_case_text)
    )


CERT_PATTERN = re.compile(
    r"\bcertificat(?:e|ion)s?\b|\bcertified\b|"
    r"\bcredential\s*(?:id|no\.?|number)?\b|"
    r"\blicense\s*(?:no\.?|number)?\b",
    re.IGNORECASE
)
PUBLICATION_PATTERN = re.compile(
    r"\b(arxiv|doi|journal|conference|workshop|paper|published|under review|proceedings)\b",
    re.IGNORECASE
)
HACKATHON_PATTERN = re.compile(r"hackathon|24[\s-]?hour|36[\s-]?hour|won \d|winner|runner[\s-]?up", re.IGNORECASE)
STRICT_DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+\b")
DATE_PATTERN = re.compile(
    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*\d{4}|\b\d{4}\b",
    re.IGNORECASE
)
DATE_RANGE_PATTERN = re.compile(
    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*\d{4}.{0,25}"
    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*\d{4}|"
    r"\b\d{4}\s*[\u2013\u2014\u2015-]\s*\d{4}\b|"
    r"\b\d{4}\s*[\u2013\u2014\u2015-]\s*present\b",
    re.IGNORECASE
)
PROJECT_SIGNAL_PATTERN = re.compile(
    r"\b(built|developed|designed|engineered|implemented|created|deployed|"
    r"represented|contributed|performed|applied|extract(?:s|ed)?|achiev(?:es|ed)?|"
    r"integrat(?:es|ed)?|optimi[sz](?:es|ed)?|automat(?:es|ed)?|generat(?:es|ed)?|"
    r"build(?:s)?|use(?:s|d)?|creates?)\b",
    re.IGNORECASE
)
SECTION_HEADING_PATTERN = re.compile(
    r"\b(experience|education|projects?|publications?|certifications?|"
    r"hackathons?|skills?|summary|objective|profile|achievements?|"
    r"awards?|references?|contact|interests?|languages?|volunteer(?:ing)?)\b",
    re.IGNORECASE
)


## ===== 3. EXTRACT ALL TEXT FROM PDF ===== ##

normal_text = ""
for page in doc:
    normal_text += page.get_text()

normal_text = sanitize_text(normal_text)
all_text_lines = [l.strip() for l in normal_text.split("\n") if l.strip()]

if not normal_text.strip():
    print("image-only pdf — no text layer")
    sys.exit(1)


## ===== 4. CANDIDATE NAME EXTRACTION ===== ##

candidate_name = ""

for idx, line in enumerate(all_text_lines[:10]):
    cleaned = clean_start(line)
    if not cleaned:
        continue
    if "@" in cleaned or find_links_in_line(cleaned):
        continue
    if re.search(r"\d", cleaned):
        continue

    nearby_text = " ".join(all_text_lines[idx + 1: idx + 3])
    if DATE_RANGE_PATTERN.search(nearby_text):
        continue

    if has_degree_signal_in(cleaned):
        continue
    if CERT_PATTERN.search(cleaned):
        continue
    if PUBLICATION_PATTERN.search(cleaned):
        continue
    if HACKATHON_PATTERN.search(cleaned):
        continue
    if SECTION_HEADING_PATTERN.search(cleaned):
        continue

    if re.match(r"^[A-Za-z.]+(?:\s+[A-Za-z.]+){1,3}$", cleaned):
        candidate_name = cleaned
        break


## ===== 5. EMAIL & PHONE EXTRACTION ===== ##

emails = re.findall(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    normal_text
)

phones = re.findall(
    r"\+?\d{1,3}[\s.-]\d{10}"
    r"|\d{1,3}-\d{10}"
    r"|(?:\(?\+?\d{1,3}\)?[\s.-]?)?(?:\d{2,5}[\s.-])+\d{3,5}"
    r"|\b\d{10}\b",
    normal_text
)
phones = [p.strip() for p in phones if len(re.sub(r"\D", "", p)) >= 10]


## ===== 6. LINKS EXTRACTION (TEXT + EMBEDDED) ===== ##

links = []
for line in all_text_lines:
    for url in find_links_in_line(line):
        links.append({"url": url, "source": "text", "anchor": url})

for page in doc:
    for link in page.get_links():
        if "uri" in link:
            anchor = ""
            if "from" in link:
                anchor = page.get_textbox(link["from"]).strip()
            links.append({"url": link["uri"], "source": "embedded", "anchor": anchor})

unique_links = []
seen_urls = set()
for link in links:
    if link["url"] not in seen_urls:
        unique_links.append(link)
        seen_urls.add(link["url"])


## ===== 7. HEADING DETECTION (FONT SIZE / BOLD BASED) ===== ##

font_sizes = []
for page in doc:
    d = page.get_text("dict")
    for block in d["blocks"]:
        if "lines" not in block:
            continue
        for line in block["lines"]:
            real_spans = [s for s in line["spans"] if re.search(r"[A-Za-z0-9]", s["text"])]
            if real_spans:
                font_sizes.append(round(max(s["size"] for s in real_spans)))

body_size = Counter(font_sizes).most_common(1)[0][0] if font_sizes else 0

heading_candidate_sizes = []
for page in doc:
    d = page.get_text("dict")
    for block in d["blocks"]:
        if "lines" not in block:
            continue
        for line in block["lines"]:
            real_spans = [s for s in line["spans"] if re.search(r"[A-Za-z0-9]", s["text"])]
            if not real_spans:
                continue
            text = "".join(s["text"] for s in line["spans"]).strip()
            if not text or len(text.split()) > 5:
                continue
            if starts_with_bullet(text):
                continue
            if candidate_name and clean_start(text).lower() == candidate_name.lower():
                continue
            size = max(s["size"] for s in real_spans)
            is_bold = any("bold" in s["font"].lower() for s in real_spans)
            if is_bold or size > body_size + 0.4:
                heading_candidate_sizes.append(size)

top_heading_size = max(heading_candidate_sizes) if heading_candidate_sizes else body_size


def line_is_heading(text, real_spans):
    if not real_spans:
        return False
    if starts_with_bullet(text):
        return False

    max_size = max(s["size"] for s in real_spans)
    is_bold = any("bold" in s["font"].lower() for s in real_spans)
    word_count = len(text.split())

    is_emphasised = is_bold or max_size > body_size + 0.4
    is_top_size_tier = abs(max_size - top_heading_size) < 0.3
    is_all_caps = text.isupper() and any(c.isalpha() for c in text)

    return (
        word_count <= 5
        and is_emphasised
        and (is_top_size_tier or is_all_caps)
        and not text.endswith(".")
        and "@" not in text
        and "|" not in text
        and not re.search(r"\d", text)
        and not find_links_in_line(text)
    )


## ===== 8. TYPE GUESSING HELPERS ===== ##

def is_skills_list_pattern(text):
    comma_count = text.count(",")
    period_count = text.count(".")
    word_count = len(text.split())
    if word_count == 0:
        return False
    comma_density = comma_count / max(word_count, 1)
    return comma_density > 0.12 and period_count <= 1


def is_title_like(line):
    words = line.split()
    return (
        2 <= len(words) <= 14
        and line[:1].isalpha()
        and "@" not in line
        and not line.endswith(".")
    )


def split_long_publication_title(title, details):
    quote_match = re.search(r'"([^"]+)"', title)
    if not quote_match:
        return title, details

    new_title = quote_match.group(1).strip().rstrip(",").strip()
    leftover = (title[:quote_match.start()] + title[quote_match.end():]).strip(" ,.\"")
    leftover = re.sub(r"\s+", " ", leftover)
    new_details = (leftover + " " + details).strip() if leftover else details

    if not new_title:
        return title, details

    return new_title, new_details


def guess_type_from_content(title, details):
    full_text = title + " " + details
    t = full_text.lower()

    has_degree_signal = has_degree_signal_in(full_text)
    has_cert_signal = bool(CERT_PATTERN.search(t))
    has_hackathon_signal = bool(HACKATHON_PATTERN.search(t))
    has_publication_signal = bool(
        PUBLICATION_PATTERN.search(t) or STRICT_DOI_PATTERN.search(full_text)
    )

    has_action_in_title = bool(PROJECT_SIGNAL_PATTERN.search(title.lower()))
    has_action_anywhere = bool(PROJECT_SIGNAL_PATTERN.search(t))

    has_date_range_signal = bool(DATE_RANGE_PATTERN.search(t))

    if not has_degree_signal and not has_date_range_signal and not has_action_anywhere \
            and not has_cert_signal and not has_hackathon_signal and not has_publication_signal:
        if is_skills_list_pattern(full_text):
            return None, title, details

    if not is_title_like(title):
        return None, title, details

    if has_degree_signal:
        return "education", title, details
    if has_cert_signal:
        return "certification", title, details
    if has_hackathon_signal:
        return "hackathon", title, details

    if has_action_in_title:
        return "project", title, details

    if has_date_range_signal:
        return "experience", title, details

    if has_action_anywhere:
        return "project", title, details

    if has_publication_signal:
        new_title, new_details = split_long_publication_title(title, details)
        return "publication", new_title, new_details

    has_date = bool(DATE_PATTERN.search(t))
    word_count = len(full_text.split())

    if has_date:
        if word_count < 15:
            return "certification", title, details
        return "experience", title, details

    return None, title, details


## ===== 9. BLOCK EXTRACTION FROM PDF ===== ##

raw_units = []

for page in doc:
    d = page.get_text("dict")
    for block in d["blocks"]:
        if "lines" not in block:
            continue

        block_text_lines = []
        for line in block["lines"]:
            text = sanitize_text("".join(s["text"] for s in line["spans"]).strip())
            if text:
                real_spans = [s for s in line["spans"] if re.search(r"[A-Za-z0-9]", s["text"])]
                block_text_lines.append((text, real_spans))

        if not block_text_lines:
            continue

        if len(block_text_lines) == 1:
            text, real_spans = block_text_lines[0]
            if line_is_heading(text, real_spans):
                if candidate_name and clean_start(text).lower() == candidate_name.lower():
                    raw_units.append({"kind": "skip", "lines": [text]})
                else:
                    raw_units.append({"kind": "heading", "lines": [text]})
                continue

        raw_units.append({"kind": "content", "lines": [t for t, _ in block_text_lines]})


def split_content_block(block_lines):
    first_is_bullet = starts_with_bullet(block_lines[0])

    if not first_is_bullet:
        title = clean_start(block_lines[0])
        details = " ".join(clean_start(l) for l in block_lines[1:])
        return [{"title": title, "details": details}]

    items = []
    current_title = None
    current_details = ""
    for line in block_lines:
        if starts_with_bullet(line):
            if current_title:
                items.append((current_title, current_details))
            current_title = clean_start(line)
            current_details = ""
        else:
            current_details = (current_details + " " + clean_start(line)).strip() if current_details else clean_start(line)
    if current_title:
        items.append((current_title, current_details))

    return [{"title": t, "details": d} for t, d in items]


GPA_NOTATION_PATTERN = re.compile(r"\bc?gpa\s*[:\-]?\s*\d", re.IGNORECASE)


def is_continuation_block(text):
    return bool(DATE_PATTERN.search(text)) or bool(GPA_NOTATION_PATTERN.search(text))


## ===== 10. MERGE BLOCKS INTO FINAL ENTRIES ===== ##

candidate_entries = []
seen_first_heading = False
current_section_type = None
entry_open = False
last_entry_ref = None

for unit in raw_units:
    if unit["kind"] == "skip":
        continue

    if unit["kind"] == "heading":
        seen_first_heading = True
        current_section_type = classify_heading_text(unit["lines"][0])
        entry_open = False
        last_entry_ref = None
        continue

    lines = unit["lines"]
    first_is_bullet = starts_with_bullet(lines[0])
    block_text = " ".join(clean_start(l) for l in lines)

    # Multi-bullet merging (treating the NEXT single-bullet block as a
    # continuation of the PREVIOUS entry, e.g. a job-title bullet followed
    # by a company/date bullet) is only structurally valid for section
    # types where one entry legitimately spans several bullets. For flat
    # list sections — certification, hackathon, publication — every
    # bullet is an independent sibling item and must become its own
    # entry; merging them was the root cause of two certifications
    # collapsing into a single claim.
    CONTINUATION_ELIGIBLE_TYPES = {"experience", "education", "project", None}

    if first_is_bullet:
        if (
            entry_open
            and last_entry_ref is not None
            and current_section_type in CONTINUATION_ELIGIBLE_TYPES
        ):
            last_entry_ref["details"] = (last_entry_ref["details"] + " " + block_text).strip()
        else:
            items = split_content_block(lines)
            for entry in items:
                candidate_entries.append((entry, seen_first_heading, current_section_type))

            if len(items) == 1:
                last_entry_ref = items[0]
                entry_open = True
            else:
                entry_open = False
                last_entry_ref = None

    else:
        if entry_open and last_entry_ref is not None and is_continuation_block(lines[0]):
            last_entry_ref["details"] = (last_entry_ref["details"] + " " + block_text).strip()
        else:
            title = clean_start(lines[0])
            details = " ".join(clean_start(l) for l in lines[1:])
            entry = {"title": title, "details": details}
            candidate_entries.append((entry, seen_first_heading, current_section_type))
            last_entry_ref = entry
            entry_open = True


## ===== 11. BUILD FINAL CLAIMS LIST ===== ##

claims = []
for entry, came_after_heading, section_type in candidate_entries:
    if not came_after_heading:
        continue

    if section_type == "skills":
        continue

    content_type, final_title, final_details = guess_type_from_content(entry["title"], entry["details"])

    if section_type:
        if content_type is None and (
            not is_title_like(entry["title"])
            or is_skills_list_pattern(entry["title"] + " " + entry["details"])
        ):
            continue
        claim_type = section_type
        if content_type is None:
            final_title, final_details = entry["title"], entry["details"]
    else:
        if content_type is None:
            continue
        claim_type = content_type

    if claim_type not in ALLOWED_CLAIM_TYPES:
        continue

    full_text = final_title + " " + final_details
    claim_links = []
    for url in find_links_in_line(full_text):
        if url not in claim_links:
            claim_links.append(url)

    claims.append({
        "type": claim_type,
        "title": final_title,
        "details": final_details.strip(),
        "links": claim_links
    })


## ===== 12. WARNINGS ===== ##

warnings = []
if not candidate_name:
    warnings.append("candidate name not found")
if not emails:
    warnings.append("email not found")
if not phones:
    warnings.append("phone not found")
if not unique_links:
    warnings.append("no links found")
if not claims:
    warnings.append("no claims found")


## ===== 13. FINAL JSON OUTPUT ===== ##

output = {
    "candidate": {
        "name": candidate_name,
        "email": emails[0] if emails else "",
        "phone": phones[0] if phones else ""
    },
    "links": unique_links,
    "claims": claims,
    "meta": {
        "pages": len(doc),
        "has_text_layer": True,
        "warnings": warnings
    }
}

with open("cv.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=4)

print(json.dumps(output, indent=4))
