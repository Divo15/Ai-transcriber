from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
import anthropic
import fitz  # PyMuPDF
import docx
import os
import json
import io
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Concall Research Portal")

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are a senior equity research analyst producing a concall summary in the style of Screener.in — India's leading financial research platform.

Your output must be a JSON object structured EXACTLY as described below.

FORMAT RULES:
1. Identify 4–8 thematic sections from the transcript (e.g. "Revenue and financial performance", "Management's explanation of key concerns", "Growth initiatives", "Forward guidance", "Capacity utilization", "New business / partnerships", etc.). Use whatever themes actually appear — do not force themes not discussed.
2. Each section has a title and an array of items.
3. Each item is one of:
   - type "numbered": a numbered sub-topic (e.g. "1. Legacy receivables") with bullets underneath
   - type "subheading": a bold sub-heading with bullets (for sub-categories within a topic)
   - type "prose": a standalone narrative paragraph
4. Bullets are plain strings. Use **double asterisks** around KEY TERMS, NUMBERS, NAMES. Use regular double quotes around DIRECT QUOTES from management.
5. ONLY include information explicitly stated in the transcript. Never hallucinate. Omit sections not present.
6. Be specific — include actual figures, names, timelines, and direct quotes wherever they appear.

EXAMPLE BULLET STYLE:
- "Characterized as receivables **not due to be paid over a longer timeframe**. They executed **~INR60 crore** of experimental discounting already (\"off our books right now\")."
- "**Anchor customers**: \"AOS and L&T Semiconductor\""
- "Management stated PCB margins should be **above current consolidated levels**: \"definitely... higher... significantly higher than this.\""

OUTPUT JSON (no markdown fences, no explanation outside JSON):
{
  "company_name": "string",
  "period": "string e.g. Q2 FY2025 / Nov 2025",
  "management_tone": "Optimistic | Cautious | Neutral | Pessimistic",
  "confidence_level": "High | Medium | Low",
  "sections": [
    {
      "title": "Thematic section heading",
      "items": [
        { "type": "numbered", "heading": "1. Sub-topic heading", "bullets": ["bullet text with **bold** and \\"quoted\\" markers"] },
        { "type": "subheading", "heading": "Sub-category heading:", "bullets": ["bullet text"] },
        { "type": "prose", "text": "Narrative paragraph." }
      ]
    }
  ]
}"""


def extract_text_from_pdf(file_bytes: bytes) -> str:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    return text.strip()


def extract_text_from_docx(file_bytes: bytes) -> str:
    document = docx.Document(io.BytesIO(file_bytes))
    return "\n".join([p.text for p in document.paragraphs]).strip()


@app.get("/")
async def serve_frontend():
    return FileResponse("static/index.html")


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    MAX_SIZE = 20 * 1024 * 1024  # 20MB
    file_bytes = await file.read()

    if len(file_bytes) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 20MB.")

    filename = file.filename or ""
    ext = filename.lower().split(".")[-1]

    if ext not in ("pdf", "docx", "doc", "txt"):
        raise HTTPException(status_code=400, detail=f"Unsupported file type: .{ext}. Use PDF, DOCX, or TXT.")

    try:
        # For PDFs: send directly to Claude as base64 (handles scanned PDFs natively)
        if ext == "pdf":
            import base64
            b64 = base64.b64encode(file_bytes).decode("utf-8")
            messages = [{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": b64
                        }
                    },
                    {
                        "type": "text",
                        "text": "Analyze this earnings call transcript and return the structured JSON concall summary. Return only the JSON object."
                    }
                ]
            }]

        # For DOCX / TXT: extract text first
        elif ext in ("docx", "doc"):
            text = extract_text_from_docx(file_bytes)
            if len(text.strip()) < 50:
                raise HTTPException(status_code=400, detail="Document appears empty or unreadable.")
            doc_text = text[:150000] + "\n[TRUNCATED]" if len(text) > 150000 else text
            messages = [{"role": "user", "content": f"Analyze this earnings call transcript and return the structured JSON concall summary.\n\nTRANSCRIPT:\n---\n{doc_text}\n---\n\nReturn only the JSON object."}]

        elif ext == "txt":
            text = file_bytes.decode("utf-8", errors="ignore")
            if len(text.strip()) < 50:
                raise HTTPException(status_code=400, detail="File appears empty.")
            doc_text = text[:150000] + "\n[TRUNCATED]" if len(text) > 150000 else text
            messages = [{"role": "user", "content": f"Analyze this earnings call transcript and return the structured JSON concall summary.\n\nTRANSCRIPT:\n---\n{doc_text}\n---\n\nReturn only the JSON object."}]

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")

    # Call Claude
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            messages=messages
        )
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=500, detail="Server API key is invalid. Contact the portal administrator.")
    except anthropic.RateLimitError:
        raise HTTPException(status_code=429, detail="Rate limit reached. Please try again in a moment.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

    # Parse response
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Model returned malformed response. Please retry.")

    return JSONResponse(content={
        "status": "success",
        "filename": filename,
        "analysis": result
    })


# Serve static files (must be after routes)
app.mount("/static", StaticFiles(directory="static"), name="static")
