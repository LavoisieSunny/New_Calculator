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
    "You are an expert legal assistant specializing in Motor Accident Claims Tribunal (MACT) appeals in India. "
    "Your task is to read the grounds of appeal and the relief claimed (prayer) and generate a concise, "
    "professional summary in English.\n"
    "Focus on:\n"
    "1. The core grounds raised by the appellant (e.g., liability disputation, quantum enhancement, negligence, multiplier/interest dispute).\n"
    "2. The specific prayer/relief sought (e.g., enhancement of compensation, setting aside the award, exoneration, reduction).\n"
    "Keep it generalizable and objective, avoiding any hardcoded assumptions. Write in clean, professional legal English."
)

APPEAL_SUMMARY_USER_PROMPT = (
    "Grounds Section Text:\n{grounds_text}\n\n"
    "Relief/Prayer Section Text:\n{relief_text}\n\n"
    "Generate a concise, professional summary (1-2 paragraphs) of the grounds of appeal and the relief claimed."
)

