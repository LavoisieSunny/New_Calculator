# config/llm.py
import os

# ======================================================
# LLM PROVIDER & API ENDPOINT CONFIGURATIONS
# ======================================================

# Provider options:
# 1. "gemini"    -> Google Generative AI API (Cloud)
# 2. "ollama"    -> Local Ollama Server (Offline)
# 3. "openai"    -> OpenAI Developer API
# 4. "custom"    -> Custom local model gateway (e.g. vLLM or local model server)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")

# Model identifier
# Gemini options: "gemini-1.5-flash", "gemini-2.5-flash"
# Ollama options: "qwen2.5:14b", "llama3", "mistral"
# OpenAI options: "gpt-4o-mini", "gpt-4o"
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "qwen2.5:14b")

# API Keys (Loaded from environment variable, or hardcoded for ease of development)
LLM_API_KEY = os.getenv("LLM_API_KEY", "")

# Base API address/endpoint for Ollama, OpenAI, or Custom servers.
# Gemini requests go directly to the official Google API address unless a custom endpoint is specified.
LLM_API_ENDPOINT = os.getenv("LLM_API_ENDPOINT", "http://localhost:11434")

# ======================================================
# APPEAL SUMMARY LLM CONFIGURATIONS
# ======================================================
LLM_SUMMARY_TEMPERATURE = float(os.getenv("LLM_SUMMARY_TEMPERATURE", "0.2"))

APPEAL_SUMMARY_SYSTEM_INSTRUCTION = (
    "You are an expert legal assistant specializing in Motor Accident Claims Tribunal (MACT) appeals in India.\n"
    "Your task is to analyze the grounds of appeal and relief/prayer text extracted from a judgment or memo of appeal, "
    "and produce a brief, clean, human-style synthesized legal summary.\n\n"
    "CRITICAL RULES:\n"
    "1. DO NOT copy-paste raw OCR text, verbatim court clauses, noise, copying stamps, limitation calculations, or garbled sentences.\n"
    "2. SYNTHESIZE the Grounds of Appeal into 3 to 4 distinct, concise, human-readable legal bullet points (e.g. disputing liability/insurance policy, income assessment, multiplier error, negligence, or interest rate).\n"
    "3. SYNTHESIZE the Relief/Prayer into 2 to 3 distinct, clear bullet points (e.g. seeking setting aside of award, monetary enhancement, or interest rate modification).\n"
    "4. Even if the text contains only a few points or raw fragments, rewrite them in clear human legal language.\n"
    "5. Output strictly valid JSON matching the specified schema."
)

APPEAL_SUMMARY_USER_PROMPT = (
    "Grounds Section Text:\n{grounds_text}\n\n"
    "Relief/Prayer Section Text:\n{relief_text}\n\n"
    "Analyze the text above and return ONLY a valid JSON object with the following schema:\n"
    "{{\n"
    '  "case_overview": "A concise 2-3 sentence human-readable overview of the appeal dispute.",\n'
    '  "appeal_direction": "enhancement" | "reduction" | "exoneration" | "not_determinable",\n'
    '  "grounds_of_appeal": [\n'
    '    "Human summary ground 1 (e.g. Challenged Tribunal findings on driver negligence)",\n'
    '    "Human summary ground 2 (e.g. Erroneous calculation of monthly income and future prospects)",\n'
    '    "Human summary ground 3 (e.g. Improper application of multiplier and non-pecuniary heads)",\n'
    '    "Human summary ground 4 (e.g. Dispute regarding insurance policy liability)"\n'
    '  ],\n'
    '  "relief_sought": [\n'
    '    "Human summary relief 1 (e.g. Enhancement of overall compensation award)",\n'
    '    "Human summary relief 2 (e.g. Award of 9% interest per annum from filing date)"\n'
    '  ],\n'
    '  "key_figures_cited": []\n'
    "}}\n"
)


# ======================================================
# FINAL JUDICIAL SUMMARY ENGINE CONFIGURATIONS
# ======================================================
LLM_FINAL_SUMMARY_MODEL_NAME = os.getenv("LLM_FINAL_SUMMARY_MODEL_NAME", LLM_MODEL_NAME)
LLM_FINAL_SUMMARY_TEMPERATURE = float(os.getenv("LLM_FINAL_SUMMARY_TEMPERATURE", "0.2"))

FINAL_JUDICIAL_SUMMARY_SYSTEM_INSTRUCTION = (
    "You are simulating how an experienced High Court judge reads a MACT appeal.\n"
    "You will be given: (1) the trial court's issues framed and findings (वादप्रश्न), "
    "(2) the trial court's operative award (अधिनिर्णय), "
    "(3) the High Court grounds of appeal, and (4) the relief sought.\n\n"
    "CRITICAL RULES:\n"
    "1. Base every statement ONLY on the text given. Never invent names, amounts, or dates.\n"
    "2. For each issue where a HC ground actually challenges it, produce one issue-wise entry.\n"
    "3. Write likely_judicial_view as reasoned analysis, not a verdict of fact.\n"
    "4. Do not copy raw OCR text verbatim; synthesize in clear human legal English.\n"
    "5. Output strictly valid JSON matching the schema, nothing else."
)

FINAL_JUDICIAL_SUMMARY_USER_PROMPT = (
    "Trial Court Issues & Findings (वादप्रश्न):\n{issues_text}\n\n"
    "Trial Court Operative Award (अधिनिर्णय):\n{award_text}\n\n"
    "High Court Grounds of Appeal:\n{grounds_text}\n\n"
    "Relief Sought:\n{relief_text}\n\n"
    "Return ONLY valid JSON matching this schema exactly:\n"
    "{{\n"
    '  "issue_wise_view": [\n'
    '    {{\n'
    '      "issue": "...",\n'
    '      "trial_court_finding": "...",\n'
    '      "hc_ground_challenge": "...",\n'
    '      "likely_judicial_view": "..."\n'
    '    }}\n'
    '  ],\n'
    '  "final_summary_points": ["...", "..."],\n'
    '  "probable_outcome": "enhancement" | "reduction" | "exoneration" | "upheld" | "not_determinable"\n'
    "}}\n"
)




