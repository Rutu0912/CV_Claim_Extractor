import sys
import fitz
import re
import json
import argparse
from collections import Counter


## ===== 1. SETUP — READ PDF PATH & OPEN FILE ===== ##

# take pdf path from command line
parser = argparse.ArgumentParser(
    description="Extract candidate information, links and claims from a CV PDF."
)
parser.add_argument("pdf_path", help="Path to CV PDF file")
args = parser.parse_args()
pdf_path = args.pdf_path

# open the pdf file
doc = fitz.open(pdf_path)


## ===== 2. HELPER FUNCTIONS ===== ##

# PDF se quote symbols kabhi galat decode ho kar control characters
# (\u0010 etc) ban jaate hain. ye function:
# - inko sahi quote (") mein convert karta hai
# - baaki stray control characters hata deta hai
def sanitize_text(text):
    replacements = {
        "\u0010": '"',
        "\u0011": '"',
        "\u0013": "'",
        "\u0014": "'",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    # bache hue kisi bhi control character ko hata do (whitespace chhodke)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return text


# remove bullet/symbol from start of line
def clean_start(line):
    line = sanitize_text(line)
    return re.sub(r"^[^A-Za-z0-9]+", "", line).strip()


# find urls/links inside a line of text
def find_links_in_line(line):
    found = re.findall(
        r"(?:https?://|www\.)?[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s,;)]*)?",
        line
    )
    return [u for u in found if u.startswith("http") or u.startswith("www.") or "/" in u]


# check if line starts with bullet/symbol, not letter or digit
def starts_with_bullet(line):
    return not line[:1].isalnum()


## ===== 3. EXTRACT ALL TEXT FROM PDF ===== ##

# get all text from pdf, used for name/email/phone
normal_text = ""
for page in doc:
    normal_text += page.get_text()

# email/phone regex isi par chalte hain, isliye sanitize zaroori
normal_text = sanitize_text(normal_text)

all_text_lines = [l.strip() for l in normal_text.split("\n") if l.strip()]

# stop if pdf has no text (scanned/image only)
if not normal_text.strip():
    print("image-only pdf — no text layer")
    sys.exit(1)


## ===== 4. CANDIDATE NAME EXTRACTION (SIMPLE HEURISTIC) ===== ##

# simple heuristic, koi keyword-blacklist ya font-size nahi:
# - top 10 lines mein dekho
# - jo pehli line "naam jaisi shape" mein mile (letters only, 2-4
#   words, all-caps nahi, koi digit/email/link nahi), wahi naam hai
candidate_name = ""

for line in all_text_lines[:10]:
    cleaned = clean_start(line)
    if not cleaned:
        continue
    if "@" in cleaned or find_links_in_line(cleaned):
        continue
    if re.search(r"\d", cleaned):
        continue
    if cleaned.isupper():
        continue
    if re.match(r"^[A-Za-z]+(?:\s+[A-Za-z]+){1,3}$", cleaned):
        candidate_name = cleaned
        break


## ===== 5. EMAIL & PHONE EXTRACTION ===== ##

# extract email and phone number using regex
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

# collect links from plain text + actual hyperlinks in pdf
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

# remove duplicate links
unique_links = []
seen_urls = set()
for link in links:
    if link["url"] not in seen_urls:
        unique_links.append(link)
        seen_urls.add(link["url"])


## ===== 7. HEADING DETECTION (FONT SIZE / BOLD BASED) ===== ##

# step 1: find most common font size = body text size
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


# step 2: find the biggest font size used for bold/big lines (real headings)
# skip candidate name, it can also be big/bold but is not a heading
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


# check if a line is a section heading (eg "Experience", "Education")
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


## ===== 8. TYPE GUESSING — REGEX PATTERNS ===== ##

# regex patterns used to guess what TYPE of entry a block is
JOB_TITLE_PATTERN = re.compile(
    r"\b(fellow|intern(ship)?|manager|engineer|developer|analyst|officer|"
    r"representative|coordinator|associate|specialist|consultant|researcher|"
    r"trainee|executive|director|administrator|assistant)\b",
    re.IGNORECASE
)
DEGREE_PATTERN = re.compile(
    r"\bcgpa\b|\bb\.?tech\b|\bb\.?e\.?\b|\bm\.?tech\b|\bbachelor\b|"
    r"\bmaster\b|\bhsc\b|\bssc\b|\bdiploma\b|\bhigher secondary\b|"
    r"\bsecondary education\b|\bpercentage\s*:",
    re.IGNORECASE
)
CERT_PATTERN = re.compile(r"certificat|credential id|license no", re.IGNORECASE)
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


# check if text looks like a skills list (many commas, no real sentence)
def is_skills_list_pattern(text):
    comma_count = text.count(",")
    period_count = text.count(".")
    word_count = len(text.split())
    if word_count == 0:
        return False
    comma_density = comma_count / max(word_count, 1)
    return comma_density > 0.12 and period_count <= 1


# check if a line looks like a short title, not a long sentence
def is_title_like(line):
    words = line.split()
    return (
        2 <= len(words) <= 14
        and line[:1].isalpha()
        and "@" not in line
        and not line.endswith(".")
    )


# lamba publication title (poora sentence) chhota karne ke liye:
# - title ke andar agar quotes hon (paper ka naam), wahi naya title bane
# - baaki sentence (Published/Journal/DOI) details mein chala jaye
# - quotes na milein to title jaise ka taisa rahega
def split_long_publication_title(title, details):
    quote_match = re.search(r'"([^"]+)"', title)
    if not quote_match:
        return title, details

    # title ke andar agar trailing comma ho (jaise "...Surveillance,") to use bhi hata do
    new_title = quote_match.group(1).strip().rstrip(",").strip()
    # quote ke andar wala part title se hata kar baaki sab details mein daal do
    leftover = (title[:quote_match.start()] + title[quote_match.end():]).strip(" ,.\"")
    leftover = re.sub(r"\s+", " ", leftover)  # extra double-spaces clean karo
    new_details = (leftover + " " + details).strip() if leftover else details

    if not new_title:
        return title, details

    return new_title, new_details


# main function: guess claim type (job/education/project/etc) from text
# returns (type, final_title, final_details) -- title/details change
# sirf publication case mein (split_long_publication_title se)
def guess_type_from_content(title, details):
    full_text = title + " " + details
    t = full_text.lower()

    # degree/job-title/action-verb signal poore text (title+details) par
    # check karte hain -- asli CVs mein institute-naam title mein hota
    # hai aur "B.Tech/CGPA" details mein, isliye sirf title tak limit
    # karna education/experience detection todta hai
    has_degree_signal = bool(DEGREE_PATTERN.search(t))
    has_job_signal = bool(JOB_TITLE_PATTERN.search(title))
    has_action_signal = bool(PROJECT_SIGNAL_PATTERN.search(t))

    # publication signal poore text mein dhoondo (title sirf paper-naam
    # ho sakta hai, "Published/DOI" details mein ho sakta hai), lekin
    # tabhi maano jab title mein job-title/degree signal NA ho -- warna
    # "Research Fellow ... published in IJERT" jaisi internship entries
    # galti se publication ban jaati hain
    title_lower = title.lower()
    has_publication_signal = bool(
        PUBLICATION_PATTERN.search(t) or STRICT_DOI_PATTERN.search(full_text)
    )
    title_has_job_or_degree = bool(
        JOB_TITLE_PATTERN.search(title) or DEGREE_PATTERN.search(title_lower)
    )


    has_cert_signal = bool(CERT_PATTERN.search(t))
    has_hackathon_signal = bool(HACKATHON_PATTERN.search(t))

    if not has_degree_signal and not has_job_signal and not has_action_signal \
            and not has_cert_signal and not has_hackathon_signal:
        if is_skills_list_pattern(full_text):
            return None, title, details

    # long sentence title = probably summary text, not a real claim
    if not is_title_like(title):
        return None, title, details

    if has_job_signal:
        return "experience", title, details
    if has_degree_signal:
        return "education", title, details
    if CERT_PATTERN.search(t):
        return "certification", title, details
    if HACKATHON_PATTERN.search(t):
        return "hackathon", title, details

    has_date_range = bool(DATE_RANGE_PATTERN.search(t))
    has_date = bool(DATE_PATTERN.search(t))
    has_action = bool(PROJECT_SIGNAL_PATTERN.search(t))
    word_count = len(full_text.split())

    # action verbs (built/designed/etc) = most likely a project
    if has_action:
        return "project", title, details
    
    # publication check after project check
    if has_publication_signal and not title_has_job_or_degree:
        new_title, new_details = split_long_publication_title(title, details)
        return "publication", new_title, new_details

    if has_date_range:
        return "experience", title, details

    if has_date:
        # short text with just a year = likely a certification
        if word_count < 15:
            return "certification", title, details
        return "experience", title, details

    return None, title, details


## ===== 9. BLOCK EXTRACTION FROM PDF ===== ##

# BLOCK EXTRACTION: group pdf text into blocks (each block ~ one entry)
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
                # skip candidate's own name even if it looks like heading
                if candidate_name and clean_start(text).lower() == candidate_name.lower():
                    raw_units.append({"kind": "skip", "lines": [text]})
                else:
                    raw_units.append({"kind": "heading", "lines": [text]})
                continue

        raw_units.append({"kind": "content", "lines": [t for t, _ in block_text_lines]})


# split one block into one or more entries (title + details)
def split_content_block(block_lines):
    first_is_bullet = starts_with_bullet(block_lines[0])

    if not first_is_bullet:
        title = clean_start(block_lines[0])
        details = " ".join(clean_start(l) for l in block_lines[1:])
        return [{"title": title, "details": details}]

    # bullet wali line = title, baaki continuation lines = details
    # (pehle sab title mein jud jaata tha, claim drop ho jaati thi)
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


# helper: check if block is just a date/gpa line (continuation of last entry)
GPA_NOTATION_PATTERN = re.compile(r"\bc?gpa\s*[:\-]?\s*\d", re.IGNORECASE)


def is_continuation_block(text):
    return bool(DATE_PATTERN.search(text)) or bool(GPA_NOTATION_PATTERN.search(text))


## ===== 10. MERGE BLOCKS INTO FINAL ENTRIES ===== ##

# merge blocks into final entry list (handles split title/date/bullets)
candidate_entries = []
seen_first_heading = False
entry_open = False
last_entry_ref = None

for unit in raw_units:
    if unit["kind"] == "skip":
        continue

    if unit["kind"] == "heading":
        seen_first_heading = True
        entry_open = False
        last_entry_ref = None
        continue

    lines = unit["lines"]
    first_is_bullet = starts_with_bullet(lines[0])
    block_text = " ".join(clean_start(l) for l in lines)

    if first_is_bullet:
        if entry_open and last_entry_ref is not None:
            # bullets right after open entry = its details
            last_entry_ref["details"] = (last_entry_ref["details"] + " " + block_text).strip()
        else:
            # no open entry = independent list (skills etc)
            for entry in split_content_block(lines):
                candidate_entries.append((entry, seen_first_heading))
            entry_open = False
            last_entry_ref = None

    else:
        if entry_open and last_entry_ref is not None and is_continuation_block(lines[0]):
            # just metadata (date/gpa), merge into open entry
            last_entry_ref["details"] = (last_entry_ref["details"] + " " + block_text).strip()
        else:
            # new entry header found
            title = clean_start(lines[0])
            details = " ".join(clean_start(l) for l in lines[1:])
            entry = {"title": title, "details": details}
            candidate_entries.append((entry, seen_first_heading))
            last_entry_ref = entry
            entry_open = True


## ===== 11. BUILD FINAL CLAIMS LIST ===== ##

# build final claims list with type + links
claims = []
for entry, came_after_heading in candidate_entries:
    if not came_after_heading:
        continue

    # guess_type_from_content 3 values deta hai: type + (zaroorat pade
    # to) updated title/details -- sirf publication case mein badalte hain
    claim_type, final_title, final_details = guess_type_from_content(entry["title"], entry["details"])
    if claim_type is None:
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

# add warnings if something important is missing
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

# build final json output and save to file
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
