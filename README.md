AI-powered earnings call analyzer that generates structured management commentary summaries in Screener.in format using Claude Sonnet.

README / longer description:

Concall Research Portal
An internal research tool that analyzes earnings call transcripts and produces structured analyst-grade summaries — modeled after Screener.in's concall summary format.
Features

Upload PDF (including scanned), DOCX, or TXT transcripts
AI extracts thematic sections, numbered sub-topics, key quotes, and management tone
Output mirrors professional equity research style with inline bold terms and direct management quotes
Backend keeps API key secure — evaluators just upload and read

Tech Stack

Frontend: Vanilla HTML/CSS/JS
Backend: FastAPI + Uvicorn (Python)
AI: Anthropic Claude Sonnet (claude-sonnet-4-6)
PDF parsing: PyMuPDF (supports scanned PDFs natively via Claude's document API)
Deployment: Render

Setup

Clone the repo
Add ANTHROPIC_API_KEY as an environment variable
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
