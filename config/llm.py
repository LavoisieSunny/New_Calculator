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



