# CV Claim Extractor

A command-line Python tool that extracts structured information from CV PDFs and converts it into structured JSON output.

## Requirements

- Python 3.11
- PyMuPDF

## Setup

### Option 1: Clone with Git

```bash
git clone https://github.com/Rutu0912/CV_Claim_Extractor.git
cd CV_Claim_Extractor
```

### Option 2: Download ZIP

Download the repository as a ZIP file from GitHub and extract it locally.

Open a terminal inside the extracted project folder.

### Install Dependencies

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

Run the extractor:

```bash
python extract.py path/to/cv.pdf
```

Example:

```bash
python extract.py Resume_Examples/Rutu_Patel_Resume.pdf
```

The tool prints the extracted JSON and also saves it as:

```bash
cv.json
```

If no argument is provided:

```bash
python extract.py
```

the program displays usage information and exits cleanly.

If the PDF does not contain a text layer:

```text
image-only pdf — no text layer
```

is displayed and the program exits.

---

## Output Structure

### Candidate

- Name
- Email
- Phone Number

### Links

- Text URLs
- Embedded PDF Hyperlinks

### Claims

- Experience
- Education
- Projects
- Certifications
- Publications
- Hackathons

### Metadata

- Page Count
- Text Layer Status
- Warnings

---

## Approach

### Candidate Information Extraction

Email addresses and phone numbers are extracted using regular expressions.

Candidate names are identified using deterministic heuristics applied to the top section of the resume. The extractor filters out contact information, links, section headings, qualification indicators, and other non-name content before selecting the most likely candidate name.

### Section Detection

The extractor identifies section boundaries using document structure and formatting signals such as font size, text emphasis, and heading-like layout.

This allows it to work with different heading names and resume styles instead of relying only on fixed keywords.

### Link Extraction

Links are collected from:

1. URLs present directly in resume text
2. Embedded PDF hyperlink annotations

This allows detection of links even when the visible text is only a label such as GitHub, LinkedIn, Portfolio, or Repository.

### Claim Extraction

Resume content is grouped into logical entries using PDF text blocks, section boundaries, dates, bullet points, and continuation lines.

This helps keep related information together and reduces fragmented claims.

### Claim Classification

Claim classification primarily uses the section in which an entry appears, such as Experience, Education, Projects, Certifications, Publications, or Hackathons.

When section information is unclear, additional structural signals such as dates, degree indicators, certification indicators, publication indicators, and project-related patterns are used as fallbacks.

This approach reduces dependence on specific job titles and makes the classification more adaptable across different resume styles and domains.

### Claim-to-Link Matching

Links are attached only to the claim in which they appear.

This keeps the matching predictable, explainable, and avoids assumptions across unrelated sections.

---

## Limitations

1. Extraction quality depends on the text structure available in the PDF.

2. Highly customized layouts, tables, sidebars, or complex multi-column designs may affect extraction quality.

3. Link-to-claim matching is based on local text association and may not always reflect visual relationships within the document.

4. PDF text extraction depends on the reading order provided by the document. In some multi-column or densely formatted resumes, separate entries may occasionally be merged, split, or ordered differently than their visual layout.

---

## Design Choices

- Deterministic extraction
- No LLMs
- No paid APIs
- No OCR
- No database
- No UI
- Command-line execution
- Explainable rule-based heuristics
