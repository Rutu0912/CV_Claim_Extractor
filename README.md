# CV Claim Extractor

A command-line tool that extracts structured information from a CV PDF and outputs it as JSON.

## Requirements

- Python 3.11
- PyMuPDF

## Clean Machine Setup

Clone the repository:

```bash
git clone https://github.com/Rutu0912/CV_Claim_Extractor.git
cd CV_Claim_Extractor
```

Create a virtual environment and install dependencies:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Run the tool:

```bash
python extract.py path/to/cv.pdf
```

Example:

```bash
python extract.py Resume_Examples/Rutu_Patel_Resume.pdf
```

No arguments → prints usage and exits cleanly:

```bash
python extract.py
```

The command prints the extracted JSON and also saves it to `cv.json`.

## Approach

### Candidate Details

Name, email and phone number are extracted using deterministic rules and regular expressions.

### Link Extraction

Links are extracted from:

- URLs written directly in the CV text
- Embedded PDF hyperlinks using `page.get_links()`

This allows extraction of links even when the visible text is only "GitHub", "LinkedIn" or "Link".

### Claim Extraction

Claims are grouped using common resume section headings such as:

- Experience
- Projects
- Education
- Certifications
- Publications
- Hackathons
- Achievements

The first meaningful line becomes the claim title and the following lines are grouped as claim details.

### Claim-to-Link Matching

A simple local heuristic is used.

If a URL appears inside the text belonging to a claim, it is attached to that claim.

This keeps the behaviour deterministic, easy to explain and avoids assigning unrelated links across different sections.

## Limitations

1. Claim extraction depends on section headings. Resumes with combined or non-standard section titles may cause some claims to be grouped with nearby sections rather than extracted separately.

2. PDF text order does not always match the visual layout. Complex multi-column layouts, tables, sidebars or heavily designed resumes may affect extraction quality.

3. Name extraction is based on deterministic rules applied near the top portion of the resume. Unusual layouts may reduce accuracy.

4. Claim-to-link matching uses local text proximity. If a link is visually related to a claim but appears elsewhere in the extracted PDF text order, it may not always be attached to that specific claim.

## Design Choices

- Deterministic only
- No LLMs
- No paid APIs
- No OCR
- No database
- No UI
- No deployment
