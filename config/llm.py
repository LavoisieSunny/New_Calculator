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
    "and produce a comprehensive, clean, synthesized legal summary.\n\n"
    "CRITICAL RULES:\n"
    "1. DO NOT copy-paste raw OCR text, noise, copying stamps, limitation period calculations, or verbatim garbled sentences.\n"
    "2. SYNTHESIZE the Grounds of Appeal into around 4 to 5 distinct, clear 1-2 sentence legal bullet points (e.g. disputing liability/insurance policy validity, quantum assessment, income/multiplier, negligence, interest rate).\n"
    "3. SYNTHESIZE the Relief/Prayer into around 2 to 3 distinct, specific bullet points (e.g. seeking total exoneration/setting aside of award, enhancement of compensation by specific amount, grant of 9% interest rate).\n"
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
    '    "Synthesized Ground 1 (e.g. liability dispute)",\n'
    '    "Synthesized Ground 2 (e.g. policy forgery/validity)",\n'
    '    "Synthesized Ground 3 (e.g. quantum/multiplier dispute)",\n'
    '    "Synthesized Ground 4 (e.g. negligence/contributory negligence)",\n'
    '    "Synthesized Ground 5 (e.g. interest rate or procedural error)"\n'
    '  ],\n'
    '  "relief_sought": [\n'
    '    "Synthesized Relief 1 (e.g. main prayer - setting aside award / exoneration)",\n'
    '    "Synthesized Relief 2 (e.g. monetary enhancement / liability shift)",\n'
    '    "Synthesized Relief 3 (e.g. interest rate or costs requested)"\n'
    '  ],\n'
    '  "key_figures_cited": []\n'
    "}}\n"
)



