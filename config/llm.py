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
LLM_SUMMARY_TEMPERATURE = float(os.getenv("LLM_SUMMARY_TEMPERATURE", "0.0"))

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
# TRIAL COURT TRANSLATION (Hindi/mixed -> legal English)
# ======================================================
LLM_TRANSLATION_MODEL_NAME = os.getenv("LLM_TRANSLATION_MODEL_NAME", LLM_MODEL_NAME)
LLM_TRANSLATION_TEMPERATURE = float(os.getenv("LLM_TRANSLATION_TEMPERATURE", "0.0"))

TRIAL_COURT_TRANSLATION_SYSTEM_INSTRUCTION = (
    "You are a certified Hindi-to-English legal translator working on Indian Motor "
    "Accident Claims Tribunal (MACT) records.\n"
    "CRITICAL RULES:\n"
    "1. Translate the given Hindi/mixed-script legal text into precise, literal legal English.\n"
    "2. Preserve every factual detail exactly: injuries, body parts, amounts, percentages, "
    "dates, names, section numbers. Never drop, merge, or generalize a fact.\n"
    "3. Do NOT summarize, shorten, or comment. This is a translation, not a summary.\n"
    "4. If a word or phrase is ambiguous, translate literally rather than guessing a modern "
    "equivalent.\n"
    "5. Output strictly valid JSON matching the schema, nothing else."
)

TRIAL_COURT_TRANSLATION_USER_PROMPT = (
    "Trial Court Issues & Findings (वादप्रश्न):\n{issues_text}\n\n"
    "Trial Court Operative Award (अधिनिर्णय):\n{award_text}\n\n"
    "Return ONLY valid JSON matching this schema exactly:\n"
    "{{\n"
    '  "issues_en": "full literal English translation of the issues & findings text",\n'
    '  "award_en": "full literal English translation of the operative award text"\n'
    "}}\n"
)

# ======================================================
# CLAIM EXTRACTION (generic -- injury, death, vehicle damage, income, etc.)
# ======================================================
LLM_CLAIM_EXTRACTION_MODEL_NAME = os.getenv("LLM_CLAIM_EXTRACTION_MODEL_NAME", LLM_MODEL_NAME)
LLM_CLAIM_EXTRACTION_TEMPERATURE = float(os.getenv("LLM_CLAIM_EXTRACTION_TEMPERATURE", "0.0"))

CLAIM_EXTRACTION_SYSTEM_INSTRUCTION = (
    "You extract discrete, checkable factual claims from Indian MACT/High Court appeal text.\n"
    "A 'claim' is any specific factual assertion that could be verified or contradicted by "
    "another document -- an injury or body part, a disability percentage, a cause of death, "
    "a claimed monthly income, a vehicle damage/total-loss assertion, a dependency figure, "
    "a hospital admission, or a specific date/amount tied to a factual (not legal-argument) point.\n"
    "Do NOT extract legal arguments, prayer requests, or procedural points (e.g. 'interest rate "
    "was wrongly applied' is a legal argument, NOT a factual claim; 'claimant lost her left ear' IS one).\n"
    "For each claim, assign one category: 'injury', 'death', 'vehicle_damage', 'income', "
    "'disability', 'dependency', 'other'.\n"
    "Output strictly valid JSON matching the schema, nothing else."
)

CLAIM_EXTRACTION_USER_PROMPT = (
    "Case type: {case_type}\n"
    "Source label: {source_label}\n\n"
    "Text:\n{text}\n\n"
    "Return ONLY valid JSON matching this schema exactly:\n"
    "{{\n"
    '  "claims": [\n'
    '    {{"claim": "short canonical description, e.g. \'left ear amputation\'", '
    '"category": "injury", "text_span": "short exact quote/paraphrase this was drawn from"}}\n'
    '  ]\n'
    "}}\n"
    'If there are no checkable factual claims, return {{"claims": []}}.'
)


# ======================================================
# FINAL JUDICIAL SUMMARY ENGINE CONFIGURATIONS  (REPLACES old block)
# ======================================================
LLM_FINAL_SUMMARY_MODEL_NAME = os.getenv("LLM_FINAL_SUMMARY_MODEL_NAME", "deepseek-r1:14b")
LLM_FINAL_SUMMARY_TEMPERATURE = float(os.getenv("LLM_FINAL_SUMMARY_TEMPERATURE", "0.0"))

FINAL_JUDICIAL_SUMMARY_SYSTEM_INSTRUCTION = (
    "You are simulating how an experienced High Court judge reads a MACT appeal.\n"
    "You will be given: (1) the trial court's issues framed and findings (वादप्रश्न, already "
    "translated to English), (2) the trial court's operative award (अधिनिर्णय, already translated "
    "to English), (3) the High Court grounds of appeal, (4) the relief sought, and (5) Medical Evidence "
    "from hospital records (if any).\n\n"
    "CRITICAL RULES:\n"
    "1. Base every statement ONLY on the text given. Never invent names, amounts, or dates.\n"
    "2. For each issue where a HC ground actually challenges it, produce one issue-wise entry.\n"
    "3. Write likely_judicial_view as reasoned analysis, not a verdict of fact.\n"
    "4. Do not copy raw OCR text verbatim; synthesize in clear human legal English.\n"
    "5. You are also given a Candidate Fact-Check list -- factual claims an automated matcher "
    "found in the grounds/relief but could NOT locate in the translated trial court text. The "
    "matcher can miss paraphrases, so actually check each candidate against the full trial court "
    "text you were given:\n"
    "   - If it is genuinely absent, keep it in factual_discrepancies with a short judicial-style note.\n"
    "   - If you can actually find it (even paraphrased) in the trial court text, put its exact "
    "claim string into rejected_candidate_claims instead, and leave it OUT of factual_discrepancies.\n"
    "   - You may add a claim of your own to factual_discrepancies if you notice a genuine one the "
    "candidate list missed.\n"
    "6. If a Medical Evidence block is provided, compare it against the trial court's disability findings. "
    "Flag any conflicts (e.g. difference in disability percentage, body part injured, or treatment duration) "
    "as entries in the factual_discrepancies array.\n"
    "7. Output strictly valid JSON matching the schema, nothing else."
)

FINAL_JUDICIAL_SUMMARY_USER_PROMPT = (
    "Trial Court Issues & Findings (English translation):\n{issues_text}\n\n"
    "Trial Court Operative Award (English translation):\n{award_text}\n\n"
    "High Court Grounds of Appeal:\n{grounds_text}\n\n"
    "Relief Sought:\n{relief_text}\n\n"
    "Medical Evidence (from hospital records, if any):\n{medical_evidence_text}\n\n"
    "Candidate Fact-Check list (unverified -- review each against the text above):\n"
    "{candidate_discrepancies}\n\n"
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
    '  "probable_outcome": "enhancement" | "reduction" | "exoneration" | "upheld" | "not_determinable",\n'
    '  "factual_discrepancies": [\n'
    '    {{"claim": "...", "found_in_grounds": true, "found_in_trial_court": false, "note": "..."}}\n'
    '  ],\n'
    '  "rejected_candidate_claims": ["claim text you found was actually present"]\n'
    "}}\n"
)




