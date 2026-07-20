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
    "and produce a clean, synthesized legal summary.\n\n"
    "CRITICAL RULES:\n"
    "1. DO NOT copy-paste raw OCR text, noise, copying stamps, limitation period calculations, or verbatim garbled sentences.\n"
    "2. SYNTHESIZE each ground into a clear, concise 1-2 sentence legal argument (e.g. 'Claims the insurance cover note was forged/manipulated to alter the policy validity period.').\n"
    "3. SYNTHESIZE the prayer/relief into clear, specific bullet points (e.g. 'Seeking total exoneration of insurer liability', 'Seeking enhancement of compensation by Rs. 2,00,000/-').\n"
    "4. Output strictly valid JSON matching the specified schema."
)

APPEAL_SUMMARY_USER_PROMPT = (
    "Grounds Section Text:\n{grounds_text}\n\n"
    "Relief/Prayer Section Text:\n{relief_text}\n\n"
    "Analyze the text above and return ONLY a valid JSON object with the following schema:\n"
    "{{\n"
    '  "case_overview": "A concise 2-3 sentence overview of the appeal and main dispute.",\n'
    '  "appeal_direction": "enhancement" | "reduction" | "exoneration" | "not_determinable",\n'
    '  "grounds_of_appeal": [\n'
    '    "Synthesized, clean bullet point for Ground 1",\n'
    '    "Synthesized, clean bullet point for Ground 2"\n'
    '  ],\n'
    '  "relief_sought": [\n'
    '    "Synthesized, clean bullet point for Relief 1"\n'
    '  ],\n'
    '  "key_figures_cited": []\n'
    "}}\n"
)


