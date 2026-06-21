# CV Claim Extractor

A command-line Python tool that extracts structured information from CV PDFs and converts it into structured JSON output.

## Requirements

- Python 3.11
- PyMuPDF

## Setup

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

---

## Output Structure

The generated JSON contains:

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

Candidate name extraction uses deterministic heuristics applied to the top portion of the resume. Lines containing links, emails, numbers, or non-name patterns are filtered out before selecting the most likely candidate name.

### Section Heading Detection

Section headings are detected using document formatting rather than relying only on fixed keywords. The extractor analyzes font size, text emphasis (bold text), and heading-like structure to identify section boundaries. This approach makes the extraction process more adaptable to different resume formats and naming conventions.

### Link Extraction

Links are collected from two sources:

1. URLs present directly in resume text
2. Embedded PDF hyperlinks obtained through PDF annotations

This helps detect links even when the visible text only contains labels such as GitHub, LinkedIn, Portfolio, or Repository.

### Claim Extraction

Resume content is first divided into logical text blocks extracted from the PDF. Using detected section boundaries, related blocks are grouped into individual claims such as jobs, projects, education entries, certifications, publications, or hackathons.

Special handling is applied for bullet points, continuation lines, dates, and GPA information to keep related content grouped together and reduce fragmented claims.

### Claim Classification

Each extracted claim is classified into a specific category using a combination of title patterns, job-title indicators, degree indicators, action verbs, date patterns, publication signals, and other contextual clues.

Multiple signals are considered together to improve classification accuracy while keeping the system fully deterministic.

### Claim-to-Link Matching

Links are attached only to the claim in which they appear.

This local matching strategy keeps the behavior predictable, explainable, and avoids making assumptions across unrelated sections.

---

## Limitations

1. Extraction quality depends on the text structure available within the PDF.

2. Complex layouts containing multiple columns, tables, sidebars, or heavily customized formatting may affect text ordering and extraction quality.

3. Candidate name extraction and claim classification rely on deterministic heuristics and may be less accurate for unusual resume formats.

4. Link-to-claim matching is based on local text association and may not always capture visually related links located elsewhere in the document.

---

## Future Improvements

- Improve support for complex multi-column resume layouts.
- Improve claim grouping for highly customized resume structures.
- Enhance classification using additional document structure signals.
- Improve layout-aware link association techniques.
- Expand support for a wider variety of resume formats.

---

## Design Choices

- Deterministic extraction
- No LLMs
- No paid APIs
- No OCR
- No database
- No UI
- Command-line based execution
- Explainable rule-based heuristics
