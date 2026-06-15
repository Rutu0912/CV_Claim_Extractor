import sys
import fitz
import re
import json
import argparse


# =========================
# 1. CLI ARGUMENT PARSING
# =========================
# Reads PDF path from command line.
parser = argparse.ArgumentParser(
    description="Extract candidate information, links and claims from a CV PDF."
)

parser.add_argument(
    "pdf_path",
    help="Path to CV PDF file"
)

args = parser.parse_args()
pdf_path = args.pdf_path

# =========================
# 2. OPEN PDF FILE
# =========================
# pdf_path was already read from command-line arguments
# using argparse in Step 1.
# Open the PDF using PyMuPDF.

doc = fitz.open(pdf_path)

# =========================
# TEXT EXTRACTION
# =========================
# First try normal text extraction.
# This usually gives the best reading order
# for standard one-column resumes.

normal_text = ""
for page in doc:
    normal_text += page.get_text()

normal_lines = [
    line.strip()
    for line in normal_text.split("\n")
    if line.strip()
]

# =========================
# BLOCK-BASED EXTRACTION
# =========================
# Also build a second version using text blocks.
# This can improve ordering for two-column CVs.

block_lines = []

for page in doc:

    page_width = page.rect.width
    blocks = page.get_text("blocks")

    left_blocks = []
    right_blocks = []

    for block in blocks:
        x0 = block[0]

        if x0 < page_width / 2:
            left_blocks.append(block)
        else:
            right_blocks.append(block)

    left_blocks.sort(key=lambda b: b[1])
    right_blocks.sort(key=lambda b: b[1])

    ordered_blocks = left_blocks + right_blocks

    for block in ordered_blocks:
        for line in block[4].split("\n"):
            line = line.strip()

            if line:
                block_lines.append(line)

# =========================
# CHOOSE BETTER VERSION
# =========================
# Heuristic:
# If block extraction produces significantly
# more content, prefer it.
# Otherwise keep normal extraction.

if len(block_lines) > len(normal_lines) * 1.1:
    lines = block_lines
else:
    lines = normal_lines

text = "\n".join(lines)

# =========================
# 4. IMAGE-ONLY PDF CHECK
# =========================
# If text is empty, it means PDF has no text layer.
# This handles scanned/photo CVs safely.
if not text.strip():
    print("image-only pdf — no text layer")
    sys.exit(1)


# =========================
# 6. MERGE HYPHENATED LINES
# =========================
# If a word is broken using "-" at line end,
# join it with the next line.

merged_lines = []

for line in lines:
    if merged_lines and merged_lines[-1].endswith("-"):
        merged_lines[-1] = merged_lines[-1][:-1] + line
    else:
        merged_lines.append(line)

lines = merged_lines

# =========================
# 7. BASIC LINE CLEANER
# =========================
# This removes bullets or symbols from the start of a line.
def clean_start(line):
    return re.sub(r"^[^A-Za-z0-9]+", "", line).strip()

# =========================
# 11. TEXT URL EXTRACTION FUNCTION
# =========================
# This function detects URLs written directly inside CV text.
# Example: github.com/user, https://site.com, www.site.com/page

def find_links_in_line(line):
    found = re.findall(
        r"(?:https?://|www\.)?[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s,;)]*)?",
        line
    )

    result = []
    for url in found:
        # Keep only link-like values.
        # This avoids normal words like email domain parts or plain text fragments.
        if url.startswith("http") or url.startswith("www.") or "/" in url:
            result.append(url)

    return result


# =========================
# CANDIDATE NAME EXTRACTION
# =========================
# Simple heuristic:
# Candidate name is usually near the top of the CV.
# We skip lines that look like headings, contacts, dates,
# links, role names, or institute/company names.

candidate_name = ""

bad_name_words = [
    "experience", "education", "skills", "summary",
    "profile", "contact", "project", "reference",
    "phone", "email", "address",
    "university", "college", "school", "institute",
    "manager", "intern", "specialist", "developer",
    "engineer", "student", "assistant"
]

for line in lines[:20]:
    cleaned = clean_start(line)
    lower_line = cleaned.lower()

    if not cleaned:
        continue

    if any(word in lower_line for word in bad_name_words):
        continue

    if "@" in cleaned or find_links_in_line(cleaned):
        continue

    if re.search(r"\d", cleaned):
        continue

    if re.match(r"^[A-Za-z]+(?:\s+[A-Za-z]+){1,3}$", cleaned):
        candidate_name = cleaned
        break


# =========================
# 9. EMAIL EXTRACTION
# =========================
# This finds email addresses from full PDF text.
emails = re.findall(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    text
)


# =========================
# 10. PHONE EXTRACTION
# =========================
# This finds phone numbers from full PDF text.
# Supports common 10-digit Indian style and country-code style numbers.
phones = re.findall(
    r"\+?\d{1,3}[\s.-]\d{10}"
    r"|\d{1,3}-\d{10}"
    r"|(?:\(?\+?\d{1,3}\)?[\s.-]?)?(?:\d{2,5}[\s.-])+\d{3,5}"
    r"|\b\d{10}\b",
    text
)
phones = [p.strip() for p in phones if len(re.sub(r'\D', '', p)) >= 10]




# =========================
# 12. COLLECT TEXT LINKS
# =========================
# This scans every line and stores URLs found in visible CV text.
# These links get source = "text".
links = []

for line in lines:
    for url in find_links_in_line(line):
        links.append({
            "url": url,
            "source": "text",
            "anchor": url
        })


# =========================
# 13. COLLECT EMBEDDED PDF LINKS
# =========================
# This extracts real PDF hyperlink annotations.
# It also works when visible text is only "Link".
# These links get source = "embedded".
for page in doc:
    for link in page.get_links():
        if "uri" in link:
            anchor = ""

            # Try to read visible text under the hyperlink rectangle.
            if "from" in link:
                anchor = page.get_textbox(link["from"]).strip()

            links.append({
                "url": link["uri"],
                "source": "embedded",
                "anchor": anchor
            })


# =========================
# 14. REMOVE DUPLICATE LINKS
# =========================
# This keeps only one copy of each URL.
# Original order is preserved.
unique_links = []
seen_urls = set()

for link in links:
    if link["url"] not in seen_urls:
        unique_links.append(link)
        seen_urls.add(link["url"])


# =========================
# SECTION TYPE DETECTION
# =========================
# Simple heuristic:
# Resume content is usually divided using headings.
# We detect common claim headings.
# We also detect non-claim headings only to stop old claim text
# from mixing into the next section.

def get_section_type(line):
    line = clean_start(line).lower()
    line = line.replace(":", "").strip()
    line = re.sub(r"\s+", " ", line)

    # Handles headings with extra spacing.
    compact = line.replace(" ", "")

    claim_sections = {
        "projects": "project",
        "project": "project",
        "personal projects": "project",
        "experience": "experience",
        "work experience": "experience",
        "work experiences": "experience",
        "internship": "experience",
        "internships": "experience",
        "education": "education",
        "educations": "education",
        "certifications": "certification",
        "certification": "certification",
        "publications": "publication",
        "publication": "publication",
        "hackathons": "hackathon",
        "hackathon": "hackathon",
        "achievements": "achievement",
        "achievement": "achievement",
        "awards": "achievement",
    }

    non_claim_sections = {
        "skills", "key skills", "technical skills",
        "summary", "profile", "profile summary",
        "career objective", "about me",
        "contact", "languages", "references"
    }

    compact_sections = {
        "workexperience": "experience",
        "workexperiences": "experience",
        "profilesummary": "non_claim",
        "careerobjective": "non_claim",
        "keyskills": "non_claim",
        "technicalskills": "non_claim",
    }

    if line in claim_sections:
        return claim_sections[line]

    if line in non_claim_sections:
        return "non_claim"

    if compact in compact_sections:
        return compact_sections[compact]

    return ""

# =========================
# 16. TITLE-LIKE LINE CHECK
# =========================
# This checks whether a line looks like a claim title.
# Used to split projects/experience/certifications into separate claims.

def is_title_like(original_line):
    if not original_line[:1].isalnum():
        return False

    line = clean_start(original_line)
    words = line.split()

    return (
        2 <= len(words) <= 18
        and line[:1].isalpha()
        and "@" not in line
        and "," not in line
        and "|" not in line
        and not line.endswith(".")
        and not find_links_in_line(line)
    )


# =========================
# 17. CLAIM EXTRACTION
# =========================
# This is the main claim grouping logic.
#
# Simple heuristic:
# 1. Resume claims usually live under headings like
#    Experience, Projects, Education, Certifications, etc.
# 2. When we enter a claim section, lines below it are grouped
#    as claims of that type.
# 3. When another section heading appears, the previous claim is closed.
# 4. Non-claim sections like Skills, Contact, Summary, Languages
#    are treated only as boundaries. They stop the previous claim,
#    but they are not added as claims.

claims = []
current_type = ""
current_claim = None
has_work_details = False

for line in lines:
    section_type = get_section_type(line)

    # =========================
    # SECTION CHANGE HANDLING
    # =========================
    # If current line is a section heading, close any running claim first.
    # This prevents Experience text from leaking into Education/Skills/etc.
    if section_type:
        if current_claim:
            claims.append(current_claim)

        current_claim = None
        has_work_details = False

        # "non_claim" means this is a real resume section,
        # but not a claim section for required output.
        # Example: Skills, Contact, Summary, Languages.
        # We stop claim extraction until a new claim section starts.
        if section_type == "non_claim":
            current_type = ""
        else:
            current_type = section_type

        continue

    # =========================
    # IGNORE TEXT OUTSIDE CLAIM SECTIONS
    # =========================
    # If we are not inside a claim section, do not create claims.
    # This avoids adding profile summary, skills, contact details, etc.
    if not current_type:
        continue

    clean_line = clean_start(line)
    line_links = find_links_in_line(line)

    # =========================
    # START FIRST CLAIM
    # =========================
    # First useful line after a claim section heading is treated as claim title.
    if current_claim is None:
        current_claim = {
            "type": current_type,
            "title": clean_line,
            "details": "",
            "links": []
        }
        has_work_details = False

    # =========================
    # START NEXT CLAIM
    # =========================
    # If a title-like line appears after details,
    # it probably starts a new project/job/education item.
    elif is_title_like(line) and has_work_details:
        claims.append(current_claim)

        current_claim = {
            "type": current_type,
            "title": clean_line,
            "details": "",
            "links": []
        }
        has_work_details = False

    # =========================
    # ADD DETAILS TO CURRENT CLAIM
    # =========================
    # Normal descriptive lines are added to the current claim details.
    else:
        current_claim["details"] += clean_line + " "

        # Once we see sentence-like detail text,
        # next title-like line can start a new claim.
        if "." in clean_line:
            has_work_details = True

    # =========================
    # LINK-TO-CLAIM MATCHING
    # =========================
    # Text URLs found inside the current claim block are attached
    # only to this claim. This keeps link matching simple and local.
    for url in line_links:
        if url not in current_claim["links"]:
            current_claim["links"].append(url)


# =========================
# ADD LAST CLAIM
# =========================
# After loop ends, add the final running claim if it exists.
if current_claim:
    claims.append(current_claim)

# =========================
# 18. WARNING COLLECTION
# =========================
# These are non-fatal warnings.
# The tool should still output valid JSON even if something is missing.
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


# =========================
# 19. FINAL JSON OUTPUT
# =========================
# This builds the required JSON structure.
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


# =========================
# 20. SAVE AND PRINT OUTPUT
# =========================
# Save result to cv.json and also print JSON to terminal.
with open("cv.json", "w", encoding="utf-8") as file:
    json.dump(output, file, indent=4)

print(json.dumps(output, indent=4))