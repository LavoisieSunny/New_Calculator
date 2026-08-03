import re
import logging
from datetime import datetime
from rapidfuzz import fuzz

logger = logging.getLogger("ParserHeuristics")

# Configurable Target Field Constants for Bundled Claims
BUNDLED_DIET_TRANSPORT_TARGET_FIELD = "special_diet"
BUNDLED_FUTURE_TARGET_FIELD = "future_medical_expenses"
BUNDLED_TRANSPORT_ATTENDER_TARGET_FIELD = "attender_charges"
BUNDLED_TRIPLE_TARGET_FIELD = "attender_charges"



# Dynamic Section Keyword Definitions
HEADING_KEYWORDS = {
    "index_section": [
        "index", "description of documents", "annexure", "table of contents", "index sheet"
    ],
    "chronological_events_section": [
        "chronological events", "date of accident", "claim petition filed", "list of dates", "chronology",
        "part b", "part b-", "chronology of events", "part b- chronology", "dates and events",
        "sequence of events", "part b chronology"
    ],
    "memo_of_appeal_section": [
        "अपील का ज्ञापन", "अपील ज्ञापन", "अपील पत्र", "विविध अपील",
        "memo of appeal", "appeal memo",
        "miscellaneous appeal", "memorandum of appeal",
        "memoofappeal", "appealmemo", "miscellaneousappeal"
    ],
    "award_copy_section": [
        "copy of award", "compensation awarded", "total compensation", "award decree", "award is passed", "impugned award"
    ],
    "vakalatnama_section": [
        "vakalatnama", "vakalat", "power of attorney", "memo of appearance"
    ],
    "claimant_section": [
        "legal representatives", "parties to the", "cause title", "party details",
        "details of claimants", "details of petitioners", "claimant details",
        "petitioner details", "memo of parties", "name and description of the injured person"
    ],
    "accident_section": [
        "manner of accident", "details of accident", "occurrence of accident", "date of accident",
        "particulars of accident"
    ],
    "compensation_section": [
        "compensation", "quantum", "assessment of compensation", "heads of claim", "calculation",
        "non-fatal accident case"
    ],
    "relief_section": [
        "प्रार्थना", "याचना", "अनुतोष", "राहत की प्रार्थना", "अतः प्रार्थना है",
        "अतः सादर प्रार्थना है", "प्रार्थना पत्र",
        "relief", "prayer", "relief claimed", "prayer clause", "it is therefore prayed",
        "relief claimed in appeal", "relief claimed in appeal : prayer", "relief claimed in appeal/prayer",
        "relief claims in appeal", "relief claims", "reliefclaimedinappeal", "reliefclaimed", "prayerclause", "reliefclaims"
    ],
    "grounds_section": [
        "अपील के आधार", "आधार", "चुनौती के आधार", "आपत्ति के आधार",
        "grounds", "grounds of appeal", "grounds of objection", "grounds of challenge", "(viii) grounds of appeal", "grounds of appeal/objection",
        "groundsofappeal", "groundsofobjection", "groundsofchallenge"
    ],
    "facts_section": [
        "other relevant facts", "(vii) other relevant facts", "relevant facts",
        "अन्य सुसंगत तथ्य", "तथ्य", "प्रकरण के तथ्य",
        "otherrelevantfacts", "relevantfacts"
    ],
    "award_operative_section": [
        "अधिनिर्णय", "अवार्ड", "अधिकरण द्वारा पारित", "अधिकरण द्वारा पारित अधिनिर्णय",
        "operative part of award", "operative award", "final order", "award decree", "award_operative"
    ],
    "issues_findings_section": [
        "वाद प्रश्न", "वादप्रश्न", "निष्कर्ष", "निर्णयार्थ बिंदु",
        "issues and findings", "issues framed", "points for determination", "issues_findings"
    ]
}


# ======================================================
# FIELD ALIAS MAPPING FOR MACT TABULAR FORM EXTRACTION
# ======================================================

FIELD_LABEL_ALIASES = {
    "claimant_name": [
        "name of claimant", "claimant name", "name of the claimant",
        "name of injured", "injured name", "name of the injured",
        "name of victim", "petitioner name", "name of petitioner",
        "name of appellant", "appellant name", "injured person name", "name"
    ],
    "deceased_name": [
        "name of deceased", "deceased name", "name of the deceased",
        "deceased person name"
    ],
    "father_name": [
        "father name", "father's name", "husband name", "husband's name",
        "father/husband name", "father / husband name",
        "father or husband name", "guardian name"
    ],
    "age_deceased": [
        "age of deceased", "age of victim", "age at the time of accident", "age at accident"
    ],
    "age_claimant": [
        "age of claimant", "age of injured"
    ],
    "age": [
        "age"
    ],
    "date_of_birth": [
        "date of birth", "dob", "d.o.b", "born on", "birth date",
        "date of birth of claimant", "date of birth of deceased",
        "date of birth of injured"
    ],
    "date_of_accident": [
        "date of accident", "accident date", "date of occurrence",
        "date of mishap", "date of incident", "date of collision",
        "date of injury", "date of the accident"
    ],
    "place_of_accident": [
        "place of accident", "place of occurrence", "place of incident",
        "location of accident", "accident spot", "site of accident",
        "place of collision", "venue of accident"
    ],
    "occupation": [
        "occupation", "profession", "trade", "vocation", "employment",
        "nature of work", "working as", "employed as", "job"
    ],
    "monthly_income": [
        "monthly income", "monthly salary", "monthly wages", "income per month",
        "salary per month", "wages per month", "monthly earning",
        "net monthly income", "gross monthly income"
    ],
    "fir_number": [
        "fir no", "fir no.", "fir number", "f.i.r. no", "f.i.r. number",
        "first information report no", "crime no", "crime number",
        "cr. no", "cr case no", "police report no"
    ],
    "policy_number": [
        "policy no", "policy no.", "policy number", "insurance policy no",
        "policy of insurance", "policy bearing no", "insurance no",
        "insurance number", "cover note no", "cover note number"
    ],
    "vehicle_number": [
        "vehicle no", "vehicle no.", "vehicle number",
        "vehicle registration no", "reg. no", "reg. no.",
        "registration no", "registration no.", "registration number",
        "bearing reg no", "bearing no", "bearing registration no",
        "offending vehicle no", "accident vehicle no"
    ],
    "insurance_company": [
        "insurance company", "name of insurance company", "insurer",
        "insurer name", "insurance co", "name of insurer",
        "respondent insurance", "insured by"
    ],
    "marital_status": [
        "marital status", "matrimonial status"
    ],
    "dependents": [
        "no. of dependents", "number of dependents", "dependents",
        "no of dependants", "no. of dependants", "number of dependants",
        "total dependents"
    ],
    "permanent_disability": [
        "permanent disability", "disability percentage", "permanent disability percentage",
        "degree of disability", "extent of disability", "permanent partial disability",
        "partial permanent disability", "percentage of disability", "disability %",
        "disability percent", "permanent disablement", "degree of permanent disability",
        "functional disability", "physical disability"
    ],
    "medical_expenses": [
        "medical expenses", "medical exp", "medical bills", "hospital expenses",
        "hospital bills", "treatment expenses", "treatment cost", "medical cost",
        "hospitalisation expenses", "hospitalisation charges", "medical expenditure",
        "medical charges", "total medical expenses",
        # Petition form labels (as adjudged by tribunal)
        "amount of expenses on treatment", "expenses on treatment",
        "amount of medical expenses", "medical expenses on treatment",
        "treatment expenses as adjudged", "amount spent on treatment"
    ],
    "future_medical_expenses": [
        "future medical expenses", "future medical", "future treatment expenses",
        "future medical cost", "future medical charges", "future hospitalisation"
    ],
    "pain_and_suffering": [
        "pain and suffering", "pain & suffering", "pain and agony",
        "pain suffering and mental agony", "physical pain", "mental agony",
        "pain and mental agony", "pain agony and suffering",
        "physical and mental pain", "suffering",
        # Petition form labels
        "amount of general damages", "general damages",
        "amount of damages as general", "amount for pain",
        "amount for pain and suffering"
    ],
    "transportation": [
        "transportation", "transport charges", "conveyance charges",
        "travelling expenses", "travel expenses", "conveyance",
        "transport expenses", "travelling charges"
    ],
    "special_diet": [
        "special diet", "special nourishment", "nutritious diet",
        "extra nourishment", "diet charges", "nourishment charges",
        "nutritional expenses", "diet expenses", "food expenses"
    ],
    "attender_charges": [
        "attender charges", "attendant charges", "nursing charges",
        "nursing expenses", "attender fee", "attendant fee",
        "caretaker charges", "care taker charges", "attendant expenses",
        "nursing care charges", "attender"
    ],
    "loss_of_income": [
        "loss of income", "loss of income during treatment",
        "loss of earning", "loss of wages", "loss of salary",
        "loss of employment income", "income loss during treatment",
        "loss of pay", "loss of work income", "loss of earnings",
        # Petition form labels
        "amount of damages as loss of income", "amount of damages as loss",
        "loss of income awarded by the tribunal",
        # Hindi keywords
        "आय की हानि", "आय हानि", "उपार्जन की क्षति", "आय की क्षति",
        "इलाज के दौरान आय", "उपचार के दौरान आय की हानि",
        "भविष्य की आय", "भावी उपार्जन"
    ],
    # Petition form specific fields (fatal/non-fatal tabular format)
    "funeral_expenses": [
        "funeral expenses", "funeral charges", "last rites", "last rituals",
        "funeral rites", "cremation expenses", "burial expenses",
        "amount for last rituals", "amount for funeral", "last ritual expenses",
        "funeral and burial", "death rituals"
    ],
    "consortium": [
        "consortium", "loss of consortium", "loss of cohabitation",
        "amount for cohabitation", "amount for consortium",
        "spousal consortium", "parental consortium", "filial consortium",
        "loss of love and affection", "cohabitation amount"
    ],
    "loss_of_dependency": [
        "loss of dependency", "amount for dependency", "dependency amount",
        "annual loss of dependency", "loss of financial dependency",
        "dependency compensation", "amount for dependency"
    ],
    "loss_of_estate": [
        "loss of estate", "amount for loss of estate", "estate loss",
        "loss of estate amount", "loss of personal estate"
    ],
    "total_compensation": [
        "total compensation awarded", "total compensation awarded by the tribunal",
        "total compensation", "total award", "award amount",
        "total amount awarded", "compensation awarded", "total awarded",
        "rs.", "total compensation awarded by tribunal"
    ],
    # ---------------------------------------------------------------
    # HINDI KEYWORD MAPPINGS FOR MACT TRIBUNAL AWARD HEADS
    # Standard Hindi terms used in lower court (MACT) judgments
    # ---------------------------------------------------------------
    "pain_and_suffering_hindi": [
        "शारीरिक एवं मानसिक पीडा", "शारीरिक एवं मानसिक कष्ट",
        "शारीरिक पीडा", "मानसिक पीडा", "दर्द एवं पीड़ा",
        "शारीरिक एवं मानसिक आघात", "कष्ट एवं पीड़ा",
        "पीडा कष्ट एवं आघात", "शारीरिक तकलीफ"
    ],
    "medical_expenses_hindi": [
        "चिकित्सा व्यय", "चिकित्सीय व्यय", "इलाज व्यय",
        "उपचार व्यय", "इलाज पर खर्च", "चिकित्सा खर्च",
        "अस्पताल व्यय", "चिकित्सा पर व्यय", "इलाज में खर्च"
    ],
    "future_medical_expenses_hindi": [
        "भविष्य में चिकित्सा व्यय", "भावी चिकित्सा व्यय",
        "भविष्य का इलाज खर्च", "भविष्य वर्ती चिकित्सा",
        "आगामी चिकित्सा व्यय"
    ],
    "transportation_hindi": [
        "आवागमन", "परिवहन व्यय", "यातायात व्यय",
        "आने जाने का खर्च", "यात्रा व्यय", "आवागमन व्यय",
        "आवागमन एवं पोष्टिक आहार", "आवागमन पर व्यय"
    ],
    "special_diet_hindi": [
        "पोष्टिक आहार", "विशेष आहार", "पौष्टिक आहार",
        "विशिष्ट आहार", "आहार व्यय", "खान पान व्यय",
        "फल पोष्टिक आहार", "विशेष पोषण"
    ],
    "attender_charges_hindi": [
        "सहायक पर व्यय", "परिचारक व्यय", "सहायक व्यय",
        "देखभाल व्यय", "सेवक व्यय", "परिचर्या व्यय",
        "सहायक पर खर्च", "परिचारक पर व्यय"
    ],
    "permanent_disability_hindi": [
        "स्थायी नियोग्यता", "स्थाई निर्योग्यता", "स्थायी अपंगता",
        "स्थाई विकलांगता", "स्थायी अक्षमता", "नियोग्यता प्रतिशत",
        "विकलांगता प्रतिशत", "स्थाई नियोग्यता"
    ],
    "monthly_income_hindi": [
        "मासिक आय", "मासिक वेतन", "मासिक मजदूरी",
        "प्रतिमाह आय", "माहवारी आय", "मासिक उपार्जन",
        "मासिक आमदनी"
    ],
    "loss_of_amenities_hindi": [
        "सुख सुविधाओं की हानि", "जीवन सुविधा हानि",
        "भविष्य में आय हानि", "भविष्य वर्ती आय की हानि",
        "आनंद हानि", "जीवन का आनंद"
    ]
}

# Mapping Hindi-specific field keys back to canonical field names
HINDI_TO_CANONICAL = {
    "pain_and_suffering_hindi": "pain_and_suffering",
    "medical_expenses_hindi": "medical_expenses",
    "future_medical_expenses_hindi": "future_medical_expenses",
    "transportation_hindi": "transportation",
    "special_diet_hindi": "special_diet",
    "attender_charges_hindi": "attender_charges",
    "permanent_disability_hindi": "permanent_disability",
    "monthly_income_hindi": "monthly_income",
    "loss_of_amenities_hindi": "loss_of_income",
}


def parse_mact_tabular_form(text_lines):
    """
    Lightweight MACT Petition Form Parser.
    Scans for 'Label : Value' structured rows common in MACT petition tabular forms
    and maps recognized label variants to canonical field names via FIELD_LABEL_ALIASES.
    Returns dict of {canonical_field_name: raw_value_string}.
    No ML, no external calls — pure regex, O(n) on input.
    """
    # Build reverse lookup: alias_lower -> canonical_field_name
    alias_lookup = {}
    for canonical, aliases in FIELD_LABEL_ALIASES.items():
        # Resolve Hindi-specific keys to their canonical English field name
        resolved = HINDI_TO_CANONICAL.get(canonical, canonical)
        for alias in aliases:
            alias_lookup[alias.lower().strip()] = resolved

    results = {}
    # Extended regex to match both Latin and Devanagari script labels
    tabular_line_re = re.compile(
        r'^(?:\(?[0-9a-zA-Z]+\)?[\.\)\-\s]+)?'
        r'([A-Za-zऀ-ॿ][A-Za-z0-9ऀ-ॿ\s\./\(\)\-\&]+?)'
        r'\s*(?:[:|\-–—]\s*|\s{2,})'
        r'(.+)$'
    )

    full_text = "\n".join(text_lines) if isinstance(text_lines, list) else text_lines

    for line in full_text.split("\n"):
        line_stripped = line.strip()
        if not line_stripped or len(line_stripped) < 5:
            continue
        if line_stripped.startswith("--- PAGE"):
            continue

        m = tabular_line_re.match(line_stripped)
        if not m:
            continue

        label_raw = m.group(1).strip()
        value_raw = m.group(2).strip()

        if len(label_raw) < 3 or not value_raw:
            continue
        # reject matches where the "value" is really just a continuation word
        if re.match(r'^[a-z]', value_raw) and len(label_raw.split()) <= 1:
            continue
        if value_raw.lower() in {'nil', 'n/a', '-', '--', '---', 'na', '_', '__'}:
            continue
        if re.match(r'^[\-_=\.\s]+$', value_raw):
            continue
        # Reject if value looks like a timestamp (HH:MM:SS) or contains time component
        if re.search(r'\d{1,2}:\d{2}:\d{2}', value_raw):
            continue

        label_norm = re.sub(r'\s+', ' ', label_raw.lower()).strip(' .')

        # Exact alias match
        canonical = alias_lookup.get(label_norm)

        # Partial alias match (label contains alias or alias contains label)
        if not canonical:
            for alias, can in alias_lookup.items():
                if can == "date_of_birth":
                    valid_dob_phrases = ["date of birth", "dob", "d.o.b", "born on", "birth date"]
                    if not any(phrase in label_norm for phrase in valid_dob_phrases):
                        continue
                if alias in label_norm or label_norm in alias:
                    canonical = can
                    break

        # Hindi partial match — check if any Hindi keyword appears in the line
        if not canonical:
            line_lower = line_stripped.lower()
            for alias, can in alias_lookup.items():
                # For Hindi aliases (Devanagari), do substring match on original line
                if any(ord(c) >= 0x0900 and ord(c) <= 0x097F for c in alias):
                    if alias in line_stripped:
                        canonical = can
                        break

        if canonical and canonical not in results:
            results[canonical] = value_raw.strip()

    return results


def _is_predominantly_devanagari(text: str, threshold: float = 0.5) -> bool:
    """
    Returns True when more than `threshold` fraction of the alphabetic characters
    in `text` fall in the Devanagari Unicode block (U+0900–U+097F).
    Lines that exceed the threshold are considered Hindi and should be excluded
    from English-only section content used for autofill.
    """
    alpha_chars = [ch for ch in text if ch.isalpha()]
    if not alpha_chars:
        return False
    deva_count = sum(1 for ch in alpha_chars if '\u0900' <= ch <= '\u097F')
    return (deva_count / len(alpha_chars)) >= threshold


def clean_noisy_text(text_line):
    """
    Cleans OCR scanning noise, stray characters, and common digit typos (like letter O/o instead of 0).
    """
    cleaned = text_line.strip()
    
    # 1. Repair common OCR digit typos: 'O' or 'o' scanned instead of '0' inside numbers
    cleaned = re.sub(r'(?<=\d)[Oo](?=\d)', '0', cleaned) # O surrounded by digits
    cleaned = re.sub(r'(?<=\d)[Oo]$', '0', cleaned)     # O at the end of a number
    cleaned = re.sub(r'^[Oo](?=\d)', '0', cleaned)     # O at the start of a number
    
    # 2. Repair dates with O/o typos, e.g. "12-O4-1992" or "12-o4-1992"
    cleaned = re.sub(r'\b(\d{1,2})[-/\.][Oo](\d)[-/\.](\d{4})\b', r'\1-0\g<2>-\3', cleaned)
    cleaned = re.sub(r'\b(\d{1,2})[-/\.](\d)[Oo][-/\.](\d{4})\b', r'\1-\g<2>0-\3', cleaned)
    cleaned = re.sub(r'\b(\d{1,2})[-/\.][Oo][Oo][-/\.](\d{4})\b', r'\1-00-\g<2>', cleaned)
    cleaned = re.sub(r'\b[Oo](\d)[-/\.](\d{1,2})[-/\.](\d{4})\b', r'0\g<1>-\g<2>-\3', cleaned)
    
    # 3. Remove typical OCR vertical bars or bracket noise in numeric/date lines
    if any(kw in cleaned.lower() for kw in ["rs", "income", "salary", "disability", "age", "dob", "date"]):
        cleaned = re.sub(r'[\|\[\]\~\^\#\_]', '', cleaned).strip()
        
    return cleaned


def merge_ocr_lines_to_paragraphs(text_lines):
    """
    Cleans noisy lines, filters out boilerplate/registry noise,
    and merges multi-page paragraph continuations (where lines do not end in sentence terminals).
    """
    cleaned_lines = []
    
    # Procedural boilerplate filters
    boilerplate_patterns = [
        r'^\s*presented\s+on\s*[:\-]',
        r'^\s*presented\s+by\s*[:\-]',
        r'^\s*registry\s+notice',
        r'^\s*in\s+the\s+court\s+of\b',
        r'^\s*adjudication\s+sheet\b',
        r'^\s*advocates?\s+for\b',
        r'^\s*date\s+of\s+stamping\b',
        r'^\s*stamps?\b',
        r'^\s*office\s+use\s+only\b',
        r'^\s*certified\s+copy\b',
        r'^\s*read\s+by\s*:',
        r'^\s*compared\s+by\s*:',
        r'^\s*typed\s+by\s*:'
    ]
    
    for line in text_lines:
        cleaned = clean_noisy_text(line)
        if not cleaned:
            continue
            
        # Ignore obvious procedural boilerplate lines
        if any(re.search(pat, cleaned.lower()) for pat in boilerplate_patterns):
            continue
            
        cleaned_lines.append(cleaned)
        
    # Paragraph reconstruction (continuations)
    merged_blocks = []
    current_block = ""
    
    for line in cleaned_lines:
        if not current_block:
            current_block = line
            continue
            
        ends_with_terminal = current_block[-1] in ['.', '?', '!', ':']
        starts_with_heading = line.isupper() and len(line) > 5
        starts_with_bullet = bool(re.match(r'^\s*(?:\d+|[a-zA-Z])[\.\)\-\]]', line))
        starts_with_number = bool(re.match(r'^\s*(?:rs\.?|inr)?\s*\d', line, re.IGNORECASE))
        current_ends_numeric = bool(re.search(r'\d(?:\s*[\/\-]*)$', current_block.strip()))
        
        if not ends_with_terminal and not starts_with_heading and not starts_with_bullet and not starts_with_number and not current_ends_numeric:
            # Word hyphenation continuation check, e.g. "compen-" + "sation"
            if current_block.endswith('-'):
                current_block = current_block[:-1] + line
            else:
                current_block += " " + line
        else:
            merged_blocks.append(current_block)
            current_block = line
            
    if current_block:
        merged_blocks.append(current_block)
        
    return merged_blocks


def extract_section_block(merged_lines, start_keywords, stop_keywords):
    """
    Isolates a standard legal section block based on start and stop keywords.
    Captures lines from a start keyword until a stop keyword is found.
    """
    block_lines = []
    capturing = False
    
    for line in merged_lines:
        line_lower = line.lower()
        
        if not capturing:
            if any(re.search(rf'\b{re.escape(kw)}\b', line_lower) for kw in start_keywords):
                capturing = True
                block_lines.append(line)
                continue
                
        if capturing:
            if any(re.search(rf'\b{re.escape(kw)}\b', line_lower) for kw in stop_keywords):
                break
            block_lines.append(line)
            
    return "\n".join(block_lines) if block_lines else ""


def clean_person_name(raw: str) -> str:
    """
    Cleans a person name by:
    - Removing relationship fragments (S/o, W/o, D/o, C/o, son of, wife of, daughter of) followed by anything.
    - Stripping leading/trailing honorifics (Shri, Shrimati, Smt, Km, Kumari, Late, Late Shri, Mr, Mrs)
      with optional trailing commas/dots/spaces.
    - Stripping any residual leading/trailing punctuation and double spaces.
    """
    if not raw or not isinstance(raw, str):
        return ""
        
    name_str = raw.strip()
    
    # 1. Strip relationship fragments (S/o, W/o, D/o, C/o, son/daughter/wife of, husband of, care of) followed by anything.
    rel_pattern = r'[\s,\-\(\/]+(?:s/o|d/o|w/o|c/o|son of|daughter of|wife of|husband of|care of)\b.*$'
    name_str = re.sub(rel_pattern, '', name_str, flags=re.IGNORECASE)
    
    # Also handle cases where there is a direct S/o or W/o without preceding separators
    name_str = re.sub(r'\b(?:s/o|d/o|w/o|c/o|son of|daughter of|wife of|husband of|care of)\b.*$', '', name_str, flags=re.IGNORECASE)

    # 2. Loop to strip leading/trailing honorifics cleanly (e.g. "Late Shri," -> we strip both)
    # We do a while loop since they can be nested or sequential
    changed = True
    honorifics = [
        r'\blate\s+shri\b', r'\blate\b', r'\bshri\b', r'\bshrimati\b', r'\bsmt\b',
        r'\bkm\b', r'\bkumari\b', r'\bmr\b', r'\bmrs\b', r'\bsh\.?\b'
    ]
    
    while changed:
        before = name_str
        
        # Strip leading punctuation/spaces
        name_str = re.sub(r'^[\"\’\‘\“\”\s\.\,\-\/\|]+', '', name_str)
        # Strip trailing punctuation/spaces
        name_str = re.sub(r'[\"\’\‘\“\”\s\.\,\-\/\|]+$', '', name_str)
        
        # Strip leading honorifics
        for hon in honorifics:
            # Match word starting at beginning
            new_str = re.sub(r'^' + hon + r'\b\.?\s*,?\s*', '', name_str, flags=re.IGNORECASE)
            if new_str != name_str:
                name_str = new_str
                break
                
        # Strip trailing honorifics
        for hon in honorifics:
            new_str = re.sub(hon + r'\b\.?\s*,?\s*$', '', name_str, flags=re.IGNORECASE)
            if new_str != name_str:
                name_str = new_str
                break
                
        if name_str == before:
            changed = False

    # 3. Final punctuation strip and whitespace normalization
    name_str = re.sub(r'^[\"\’\‘\“\”\s\.\,\-\/\|]+|[\"\’\‘\“\”\s\.\,\-\/\|]+$', '', name_str)
    name_str = re.sub(r'\s+', ' ', name_str).strip()
    
    return name_str


def clean_legal_name(name_str):
    """
    Step 3 — Name Cleaning:
    Removes legal prefixes and filters out non-claimant legal entities.
    Applies Entity Contamination Prevention keywords.
    """
    if not name_str:
        return ""
        
    # Remove trailing relative pronouns, verbs, and common prepositions/conjunctions
    name_str = re.sub(r'\b(?:who|which|that|is|was|were|died|expired|in|on|at|by|for|of|and|the|a|an)\b.*$', '', name_str, flags=re.IGNORECASE)
    name_str = name_str.strip()
    
    # Ignore obvious non-person entities or metadata fields
    IGNORE_KEYWORDS = [
        "advocate", "counsel", "judge", "justice", "adv.", "appearing", "learned", "counsel", "advocate", "prosecutor", "amicus", "curiae",
        "insurance company", "insurance co", "citation", "referred case", 
        "cited case", "vakalatnama", "scc", "acj",
        "insurance", "insur", "general", "company", "ltd", "limited", "corp", "corporation",
        "is assessed", "assessed at", "monthly income", "income is", "rs.", "rs ", "inr", "per month", "per annum",
        "died in", "died on", "accident occurred", "occurred at", "took place", "working as", "employed as", "earning", "wages", "salary",
        "description", "particulars", "details of", "description of",
        "non-claimant", "non claimant", "owner", "driver",
        "appellant", "respondent", "versus", "vs", "petitioner", "claimant", "deceased", "injured",
        "citation", "judgment", "judgement", "appeal", "application", "petitions", "suit",
        "sarla verma", "pranay sethi", "national insurance", "oriental insurance", "new india assurance", 
        "united india", "challa bharathamma", "munna lal jain", "lata wadhwa", "reshma kumari",
        "sanjay verma", "delhi transport", "d.t.c", "upsrtc", "mpsrtc", "rsrtc", "corporation", "co-operative"
    ]
    name_lower = name_str.lower()
    if any(kw.lower() in name_lower for kw in IGNORE_KEYWORDS):
        return ""
        
    # Strictly reject any name containing inline versus/vs/v. to prevent case title contamination
    if any(kw in name_lower for kw in [" vs ", " vs. ", " versus ", " v. ", " v "]):
        return ""
        
    # Reject directly contaminated prefix lines to preserve strict backward compatibility with existing unit tests
    if name_lower.startswith("appellant ") or name_lower.startswith("respondent ") or name_lower.startswith("versus "):
        return ""
        
    # Clean the string by removing legal noise like "versus", "vs.", "appellant", "respondent"
    for vs_pattern in [r'\bversus\b', r'\bvs\b\.?', r'\bv\b\.?']:
        if re.search(vs_pattern, name_lower):
            parts = re.split(vs_pattern, name_str, flags=re.IGNORECASE)
            part1 = parts[0].strip()
            part2 = parts[1].strip() if len(parts) > 1 else ""
            
            # Check if part1 is an insurance company/corporate entity
            part1_lower = part1.lower()
            is_ins = any(kw in part1_lower for kw in ["insurance", "ins.", "co.", "ltd", "limited", "corp", "corporation"])
            
            if is_ins and part2:
                name_str = part2
            else:
                name_str = part1
            name_lower = name_str.lower()
            
    # Remove role suffixes/prefixes safely (including group markers)
    role_patterns = [
        r'\bappellants?\b\.?', r'\brespondents?\b\.?', r'\bclaimants?\b\.?', 
        r'\bpetitioners?\b\.?', r'\bvictims?\b\.?', r'\binjured\b\.?', 
        r'\bdeceased\b\.?', r'\boriginal petitioner\b\.?', r'\bo\.p\b\.?',
        r'\b(?:and|&)\s+others?\b\.?', r'\b(?:and|&)\s+ors\b\.?', 
        r'\b(?:and|&)\s+anr\b\.?', r'\b(?:and|&)\s+another\b\.?',
        r'\bothers?\b\.?', r'\bors\b\.?'
    ]
    for role_pat in role_patterns:
        name_str = re.sub(role_pat, '', name_str, flags=re.IGNORECASE).strip()

    # Strip whitespace and common noise characters
    name_str = name_str.strip().replace("|", "")
    name_str = re.sub(r'^[\"\’\‘\“\”\s\.\,\-\/\|]+|[\"\’\‘\“\”\s\.\,\-\/\|]+$', '', name_str)
    
    # Remove standard titles with case-insensitive word boundaries (optional dot included)
    prefixes = [r'\bshri\b\.?', r'\bsmt\b\.?', r'\bmr\b\.?', r'\bmrs\b\.?', r'\bkumari\b\.?', r'\blate\b\.?']
    for pref in prefixes:
        name_str = re.sub(pref, '', name_str, flags=re.IGNORECASE)
        
    # Remove relationship fragments if they leaked
    name_str = re.sub(r'[\s,\-]+(?:s/o|d/o|w/o|son of|daughter of|wife of).*$', '', name_str, flags=re.IGNORECASE)
    
    # Strip leading/trailing punctuation noise once more after prefix removal
    name_str = re.sub(r'^[\"\’\‘\“\”\s\.\,\-\/\|]+|[\"\’\‘\“\”\s\.\,\-\/\|]+$', '', name_str)

    # Normalize spaces
    name_str = re.sub(r'\s+', ' ', name_str).strip()
    
    # If the result is one of the legal roles themselves, or common particles, discard it
    if name_str.lower() in ["appellant", "respondent", "versus", "vs", "petitioner", "claimant", "deceased", "injured", "name", "father", "husband", "wife", "son", "daughter", "the", "a", "an", "of", "and", "to", "in", "for", "with", "on", "at", "by", "from", "is", "was", "were", "be", "been", "has", "have", "had", "are", "this", "that"]:
        return ""
        
    if len(name_str) < 3:
        return ""
        
    return name_str


OCCUPATION_NORMALIZATION = {
    "coolie": "Daily Wage Labourer",
    "laborer": "Daily Wage Labourer",
    "labourer": "Daily Wage Labourer",
    "daily wager": "Daily Wage Labourer",
    "daily wage": "Daily Wage Labourer",
    "agriculturist": "Farmer",
    "agriculture": "Farmer",
    "farming": "Farmer",
    "cultivator": "Farmer",
    "driver": "Driver",
    "housewife": "Housewife",
    "student": "Student",
    "teacher": "Teacher",
    "business": "Businessman/Self-Employed",
    "self employed": "Businessman/Self-Employed",
    "self-employed": "Businessman/Self-Employed",
    "shopkeeper": "Shopkeeper",
    "contractor": "Contractor",
}

def normalize_occupation(occ_str):
    if not occ_str:
        return ""
    occ_lower = occ_str.lower().strip()
    for key, normalized in OCCUPATION_NORMALIZATION.items():
        if key in occ_lower:
            return normalized
    return occ_str


def determine_name_role(name, text):
    """
    Module-level Claimant vs Non-claimant Role Resolution Engine.
    Uses character-distance proximity between a name and explicit role labels inside an HSL-tailored
    narrow semantic window to robustly assign 'claimant' vs 'non-claimant' vs 'unknown' roles.
    Supports suffix and prefix fallback matching to handle OCR and digital extraction noise.
    """
    if not name or len(name) < 3:
        return "unknown"
        
    def _exact_role(name_query):
        if not name_query or len(name_query) < 3:
            return "unknown"
        name_esc = re.escape(name_query)
        best_role = "unknown"
        min_dist = 999999
        
        # 1. Proximity scan inside an 80-character window
        for m in re.finditer(name_esc, text, re.IGNORECASE):
            def is_cause_title_line(idx):
                l_start = text.rfind('\n', 0, idx) + 1
                l_end = text.find('\n', idx)
                if l_end == -1:
                    l_end = len(text)
                line_str = text[l_start:l_end].lower()
                return any(vs in line_str for vs in [" versus ", " vs ", "-vs-", " v. ", " v/s ", " vs. "])

            if is_cause_title_line(m.start()):
                continue

            start = max(0, m.start() - 80)
            end = min(len(text), m.end() + 80)
            window = text[start:end].lower()
            
            indicators = [
                ("non-claimant", ["non-claimant", "non claimant", "owner", "driver", "insurance", "insur."]),
                ("claimant", ["claimant", "petitioner", "victim", "injured"])
            ]
            
            for role, keywords in indicators:
                for kw in keywords:
                    for kw_m in re.finditer(re.escape(kw), window):
                        if is_cause_title_line(start + kw_m.start()):
                            continue
                        # Guard: check if the matched keyword is separated by a versus pattern from the name
                        # inside the window. If so, it might belong to the opposing party in a cause title.
                        w_idx_start = min(m.start() - start, kw_m.start())
                        w_idx_end = max(m.end() - start, kw_m.end())
                        window_part = window[w_idx_start:w_idx_end]
                        if any(vs in window_part for vs in ["versus", "vs", "-vs-", " v. ", " v/s "]):
                            continue

                        name_offset = m.start() - start
                        kw_offset = kw_m.start()
                        dist = abs(kw_offset - name_offset)
                        
                        if dist < min_dist:
                            min_dist = dist
                            best_role = role
                            
        # 2. Line-level fallback for standalone declarations
        if best_role == "unknown":
            for line in text.split("\n"):
                line_lower = line.lower()
                if name_query.lower() in line_lower:
                    if any(vs in line_lower for vs in ["versus", "-vs-", " v/s ", " vs ", " v. "]):
                        continue
                    has_non_claimant = any(kw in line_lower for kw in ["non-claimant", "non claimant", "owner", "driver", "insurance", "insur."])
                    has_claimant = any(kw in line_lower for kw in ["claimant", "petitioner", "victim", "injured"])
                    if has_non_claimant and not has_claimant:
                        return "non-claimant"
                    if has_claimant and not has_non_claimant:
                        return "claimant"
                        
        return best_role

    # 1. Try exact match first
    role = _exact_role(name)
    if role != "unknown":
        return role

    # 2. Try partial token-based fallback (suffix and prefix matching)
    name_clean = re.sub(r'[^\w\s]', '', name)
    tokens = [t for t in name_clean.split() if len(t) >= 3]
    
    if len(tokens) >= 2:
        # Try matching the last 2 tokens (e.g. "Bai Baiga" for "Santo Bai Baiga")
        last_two = " ".join(tokens[-2:])
        role = _exact_role(last_two)
        if role != "unknown":
            logger.info(f"Resolved role for '{name}' as '{role}' using suffix match '{last_two}'")
            return role
            
        # Try matching the first 2 tokens (e.g. "Birendra Singh" or "Santo Bai")
        first_two = " ".join(tokens[:2])
        role = _exact_role(first_two)
        if role != "unknown":
            logger.info(f"Resolved role for '{name}' as '{role}' using prefix match '{first_two}'")
            return role

    # 3. Try unique single tokens (skipping extremely common last names / legal particles)
    for token in tokens:
        if token.lower() in ["singh", "devi", "kumar", "bai", "sharma", "verma", "yadav", "gupta", "lal", "prasad", "others", "vs", "versus"]:
            continue
        role = _exact_role(token)
        if role != "unknown":
            logger.info(f"Resolved role for '{name}' as '{role}' using unique token match '{token}'")
            return role

    return "unknown"


def extract_relationship_entities(text):
    """
    Step 4 — Relationship-Aware Entity Splitting:
    Intelligently splits "Claimant Name, S/o Father Name" into claimant_name and father_name,
    applying strict truncation boundaries on each component separately.
    Line-by-line execution prevents bleeding across paragraphs.
    """
    if not text:
        return None
        
    rel_patterns = [
        (r'(.*?)\b(?:s[\./\s]*o|son\s+of)\b[\s\.]*(?:shri|late)?\s*(.*)', "Son of"),
        (r'(.*?)\b(?:d[\./\s]*o|daughter\s+of)\b[\s\.]*(?:shri|smt|late)?\s*(.*)', "Daughter of"),
        (r'(.*?)\b(?:w[\./\s]*o|wife\s+of)\b[\s\.]*(?:shri|late)?\s*(.*)', "Wife of")
    ]
    
    lines = text.split('\n')
    for line in lines:
        line_strip = line.strip()
        if not line_strip:
            continue
            
        for pat, rel_type in rel_patterns:
            m = re.search(pat, line_strip, re.IGNORECASE)
            if m:
                c_part = m.group(1).strip()
                f_part = m.group(2).strip()
                
                # Strip typical claimant/petitioner label prefixes from the claimant part
                c_part = re.sub(r'^(?:the\s+)?(?:claimant\s+name|petitioner\s+name|name\s+of\s+injured|name\s+of\s+claimant|name\s+of\s+victim|claimant|petitioner|victim|injured|name)\s*[:\-–\s]+', '', c_part, flags=re.IGNORECASE)
                
                # Apply boundary truncation to avoid leaking trailing fields
                stop_labels = [
                    "date of birth", "dob", "d.o.b", "born on", "age", "aged",
                    "occupation", "employed as", "working as", "monthly income", "salary",
                    "income", "disability", "dependents", "address", "resident of", "marital status"
                ]
                
                # Truncate c_part at stop labels and comma
                for sl in stop_labels:
                    sl_match = re.search(r'\b' + re.escape(sl) + r'\b', c_part, re.IGNORECASE)
                    if sl_match:
                        c_part = c_part[:sl_match.start()]
                
                c_comma_pos = c_part.find(",")
                if c_comma_pos != -1:
                    c_part = c_part[:c_comma_pos]
                    
                # Apply boundary truncation to the father part specifically to avoid leaking trailing fields
                # 1. Truncate at comma
                comma_pos = f_part.find(",")
                if comma_pos != -1:
                    f_part = f_part[:comma_pos]
                    
                # 2. Truncate at Date pattern
                date_pos = re.search(r'\b\d{1,2}[-/\.]\d{1,2}[-/\.]\d{4}\b', f_part)
                if date_pos:
                    f_part = f_part[:date_pos.start()]
                    
                # 3. Truncate at stop labels
                for sl in stop_labels:
                    sl_match = re.search(r'\b' + re.escape(sl) + r'\b', f_part, re.IGNORECASE)
                    if sl_match:
                        f_part = f_part[:sl_match.start()]
                        
                c_clean = clean_legal_name(c_part)
                f_clean = clean_legal_name(f_part)
                
                if c_clean and f_clean:
                    # Validate that c_clean is NOT a non-claimant role in the claimant section!
                    role = determine_name_role(c_clean, text)
                    if role == "non-claimant":
                        logger.info(f"Relationship splitting rejected '{c_clean}' because role is resolved as non-claimant")
                        continue
                    return c_clean, rel_type, f_clean
                    
    return None
                
    return None


def validate_name_confidence(name, current_confidence):
    """
    Step 5 — Confidence Validation:
    Automatically reduces confidence to <= 0.3 if the name contains digit patterns,
    other field keywords, or punctuation overflow (e.g. >= 3 separators).
    """
    if not name:
        return current_confidence
        
    name_lower = name.lower()
    
    # 1. Check for bad keywords
    bad_keywords = ["date", "age", "income", "salary", "disability", "occupation", "dependents", "address", "non-claimant", "owner", "driver", "insurance", "respondent"]
    contains_bad_kw = any(kw in name_lower for kw in bad_keywords)
    
    # 2. Check for digits
    contains_digits = bool(re.search(r'\d', name))
    
    # 3. Check for punctuation overflow (>= 3 chars)
    punc_matches = re.findall(r'[.,:\-/\_\\]', name)
    overflow_punc = len(punc_matches) >= 3
    
    if contains_bad_kw or contains_digits or overflow_punc:
        logger.warning(f"Confidence validation failed for name '{name}' (bad kw: {contains_bad_kw}, digits: {contains_digits}, punc: {overflow_punc}). Dropping confidence.")
        return min(current_confidence, 0.30)
        
    return current_confidence


def parse_indian_rupee_value(text):
    """
    Parses and normalises Indian currency text, converting Lakhs, Crores, commas, and suffixes into float.
    E.g. "Rs. 1,50,000/-" -> 150000.0
         "1.5 Lakhs" -> 150000.0
    """
    if not text:
        return 0.0
        
    text = text.lower().strip()
    
    # Clean up standard rupee notations
    text = re.sub(r'[\brs\.?|inr|rupees?|\/\-]|\s+', '', text)
    
    # Check for Lakh/Lakhs
    lakh_match = re.search(r'([\d\.]+)\s*(?:lakhs?|lac|lacs)', text)
    if lakh_match:
        try:
            return float(lakh_match.group(1)) * 100000.0
        except ValueError:
            pass
            
    # Check for Crore/Crores
    crore_match = re.search(r'([\d\.]+)\s*(?:crores?|cr)', text)
    if crore_match:
        try:
            return float(crore_match.group(1)) * 10000000.0
        except ValueError:
            pass
            
    # Remove commas and extract numbers
    cleaned_num = re.sub(r'[^\d\.]', '', text)
    try:
        if cleaned_num:
            return float(cleaned_num)
    except ValueError:
        pass
        
    return 0.0


_VALID_HEADS = [
    "dependency", "consortium", "funeral", "estate", "pain", "medical", 
    "transport", "nourishment", "diet", "attender", "attendant", 
    "disability", "amenities", "earning", "structure", "litigation", 
    "miscellaneous", "marriage", "expectation", "love", "enjoyment", 
    "lumpsum", "spouse", "parental", "children", "wife", "mother", 
    "father", "husband", "brother", "sister", "income", "damages", 
    "general", "loss", "treatment", "expenses"
]


def is_valid_head(head_str):
    hl = head_str.lower()
    if len(head_str) <= 3:
        return False
    if not any(kw in hl for kw in _VALID_HEADS):
        return False
    reject_kws = ["total", "interest", "passed", "order", "judgment"]
    if any(kw in hl for kw in reject_kws):
        return False
    if "awarded" in hl and "awarded by" not in hl:
        return False
    return True


_CLAUSE_PATTERN = re.compile(
    r'(?:rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*/?-?\s+for\s+'
    r'([a-zA-Z][a-zA-Z\s&]{2,60}?)'
    r'(?=\s*,\s*(?:rs\.?|inr)|[.;]|$)',
    re.IGNORECASE
)


def parse_comma_separated_compensation_clauses(text: str) -> dict:
    """
    Handles the common MACT/HC template sentence:
    'Rs. X/- for <head>, Rs. Y/- for <head>, Rs. Z/- for <head>.'
    — a format parse_compensation_table's line-based pattern_single
    cannot match at all, because its head-capture group excludes
    commas and therefore cannot bridge between clauses. Returns
    {head.title(): amount} for every clause found, using the same
    is_valid_head() gate as the rest of the table so garbage clause
    fragments are rejected the same way.
    """
    found = {}
    if not text:
        return found
    for m in _CLAUSE_PATTERN.finditer(text):
        amount = parse_indian_rupee_value(m.group(1))
        head = re.sub(r'\s+', ' ', m.group(2)).strip()
        if amount > 0 and is_valid_head(head):
            found[head.title()] = amount
    return found


def parse_compensation_table(text):
    """
    Layer 3: Compensation Table Parser.
    Parses structured lists of compensation heads and amounts from text blocks.
    Supports multiline look-ahead pairing of split labels and values, and parenthetical cleaning.
    """
    if not text:
        return {}
        
    table = {}
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    
    cleaned_lines = []
    for line in lines:
        cleaned = re.sub(r'[\(\)]', ' ', line)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        cleaned_lines.append(cleaned)
        
    pattern_single = r'(?:\d+[\.\)\-]\s*)?([A-Za-z\s&\(\)/\-\’\‘\“\”]+)\s*(?:[:\-–]|\b\.?\s*rs\.?\b)\s*(?:rs\.?|inr)?\s*([\d,\.\s]+lakhs?|[\d,\.\-\/]+)\b'
    
    i = 0
    while i < len(cleaned_lines):
        line = cleaned_lines[i]
        
        m = re.search(pattern_single, line, re.IGNORECASE)
        if m:
            head = m.group(1).strip()
            head = re.sub(r'\s+', ' ', head).strip()
            if is_valid_head(head):
                val = parse_indian_rupee_value(m.group(2))
                if val > 0:
                    table[head.title()] = val
            i += 1
            continue
            
        has_letters = any(c.isalpha() for c in line)
        has_digits = any(c.isdigit() for c in line)
        
        if has_letters and not has_digits:
            j = i + 1
            found_val = None
            skipped_lines = []
            while j < len(cleaned_lines):
                next_line = cleaned_lines[j]
                next_has_letters = sum(1 for c in next_line if c.isalpha())
                next_has_digits = any(c.isdigit() for c in next_line)
                
                if next_has_letters > 10 and not next_has_digits:
                    if any(stop in next_line.lower() for stop in ["total", "interest"]):
                        break
                    skipped_lines.append(next_line)
                    j += 1
                    continue
                
                if next_has_digits and next_has_letters < 5:
                    num_match = re.search(r'(?:rs\.?|inr)?\s*([\d,]+(?:\/-)?)\b', next_line, re.IGNORECASE)
                    if num_match:
                        found_val = parse_indian_rupee_value(num_match.group(1))
                        break
                break
                
            if found_val is not None and found_val > 0:
                full_label = " ".join([line] + skipped_lines)
                full_label = re.sub(r'\s+', ' ', full_label).strip()
                if is_valid_head(full_label):
                    table[full_label.title()] = found_val
                i = j + 1
                continue
                
        i += 1
        
    clause_matches = parse_comma_separated_compensation_clauses(text)
    for head, val in clause_matches.items():
        if head not in table:
            table[head] = val
            
    return table


def fuzzy_match_heading(line, keywords):
    """Matches a line against a list of fuzzy keywords for heading detection."""
    # Remove list indicators / bullets like '1. ', 'A. ', 'I. ', 'a) ', 'i) ', '(VIII) ', '(A) ', etc.
    line_lower = re.sub(r'^\s*(?:\(|\[)?\s*(?:[ivxIVX]+|\d+|[a-zA-Z])\s*(?:\)|\]|[\.\-\)])\s*', '', line).strip().lower()
    for kw in keywords:
        kw_lower = kw.lower().strip()
        # 1. Exact match
        if kw_lower == line_lower:
            return True
        # 2. Strict substring match with length threshold to avoid matching inside paragraphs
        if kw_lower in line_lower and len(line_lower) < len(kw_lower) + 12:
            return True
        # 3. Fuzzy sequencing match
        words = kw_lower.split()
        if len(words) > 1:
            pattern = r'.*'.join(re.escape(w) for w in words)
            if re.search(r'^\s*' + pattern, line_lower) and len(line_lower) < len(kw_lower) + 15:
                return True
    return False


def classify_page_fallback(page_text, section_name):
    """Layout fallback classifier for page classification when headings are missing."""
    text_lower = page_text.lower()
    
    if section_name == "index_section":
        return any(w in text_lower for w in ["index", "description of documents", "annexure", "page no"])
        
    elif section_name == "chronological_events_section":
        dates = re.findall(r'\b\d{1,2}[-/\.]\d{1,2}[-/\.]\d{4}\b', page_text)
        return len(dates) >= 2 and any(w in text_lower for w in ["accident", "filed", "petition", "date"])
        
    elif section_name == "claimant_section":
        if any(w in text_lower for w in ["vakalatnama", "vakalath", "appoint", "advocate"]):
            return False
        has_rel = any(w in text_lower for w in ["s/o", "d/o", "w/o", "son of", "wife of"])
        # require something specifically about identifying parties, not just "versus"/"respondent"
        has_parties = any(w in text_lower for w in ["legal representatives", "cause title", "memo of parties", "petitioner details", "claimant details"])
        return has_rel or has_parties
        
    elif section_name == "vakalatnama_section":
        return any(w in text_lower for w in ["vakalatnama", "vakalath", "appoint", "advocate"])
        
    elif section_name == "accident_section":
        return any(w in text_lower for w in ["date of accident", "manner of accident", "accident took place"])
        
    elif section_name == "compensation_section" or section_name == "award_copy_section":
        comp_kws = ["dependency", "multiplier", "consortium", "funeral", "loss of", "pain and suffering", "medical expenses", "rs.", "compensation", "award", "awarded", "disability"]
        comp_hits = sum(1 for kw in comp_kws if kw in text_lower)
        return comp_hits >= 2
        
    elif section_name == "relief_section":
        return any(w in text_lower for w in ["prayer", "relief", "prayed for", "allow the appeal"])
        
    elif section_name == "grounds_section" or section_name == "memo_of_appeal_section":
        return any(w in text_lower for w in ["grounds of appeal", "grounds", "erred in", "failed to appreciate"])
        
    elif section_name == "facts_section":
        return any(w in text_lower for w in ["other relevant facts", "relevant facts", "सुसंगत तथ्य", "तथ्य", "case of", "facts of the case"])
        
    elif section_name == "award_operative_section":
        strong_aw_kws = [
            "अधिनिर्णय", "अवार्ड", "अधिकरण द्वारा पारित",
            "operative part of award", "operative award", "final order",
            "award decree", "compensation is awarded", "award is passed",
            "award passed by", "date of award",
        ]
        if any(kw in text_lower for kw in ["grounds of appeal", "memorandum of appeal", "memo of appeal"]):
            return False
        return sum(1 for kw in strong_aw_kws if kw in text_lower) >= 1
        
    elif section_name == "issues_findings_section":
        strong_iss_kws = [
            "वाद प्रश्न", "वादप्रश्न", "निर्णयार्थ बिंदु",
            "issues framed", "issues and findings", "issue no", "point for determination",
        ]
        if any(kw in text_lower for kw in ["grounds of appeal", "memorandum of appeal", "memo of appeal"]):
            return False
        return sum(1 for kw in strong_iss_kws if kw in text_lower) >= 1
        
    return False


def normalize_issues_table(raw_section_text: str) -> list:
    """
    Converts raw issues_findings_section text (pipe-joined OCR rows or markdown table
    from PP-StructureV3) into [{"issue": ..., "finding": ...}, ...].
    Falls back to returning the raw text as a single unstructured row if no clear tabular
    delimiter is found -- never raises, never fabricates rows.
    """
    if not raw_section_text or not raw_section_text.strip():
        return []
        
    rows = []
    lines = [line.strip().strip("|") for line in raw_section_text.splitlines() if line.strip()]
    for line in lines:
        cells = [c.strip() for c in re.split(r"\s*\|\s*", line) if c.strip()]
        if len(cells) >= 2:
            rows.append({"issue": cells[0], "finding": " | ".join(cells[1:])})
            
    if not rows and raw_section_text.strip():
        rows.append({"issue": "Trial Court Issues / Findings", "finding": raw_section_text.strip()})
        
    return rows



def classify_page_type(page_text, page_number):
    """
    Indian MACT & High Court Appeal Page Layout Classifier.
    Categorises a PDF page into:
    - scrutiny report
    - computer sheet
    - award copy
    - order sheet
    - appeal memo
    - chronology
    - vakalatnama
    - evidence
    - tribunal judgment
    - annexure
    - handwritten note
    """
    text_lower = page_text.lower()
    
    # 1. Scrutiny Report
    if any(w in text_lower for w in ["scrutiny report", "scrutiny sheet", "office report", "limitation period"]):
        return "scrutiny report"
        
    # 2. Computer Sheet
    if any(w in text_lower for w in ["computer sheet", "computer data sheet"]):
        return "computer sheet"
        
    # 3. Vakalatnama
    if any(w in text_lower for w in ["vakalatnama", "vakalath", "appoint", "power of attorney", "pleader"]):
        return "vakalatnama"
        
    # 4. Chronology
    if any(w in text_lower for w in ["chronology", "chronological", "date of accident", "date of award"]) and any(w in text_lower for w in ["events", "particulars"]):
        return "chronology"
        
    # 5. Appeal Memo
    if any(w in text_lower for w in ["memo of appeal", "miscellaneous appeal", "under section 173", "m.a. no."]):
        return "appeal memo"
        
    # 6. Order Sheet
    if any(w in text_lower for w in ["order sheet", "order-sheet", "proceeding"]):
        return "order sheet"
        
    # 7. Award Copy / Compensation Table
    if any(w in text_lower for w in ["loss of dependency", "multiplier", "funeral expenses", "loss of estate", "total compensation"]):
        return "award copy"
        
    # 8. Evidence
    if any(w in text_lower for w in ["deposition", "cross-examination", "examination-in-chief", "witness", "p.w.", "d.w."]):
        return "evidence"
        
    # 9. Annexure
    if any(w in text_lower for w in ["annexure", "exhibit", "certified copy", "fir copy", "post mortem"]):
        return "annexure"
        
    # 10. Tribunal Judgment / General Judgment Text
    if any(w in text_lower for w in ["judgment", "award", "tribunal", "claims tribunal"]):
        return "tribunal judgment"
        
    # Default to handwritten note if text density is extremely sparse (signaling handwritten notes/stamps/scrawls)
    clean_lines = [l for l in page_text.split("\n") if l.strip()]
    if len(clean_lines) < 3 or (sum(len(l) for l in clean_lines) / max(len(clean_lines), 1)) < 15:
        return "handwritten note"
        
    return "judgment text"


def clean_numeric_to_float_or_int(val, field_name):
    """
    Cleans raw strings containing numbers (e.g. 'Rs. 25,000/-', '40%', '28 years')
    and extracts a clean float or integer so that the browser does not reject
    them on type="number" inputs.
    """
    if val is None or val == "":
        return ""
    if isinstance(val, (int, float)):
        return val
        
    val_str = str(val).lower().strip()
    
    # 1. Check for Lakh/Lac
    lakh_match = re.search(r'([\d\.]+)\s*(?:lakhs?|lac|lacs)', val_str)
    if lakh_match:
        try:
            return float(lakh_match.group(1)) * 100000.0
        except ValueError:
            pass
            
    # 2. Check for Crore
    crore_match = re.search(r'([\d\.]+)\s*(?:crores?|cr)', val_str)
    if crore_match:
        try:
            return float(crore_match.group(1)) * 10000000.0
        except ValueError:
            pass

    # Remove commas
    val_str = val_str.replace(",", "")
    
    # 3. Extract first valid float/int match
    num_match = re.search(r'\d+\.?\d*', val_str)
    if num_match:
        extracted = num_match.group(0)
        try:
            if field_name in ["age", "dependents"]:
                return int(float(extracted))
            return float(extracted)
        except ValueError:
            pass
            
    return ""


# ======================================================
# ENHANCEMENT vs REDUCTION CLASSIFICATION
# ======================================================
# Determines whether the appeal is seeking an ENHANCEMENT (claimant wants
# more compensation) or a REDUCTION (insurer/respondent wants the award
# lowered or set aside), based on the Grounds of Appeal and the Prayer /
# Relief Claimed sections specifically — not the whole document — because
# those are the sections that state what is actually being asked of the
# court, as opposed to narrative/background sections that may merely
# describe the original award.

_ENHANCEMENT_PHRASES = [
    "be enhanced", "compensation be enhanced", "award be enhanced",
    "prays for enhancement", "prayer for enhancement", "seeking enhancement",
    "enhancement of compensation", "enhancement of the award",
    "amount be increased", "compensation be increased", "award be increased",
    "inadequate compensation", "award is inadequate", "compensation is inadequate",
    "grossly inadequate", "on the lower side", "is too low", "meagre compensation",
    "just and proper compensation", "adequate compensation be awarded",
    "enhance the appropriate compensation", "enhance the compensation", "enhance compensation",
    "enhancing", "less amount", "awarded less", "modify by enhancing",
    "proper compensation", "just compensation", "adequate compensation", "increase",
]

_REDUCTION_PHRASES = [
    "be reduced", "compensation be reduced", "award be reduced",
    "amount be reduced", "set aside the award", "award be set aside",
    "award be quashed", "exonerate", "exoneration",
    "excessive compensation", "award is excessive", "compensation is excessive",
    "on the higher side", "is too high", "liability be apportioned",
    "appeal be allowed and the award be modified", "award be modified",
    "set aside", "be set aside", "setaside", "dismiss the claim", 
    "not liable", "wrongly held liable", "contributory negligence", 
    "negligent of deceased", "quashed", "quash", "apportionment of liability",
    "liable to pay", "liability of the insurance", "liability of the appellant",
    "exonerate the insurance", "exonerating the insurance", "exonerate the appellant",
    "exonerated from liability", "reverse the finding", "erred in holding",
]

# Phrases that look like enhancement/reduction keywords but describe what
# the TRIBUNAL ALREADY DID, not what the appellant is asking for. If a
# matched phrase is preceded closely by one of these, we discount it.
_PAST_TENSE_GUARDS = [
    "tribunal enhanced", "tribunal correctly enhanced", "court enhanced",
    "tribunal reduced", "tribunal correctly reduced", "court reduced",
    "already enhanced", "already reduced", "had enhanced", "had reduced",
    "should be enhanced", "shall be enhanced", "should be increased", "shall be increased",
]

_ENHANCEMENT_PHRASES_HI = [
    "वृद्धि की जाये", "मुआवजा राशि में वृद्धि", "प्रतिकर राशि में वृद्धि",
    "क्षतिपूर्ति राशि बढ़ाई जाये", "राशि बढ़ाई जाये", "अपर्याप्त क्षतिपूर्ति",
    "अपर्याप्त मुआवजा", "अपर्याप्त प्रतिकर", "अत्यल्प क्षतिपूर्ति",
    "न्यायोचित एवं समुचित क्षतिपूर्ति", "उचित क्षतिपूर्ति दिलाई जाये",
    "अवार्ड बढ़ाया जाये", "राशि अपर्याप्त एवं कम है",
    "वृद्धि की जावे", "बढ़ाई जावे", "कम है", "अपर्याप्त है"
]

_REDUCTION_PHRASES_HI = [
    "कम की जाये", "राशि कम की जाये", "अवार्ड कम किया जाये",
    "अवार्ड अपास्त किया जाये", "निर्णय अपास्त किया जाये",
    "दायित्व से मुक्त किया जाये", "उन्मोचित किया जाये",
    "अत्यधिक क्षतिपूर्ति", "अत्यधिक मुआवजा", "राशि अधिक है",
    "अवार्ड में संशोधन किया जाये", "पत्रावली वापस भेजी जाये",
    "अपास्त किया जावे", "अपास्त किया जाये", "दायित्व से मुक्त", "अत्यधिक है"
]

_PAST_TENSE_GUARDS_HI = [
    "अधिकरण ने वृद्धि की", "अधिकरण द्वारा वृद्धि की गई",
    "अधिकरण ने कमी की", "पहले से ही बढ़ाया", "पहले से ही घटाया",
    "न्यायालय ने वृद्धि की"
]


def _score_enhancement_reduction(text):
    """
    Scans `text` for enhancement/reduction prayer-style phrases.
    Returns (verdict, confidence, matched_snippet) where verdict is one of
    "enhancement", "reduction", "unclear".
    Past-tense / narrative mentions (e.g. "the tribunal correctly enhanced
    the award") are discounted so they don't get mistaken for a live prayer.
    """
    if not text or not text.strip():
        return "unclear", 0.0, ""

    lowered = text.lower().replace('é', 'e')

    combined_enhancement = _ENHANCEMENT_PHRASES + _ENHANCEMENT_PHRASES_HI
    combined_reduction = _REDUCTION_PHRASES + _REDUCTION_PHRASES_HI
    combined_guards = _PAST_TENSE_GUARDS + _PAST_TENSE_GUARDS_HI

    def _matches(phrases):
        hits = []
        for phrase in phrases:
            idx = lowered.find(phrase)
            if idx == -1:
                continue
            window_start = max(0, idx - 45)
            window = lowered[window_start:idx]
            if any(guard in window for guard in combined_guards):
                continue  # discount: this is describing a past/completed act
            hits.append(phrase)
        return hits

    enhancement_hits = _matches(combined_enhancement)
    reduction_hits = _matches(combined_reduction)

    if enhancement_hits and not reduction_hits:
        confidence = min(0.95, 0.6 + 0.1 * len(enhancement_hits))
        snippet = _extract_snippet(text, enhancement_hits[0])
        return "enhancement", round(confidence, 2), snippet

    if reduction_hits and not enhancement_hits:
        confidence = min(0.95, 0.6 + 0.1 * len(reduction_hits))
        snippet = _extract_snippet(text, reduction_hits[0])
        return "reduction", round(confidence, 2), snippet

    if enhancement_hits and reduction_hits:
        # Both present in the same section — genuinely ambiguous at the
        # section level; let the caller's combiner logic decide.
        snippet = _extract_snippet(text, enhancement_hits[0])
        return "unclear", 0.3, snippet

    return "unclear", 0.0, ""


# Periods/abbreviations that commonly appear in Indian legal documents but
# do NOT mark the end of a sentence. Used by _extract_snippet() so it does
# not mistake "Rs." or a numbered clause marker ("1.", "B.") for a real
# sentence boundary when building a human-readable excerpt.
_NON_BOUNDARY_ABBREVIATIONS = [
    "rs", "no", "nos", "ms", "mr", "mrs", "dr", "smt", "shri",
    "sec", "art", "regn", "vol", "p", "pp", "co", "ltd", "u/s", "u/r",
    "vs", "versus", "ors", "etc",
    "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
    "a", "b", "c", "d", "e", "f", "g", "h",
]


def _is_real_boundary_text(text, period_idx):
    before = text[:period_idx]
    token_match = re.search(r'([A-Za-z0-9]+)$', before)
    if token_match:
        token = token_match.group(1).lower()
        if token in _NON_BOUNDARY_ABBREVIATIONS:
            return False
        if token.isdigit() and len(token) <= 2:
            return False  # numbered clause marker, e.g. "1." / "2."
    after_slice = text[period_idx + 1:period_idx + 4]
    if after_slice == "" or re.match(r'\s*[A-Z([0-9]', after_slice):
        return True
    return False


def _split_into_sentences_or_points(text):
    if not text:
        return []
    
    # Preprocess inline list items (e.g. "PRAYER 1." or "Rs. 2,00,000/-. 2.") to split them onto new lines
    text = re.sub(r'\s+(?=[0-9]{1,2}\.\s+)', '\n', text)
    text = re.sub(r'\s+(?=[A-Za-z]\.\s+)', '\n', text)
    text = re.sub(r'\s+(?=\([A-Za-z0-9]{1,2}\)\s+)', '\n', text)
    
    # First split by lines and construct list items intelligently
    lines = text.split('\n')
    points = []
    current_point = ""
    
    for line in lines:
        line = line.strip()
        if not line:
            if current_point:
                points.append(current_point)
                current_point = ""
            continue
        
        is_new_bullet = False
        if not current_point:
            is_new_bullet = True
        else:
            # Check if this line starts a new bullet/point (e.g. "1.", "A.", "(i)", bullet character, or follows a period)
            has_marker = re.match(r'^(?:[0-9]{1,2}|[A-Za-z]{1,2})\s*[\.\)]', line) or \
                         re.match(r'^\([0-9A-Za-z]{1,2}\)', line) or \
                         line.startswith(('•', '-', '*'))
            
            ends_with_boundary = current_point.endswith(('.', ';', '!', '?', '।'))
            
            if has_marker or ends_with_boundary:
                is_new_bullet = True
            elif line[0].isupper():
                # Conjunctions / prepositions / articles connector check
                last_word_match = re.search(r'\b(\w+)$', current_point)
                last_word = last_word_match.group(1).lower() if last_word_match else ""
                if last_word in ('and', 'or', 'of', 'to', 'the', 'a', 'in', 'on', 'with', 'for', 'at', 'by'):
                    is_new_bullet = False
                else:
                    is_new_bullet = True
        
        if is_new_bullet:
            if current_point:
                points.append(current_point)
            current_point = line
        else:
            current_point = current_point + " " + line
            
    if current_point:
        points.append(current_point)
        
    final_clauses = []
    for pt in points:
        boundary_positions = [0]
        for m in re.finditer(r'(?:[.;]\s+|।\s*)', pt):
            pos = m.start()
            if pt[pos] == '.' and not _is_real_boundary_text(pt, pos):
                continue
            boundary_positions.append(m.end())
        boundary_positions.append(len(pt))
        
        for i in range(len(boundary_positions) - 1):
            clause = pt[boundary_positions[i]:boundary_positions[i+1]].strip()
            if clause:
                clause = re.sub(r'\s+', ' ', clause)
                final_clauses.append(clause)
                
    return final_clauses


def _extract_matching_points(text, verdict_type):
    """
    Splits text into clauses/sentences and filters those that contain matching keywords
    for the given verdict_type ('enhancement' or 'reduction').
    """
    if not text:
        return []
    
    clauses = _split_into_sentences_or_points(text)
    matched_points = []
    
    combined_enhancement = _ENHANCEMENT_PHRASES + _ENHANCEMENT_PHRASES_HI
    combined_reduction = _REDUCTION_PHRASES + _REDUCTION_PHRASES_HI
    combined_guards = _PAST_TENSE_GUARDS + _PAST_TENSE_GUARDS_HI
    
    phrases = combined_enhancement if verdict_type == "enhancement" else combined_reduction
    
    for clause in clauses:
        clause_lower = clause.lower()
        # Filter out court fee lines, fee structures, or trivial formatting/metadata lines
        if any(kw in clause_lower for kw in [
            "court fee", "court-fee", "court fees", "affidavit", "c.c. :-", "c.c. :", "cc :-", "cc :",
            "interlocutory application", "interlocutory", "main case :-", "court fee of",
            "valuation of appeal", "valuation of the appeal", "appeal is valued", "fixed court fee",
            "court fee paid", "ad-valorem", "ad valorem", "court fee is paid", "power :-", "power :",
            "document :-", "document :", "advocate", "power of attorney", "vakalatnama"
        ]):
            continue
        if len(clause) <= 12:
            continue

        has_hit = False
        for phrase in phrases:
            idx = clause_lower.find(phrase)
            if idx != -1:
                # check past tense guard
                window_start = max(0, idx - 45)
                window = clause_lower[window_start:idx]
                if any(guard in window for guard in combined_guards):
                    continue
                has_hit = True
                break
        if has_hit:
            # Clean leading list markers like "A. ", "1. ", "(IX) " etc.
            cleaned = re.sub(r'^(?:[A-Za-z0-9]{1,2}\.|\([A-Za-z0-9]{1,2}\)|[•\-\*])\s*', '', clause).strip()
            if cleaned:
                # Capitalize first letter
                cleaned = cleaned[0].upper() + cleaned[1:]
                matched_points.append(cleaned)
                
    return matched_points


def _extract_all_points(text):
    """
    Splits text into clauses/sentences and returns all points, cleaned of leading markers.
    """
    if not text:
        return []
    
    clauses = _split_into_sentences_or_points(text)
    points = []
    
    for clause in clauses:
        # Clean leading list markers like "A. ", "1. ", "(IX) " etc.
        cleaned = re.sub(r'^(?:[A-Za-z0-9]{1,2}\.|\([A-Za-z0-9]{1,2}\)|[•\-\*])\s*', '', clause).strip()
        if cleaned:
            cleaned_lower = cleaned.lower()
            # Filter out court fee lines, fee structures, or trivial formatting/metadata lines
            if any(kw in cleaned_lower for kw in [
                "court fee", "court-fee", "court fees", "affidavit", "c.c. :-", "c.c. :", "cc :-", "cc :",
                "interlocutory application", "interlocutory", "main case :-", "court fee of",
                "valuation of appeal", "valuation of the appeal", "appeal is valued", "fixed court fee",
                "court fee paid", "ad-valorem", "ad valorem", "court fee is paid", "power :-", "power :",
                "document :-", "document :", "advocate", "power of attorney", "vakalatnama"
            ]):
                continue
            # Filter out duplicate lines or very short noise lines
            if len(cleaned) <= 12:
                continue
            # Capitalize first letter
            cleaned = cleaned[0].upper() + cleaned[1:]
            points.append(cleaned)
            
    return points


def _extract_snippet(text, matched_phrase, max_chars=320, min_chars=40):
    """
    Returns a complete, sentence-bound excerpt around the matched phrase
    for human review -- never cuts off mid-word or mid-sentence.

    Expands outward from the matched phrase to the nearest real sentence
    boundary on each side, while ignoring periods that belong to common
    legal abbreviations ("Rs.", "Sec.", "No.") or numbered/lettered clause
    markers ("1.", "B.", "(IX)") that are standard in Grounds of Appeal and
    Prayer/Relief Claimed sections, so a numbered list item is not mistaken
    for the end of the relevant sentence.

    Falls back to a word-boundary-safe window (never mid-word) if sentence
    segmentation isn't possible (e.g. OCR text with little punctuation) or
    produces an excessively long result.
    """
    if not text or not matched_phrase:
        return ""

    lowered = text.lower()
    idx = lowered.find(matched_phrase)
    if idx == -1:
        return ""

    match_end = idx + len(matched_phrase)

    boundary_positions = []
    for m in re.finditer(r'(?:[.;]\s+|\n|।\s*)', text):
        pos = m.start()
        if text[pos] == '.' and not _is_real_boundary_text(text, pos):
            continue
        boundary_positions.append(m.end())

    start = 0
    for pos in boundary_positions:
        if pos <= idx:
            start = pos
        else:
            break

    end = len(text)
    for pos in boundary_positions:
        if pos > match_end:
            end = pos
            break

    snippet = text[start:end].strip()

    # If the matched clause alone is too short to be useful context on its
    # own, pull in the next clause as well.
    if len(snippet) < min_chars:
        for pos in boundary_positions:
            if pos > end:
                end = pos
                break
        snippet = text[start:end].strip()

    if len(snippet) > max_chars:
        window_start = max(0, idx - max_chars // 2)
        window_end = min(len(text), match_end + max_chars // 2)
        while window_start > 0 and text[window_start] not in (' ', '\n'):
            window_start -= 1
        while window_end < len(text) and text[window_end] not in (' ', '\n'):
            window_end += 1
        snippet = text[window_start:window_end].strip()
        prefix = "…" if window_start > 0 else ""
        suffix = "…" if window_end < len(text) else ""
        return prefix + snippet + suffix

    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + snippet + suffix


def classify_enhancement_or_reduction(sections):
    """
    Classifies whether the case/appeal is seeking enhancement or reduction
    of compensation, based on:
      - grounds_section (falls back to memo_of_appeal_section text)
      - relief_section ("relief claimed in appeal" / prayer clause)

    Combiner rules:
      - Both sections agree                -> that verdict, confidence = avg
      - Only one section has a signal      -> that verdict, confidence slightly reduced
      - Sections disagree (conflict)       -> "not_determinable", both shown
      - Neither section has a signal       -> "not_determinable", no evidence

    Returns a dict with verdict, confidence, signals and bullet points.
    """
    memo_text = sections.get("memo_of_appeal_section", "")
    
    grounds_text = sections.get("grounds_section", "") or sections.get("facts_section", "") or ""
    if not grounds_text.strip():
        grounds_text = memo_text or ""
        
    relief_text = sections.get("relief_section", "") or ""
    if not relief_text.strip():
        relief_text = sections.get("facts_section", "") or memo_text or ""

    if not grounds_text.strip():
        grounds_text = sections.get("raw_ocr", "")
    if not relief_text.strip():
        relief_text = sections.get("raw_ocr", "")

    # If the relief section was explicitly found, it contains the main prayer at the beginning.
    # We truncate it to 4000 characters to prevent false positive matching on calculations/citations
    # in the appended tribunal award.
    if sections.get("relief_section") and len(relief_text) > 4000:
        relief_text = relief_text[:4000]

    # Add debug logging of raw texts
    logger.info(f"[DEBUG ENHANCEMENT SECTIONS] grounds_text len: {len(grounds_text)}, relief_text len: {len(relief_text)}")
    logger.info(f"[DEBUG ENHANCEMENT SECTIONS] grounds_text raw (first 300 chars): {repr(grounds_text[:300])}")
    logger.info(f"[DEBUG ENHANCEMENT SECTIONS] relief_text raw (first 300 chars): {repr(relief_text[:300])}")

    g_verdict, g_conf, g_snippet = _score_enhancement_reduction(grounds_text)
    r_verdict, r_conf, r_snippet = _score_enhancement_reduction(relief_text)

    grounds_signal = {"verdict": g_verdict, "confidence": g_conf, "snippet": g_snippet}
    relief_signal = {"verdict": r_verdict, "confidence": r_conf, "snippet": r_snippet}

    g_has_signal = g_verdict in ("enhancement", "reduction")
    r_has_signal = r_verdict in ("enhancement", "reduction")

    # Determine resolved verdict
    resolved_verdict = "not_determinable"
    resolved_conf = 0.0
    resolved_basis = "no_signal"

    if g_has_signal and r_has_signal:
        if g_verdict == r_verdict:
            resolved_verdict = g_verdict
            resolved_conf = round((g_conf + r_conf) / 2, 2)
            resolved_basis = "agreement"
        else:
            resolved_verdict = "not_determinable"
            resolved_conf = 0.0
            resolved_basis = "conflict"
    elif r_has_signal:  # relief/prayer clause is the authoritative ask when only one side has a signal
        resolved_verdict = r_verdict
        resolved_conf = round(r_conf * 0.9, 2)
        resolved_basis = "single_source"
    elif g_has_signal:
        resolved_verdict = g_verdict
        resolved_conf = round(g_conf * 0.85, 2)  # grounds alone is weaker evidence than relief alone
        resolved_basis = "single_source"

    # Extract detailed matching bullet points for each section individually based on its own signal/verdict
    raw_ocr = sections.get("raw_ocr", "")
    
    grounds_points = []
    if grounds_text and grounds_text != raw_ocr:
        all_pts = _extract_all_points(grounds_text)
        grounds_points = [p for p in all_pts if len(p) > 15 and not any(kw in p.lower() for kw in ["grounds of appeal", "grounds of objection", "grounds of challenge"])]
    elif g_has_signal:
        grounds_points = _extract_matching_points(grounds_text, g_verdict)
        if not grounds_points and g_snippet:
            grounds_points = [g_snippet.lstrip("…").rstrip("…").strip()]

    relief_points = []
    if relief_text and relief_text != raw_ocr:
        all_pts = _extract_all_points(relief_text)
        relief_points = [p for p in all_pts if len(p) > 15 and not any(kw in p.lower() for kw in ["relief claimed", "prayer clause", "prayer in appeal"])]
    elif r_has_signal:
        relief_points = _extract_matching_points(relief_text, r_verdict)
        if not relief_points and r_snippet:
            relief_points = [r_snippet.lstrip("…").rstrip("…").strip()]

    return {
        "verdict": resolved_verdict,
        "confidence": resolved_conf,
        "basis": resolved_basis,
        "grounds_signal": grounds_signal,
        "relief_signal": relief_signal,
        "grounds_points": grounds_points[:5],
        "relief_points": relief_points[:3],
    }


def format_suggestions_for_calculator(suggestions):
    """
    Clean Minimal Legal Calculator-Ready Output Formatter.
    Returns ONLY case_type, fields dictionary, total_compensation, and low_confidence_fields.
    Keeps raw values regardless of confidence to support partial extraction recovery,
    but tracks fields with under 70% confidence inside low_confidence_fields.
    """
    case_type = suggestions.get("case_type")
    confidence_scores = suggestions.get("confidence_scores", {})
    low_conf_fields = []

    def get_field_val(flat_key, target_score_key, default_val=""):
        score_obj = confidence_scores.get(target_score_key)
        
        # Get raw value from suggestions flat structure first
        raw_val = suggestions.get(flat_key)
        if raw_val is None:
            if flat_key == "loss_of_consortium":
                raw_val = suggestions.get("consortium")
            elif flat_key == "consortium":
                raw_val = suggestions.get("loss_of_consortium")
            elif flat_key == "loss_estate":
                raw_val = suggestions.get("loss_of_estate")
            elif flat_key == "permanent_disability":
                raw_val = suggestions.get("disability")
            elif flat_key == "disability":
                raw_val = suggestions.get("disability_percentage") or suggestions.get("permanent_disability") or suggestions.get("disability")
            elif flat_key == "medical_expenses":
                raw_val = suggestions.get("medical_expenses") or suggestions.get("medical_expense")
            elif flat_key == "future_medical_expenses":
                raw_val = suggestions.get("future_medical_expenses") or suggestions.get("future_medical_expense")
            elif flat_key == "pain_and_suffering":
                raw_val = suggestions.get("pain_and_suffering") or suggestions.get("pain_suffering")
            elif flat_key == "attender_charges":
                raw_val = suggestions.get("attender_charges") or suggestions.get("attendant_charges")
            elif flat_key == "loss_of_income":
                raw_val = suggestions.get("loss_of_income") or suggestions.get("loss_income") or suggestions.get("loss_of_earnings")
            elif flat_key == "injured_name" or flat_key == "deceased_name":
                raw_val = (
                    suggestions.get("name") or
                    suggestions.get("claimant_name") or
                    suggestions.get("injured_name") or
                    suggestions.get("deceased_name")
                )

        if raw_val is None:
            raw_val = default_val

        # Confidence Rule: track low confidence fields (< 70%) but never blank them!
        conf = 1.0
        if score_obj:
            conf = score_obj.get("confidence", 1.0)
            if conf > 1.0:
                conf = conf / 100.0
        else:
            conf = 1.0 if raw_val != "" else 0.0

        if conf < 0.70 and raw_val != "":
            low_conf_fields.append(flat_key)
            
        return raw_val

    claimant_name = suggestions.get("claimant_name") or ""
    rel_type = suggestions.get("claimant_relationship_type") or suggestions.get("claimant_relationship_to_deceased") or ""
    
    valid_relation_keywords = [
        "mother", "father", "wife", "widow", "husband", "son", "daughter",
        "brother", "sister", "parent", "sibling", "child", "spouse", "dependent"
    ]
    rel_lower = rel_type.lower()
    has_valid_rel = any(kw in rel_lower for kw in valid_relation_keywords)
    
    is_relation_unconfirmed = False
    if claimant_name:
        if has_valid_rel:
            rel_display = rel_type
            if "of" in rel_lower:
                if "deceased" not in rel_lower:
                    rel_display = f"{rel_type} deceased"
            else:
                rel_display = f"{rel_type} of deceased"
            claimant_rel_val = f"{claimant_name} — {rel_display}"
        else:
            claimant_rel_val = f"{claimant_name} — Relationship not found — please verify"
            is_relation_unconfirmed = True
    else:
        claimant_rel_val = ""

    raw_cons = clean_numeric_to_float_or_int(get_field_val("consortium", "consortium"), "consortium")
    raw_funeral = clean_numeric_to_float_or_int(get_field_val("funeral_expenses", "funeral_expenses"), "funeral_expenses")
    raw_estate = clean_numeric_to_float_or_int(get_field_val("loss_estate", "loss_estate"), "loss_estate")

    # Align values and confidences for death case conventional heads:
    cons_val = raw_cons
    funeral_val = raw_funeral
    estate_val = raw_estate

    if case_type == "death":
        if "confidence_scores" not in suggestions:
            suggestions["confidence_scores"] = {}
            
        if is_relation_unconfirmed:
            suggestions["confidence_scores"]["claimant_relationship_to_deceased"] = {"confidence": 0.30, "reason": "No explicit, verified relationship to deceased found in text"}
            suggestions["confidence_scores"]["claimant_relationship_type"] = {"confidence": 0.30, "reason": "No explicit, verified relationship to deceased found in text"}
            if "claimant_relationship_to_deceased" not in low_conf_fields:
                low_conf_fields.append("claimant_relationship_to_deceased")
            if "claimant_relationship_type" not in low_conf_fields:
                low_conf_fields.append("claimant_relationship_type")
        
        # Consortium
        if raw_cons not in ["", None, 0.0, 0] and raw_cons != 40000.0:
            cons_val = raw_cons
        else:
            cons_val = 40000.0
            suggestions["confidence_scores"]["consortium"] = {"confidence": 1.0, "reason": "Standard Pranay Sethi baseline default (known constant)"}
            if "consortium" in low_conf_fields:
                low_conf_fields.remove("consortium")
                
        # Funeral expenses
        if raw_funeral not in ["", None, 0.0, 0] and raw_funeral != 15000.0:
            funeral_val = raw_funeral
        else:
            funeral_val = 15000.0
            suggestions["confidence_scores"]["funeral_expenses"] = {"confidence": 1.0, "reason": "Standard Pranay Sethi baseline default (known constant)"}
            if "funeral_expenses" in low_conf_fields:
                low_conf_fields.remove("funeral_expenses")
                
        # Loss of estate
        if raw_estate not in ["", None, 0.0, 0] and raw_estate != 15000.0:
            estate_val = raw_estate
        else:
            estate_val = 15000.0
            suggestions["confidence_scores"]["loss_estate"] = {"confidence": 1.0, "reason": "Standard Pranay Sethi baseline default (known constant)"}
            if "loss_estate" in low_conf_fields:
                low_conf_fields.remove("loss_estate")

    fields = {}
    if case_type == "death":
        fields = {
            "deceased_name": get_field_val("deceased_name", "deceased_name"),
            "claimant_relationship_to_deceased": claimant_rel_val,
            "claimant_relationship_type": get_field_val("claimant_relationship_type", "claimant_relationship_type"),
            "father_name": get_field_val("father_name", "father_name"),
            "date_of_accident": get_field_val("date_of_accident", "date_of_accident"),
            "date_of_birth": get_field_val("date_of_birth", "date_of_birth"),
            "age": clean_numeric_to_float_or_int(get_field_val("age", "age"), "age"),
            "marital_status": get_field_val("marital_status", "marital_status", "married"),
            "monthly_income": clean_numeric_to_float_or_int(get_field_val("monthly_income", "monthly_income"), "monthly_income"),
            "future_prospect": clean_numeric_to_float_or_int(get_field_val("future_prospect", "future_prospect"), "future_prospect"),
            "future_type": get_field_val("future_type", "future_type", 2),
            "place_of_accident": get_field_val("place_of_accident", "place_of_accident"),
            "fir_number": get_field_val("fir_number", "fir_number"),
            "policy_number": get_field_val("policy_number", "policy_number"),
            "vehicle_number": get_field_val("vehicle_number", "vehicle_number"),
            "insurance_company": get_field_val("insurance_company", "insurance_company"),
            "dependents": clean_numeric_to_float_or_int(get_field_val("dependents", "dependents"), "dependents"),
            "consortium": cons_val,
            "funeral_expenses": funeral_val,
            "loss_estate": estate_val,
        }
    elif case_type == "injury":
        fields = {
            "injured_name": get_field_val("injured_name", "injured_name"),
            "father_name": get_field_val("father_name", "father_name"),
            "date_of_accident": get_field_val("date_of_accident", "date_of_accident"),
            "date_of_birth": get_field_val("date_of_birth", "date_of_birth"),
            "age": clean_numeric_to_float_or_int(get_field_val("age", "age"), "age"),
            "monthly_income": clean_numeric_to_float_or_int(get_field_val("monthly_income", "monthly_income"), "monthly_income"),
            "disability": clean_numeric_to_float_or_int(get_field_val("disability", "disability"), "disability"),
            "dependents": clean_numeric_to_float_or_int(get_field_val("dependents", "dependents"), "dependents"),
            "medical_expenses": clean_numeric_to_float_or_int(get_field_val("medical_expenses", "medical_expenses"), "medical_expenses"),
            "pain_and_suffering": clean_numeric_to_float_or_int(get_field_val("pain_and_suffering", "pain_and_suffering"), "pain_and_suffering"),
            "transportation": clean_numeric_to_float_or_int(get_field_val("transportation", "transportation"), "transportation"),
            "special_diet": clean_numeric_to_float_or_int(get_field_val("special_diet", "special_diet"), "special_diet"),
            "attender_charges": clean_numeric_to_float_or_int(get_field_val("attender_charges", "attender_charges"), "attender_charges"),
            "future_medical_expenses": clean_numeric_to_float_or_int(get_field_val("future_medical_expenses", "future_medical_expenses"), "future_medical_expenses"),
            "loss_of_income": clean_numeric_to_float_or_int(get_field_val("loss_of_income", "loss_of_income"), "loss_of_income"),
            "fir_number": get_field_val("fir_number", "fir_number"),
            "policy_number": get_field_val("policy_number", "policy_number"),
            "vehicle_number": get_field_val("vehicle_number", "vehicle_number"),
            "insurance_company": get_field_val("insurance_company", "insurance_company"),
            "place_of_accident": get_field_val("place_of_accident", "place_of_accident"),
        }
    else:
        # Ambiguous case: combine death and injury fields
        fields_death = {
            "deceased_name": get_field_val("deceased_name", "deceased_name"),
            "claimant_relationship_to_deceased": claimant_rel_val,
            "claimant_relationship_type": get_field_val("claimant_relationship_type", "claimant_relationship_type"),
            "father_name": get_field_val("father_name", "father_name"),
            "date_of_accident": get_field_val("date_of_accident", "date_of_accident"),
            "date_of_birth": get_field_val("date_of_birth", "date_of_birth"),
            "age": clean_numeric_to_float_or_int(get_field_val("age", "age"), "age"),
            "marital_status": get_field_val("marital_status", "marital_status", "married"),
            "monthly_income": clean_numeric_to_float_or_int(get_field_val("monthly_income", "monthly_income"), "monthly_income"),
            "future_prospect": clean_numeric_to_float_or_int(get_field_val("future_prospect", "future_prospect"), "future_prospect"),
            "future_type": get_field_val("future_type", "future_type", 2),
            "place_of_accident": get_field_val("place_of_accident", "place_of_accident"),
            "fir_number": get_field_val("fir_number", "fir_number"),
            "policy_number": get_field_val("policy_number", "policy_number"),
            "vehicle_number": get_field_val("vehicle_number", "vehicle_number"),
            "insurance_company": get_field_val("insurance_company", "insurance_company"),
            "dependents": clean_numeric_to_float_or_int(get_field_val("dependents", "dependents"), "dependents"),
            "consortium": clean_numeric_to_float_or_int(get_field_val("consortium", "consortium"), "consortium"),
            "funeral_expenses": clean_numeric_to_float_or_int(get_field_val("funeral_expenses", "funeral_expenses"), "funeral_expenses"),
            "loss_estate": clean_numeric_to_float_or_int(get_field_val("loss_estate", "loss_estate"), "loss_estate"),
        }
        fields_injury = {
            "injured_name": get_field_val("injured_name", "injured_name"),
            "father_name": get_field_val("father_name", "father_name"),
            "date_of_accident": get_field_val("date_of_accident", "date_of_accident"),
            "date_of_birth": get_field_val("date_of_birth", "date_of_birth"),
            "age": clean_numeric_to_float_or_int(get_field_val("age", "age"), "age"),
            "monthly_income": clean_numeric_to_float_or_int(get_field_val("monthly_income", "monthly_income"), "monthly_income"),
            "disability": clean_numeric_to_float_or_int(get_field_val("disability", "disability"), "disability"),
            "dependents": clean_numeric_to_float_or_int(get_field_val("dependents", "dependents"), "dependents"),
            "medical_expenses": clean_numeric_to_float_or_int(get_field_val("medical_expenses", "medical_expenses"), "medical_expenses"),
            "pain_and_suffering": clean_numeric_to_float_or_int(get_field_val("pain_and_suffering", "pain_and_suffering"), "pain_and_suffering"),
            "transportation": clean_numeric_to_float_or_int(get_field_val("transportation", "transportation"), "transportation"),
            "special_diet": clean_numeric_to_float_or_int(get_field_val("special_diet", "special_diet"), "special_diet"),
            "attender_charges": clean_numeric_to_float_or_int(get_field_val("attender_charges", "attender_charges"), "attender_charges"),
            "future_medical_expenses": clean_numeric_to_float_or_int(get_field_val("future_medical_expenses", "future_medical_expenses"), "future_medical_expenses"),
            "loss_of_income": clean_numeric_to_float_or_int(get_field_val("loss_of_income", "loss_of_income"), "loss_of_income"),
            "fir_number": get_field_val("fir_number", "fir_number"),
            "policy_number": get_field_val("policy_number", "policy_number"),
            "vehicle_number": get_field_val("vehicle_number", "vehicle_number"),
            "insurance_company": get_field_val("insurance_company", "insurance_company"),
            "place_of_accident": get_field_val("place_of_accident", "place_of_accident"),
        }
        fields.update(fields_death)
        fields.update(fields_injury)

    # Extract total compensation
    tc_score = confidence_scores.get("total_compensation", {})
    tc_conf = tc_score.get("confidence", 1.0)
    if tc_conf > 1.0:
        tc_conf /= 100.0
    
    total_comp = suggestions.get("total_compensation") or suggestions.get("award_amount") or ""
    if tc_conf < 0.70 and total_comp != "":
        low_conf_fields.append("total_compensation")

    case_classification = suggestions.get("case_classification") or {
        "verdict": "not_determinable",
        "confidence": 0.0,
        "grounds_signal": {"verdict": "unclear", "confidence": 0.0, "snippet": ""},
        "relief_signal": {"verdict": "unclear", "confidence": 0.0, "snippet": ""},
        "basis": "no_signal",
    }

    return {
        "case_type": case_type,
        "fields": fields,
        "total_compensation": total_comp,
        "low_confidence_fields": low_conf_fields,
        "case_classification": case_classification
    }


def segment_text_lines_into_pages(text_lines):
    """
    Splits a flat OCR line list (delimited by '--- PAGE N ---' marker lines,
    the convention used across this codebase) into the [{"page_number", "lines",
    "text"}, ...] structure that detect_document_sections()/detect_document_sections_with_fallback()
    need for their heading-position and per-page fallback scans.

    Passing pages=[] to those functions is NOT a safe "skip page-aware
    detection" shortcut -- both the primary heading pass and the keyword
    fallback pass iterate over `pages`, so an empty list silently disables
    ALL deterministic section detection and forces 100% reliance on a single
    LLM classification call with no backup. Always build real pages here
    before calling detect_document_sections_with_fallback.
    """
    pages = []
    current_page_num = 1
    current_page_lines = []

    for line in text_lines:
        line_strip = line.strip()
        if line_strip.startswith("--- PAGE"):
            if current_page_lines:
                pages.append({
                    "page_number": current_page_num,
                    "lines": current_page_lines,
                    "text": "\n".join(current_page_lines)
                })
            m = re.search(r'PAGE\s+(\d+)', line_strip, re.IGNORECASE)
            if m:
                current_page_num = int(m.group(1))
            current_page_lines = []
        else:
            current_page_lines.append(line)

    if current_page_lines or not pages:
        pages.append({
            "page_number": current_page_num,
            "lines": current_page_lines,
            "text": "\n".join(current_page_lines)
        })

    return pages


def detect_document_sections(full_text, pages):
    """
    Dynamically identifies sections of the document using semantic heading matching
    and layout fallbacks.
    """
    doc_lines = []
    for p in pages:
        p_num = p["page_number"]
        for line_idx, line in enumerate(p["lines"]):
            cleaned = clean_noisy_text(line)
            if cleaned:
                doc_lines.append({
                    "text": cleaned,
                    "page": p_num,
                    "line_idx": line_idx
                })
                
    # 1. Fuzzy Heading Detection
    detected_headers = []
    for idx, item in enumerate(doc_lines):
        line_text = item["text"]
        page_num = item["page"]
        
        if len(line_text) > 70:
            continue
            
        for sec_name, keywords in HEADING_KEYWORDS.items():
            if fuzzy_match_heading(line_text, keywords):
                detected_headers.append({
                    "section_name": sec_name,
                    "line_idx": idx,
                    "page": page_num
                })
                break
                
    # 2. Section Boundary Detection
    sections = {}
    total_lines = len(doc_lines)
    
    for k, match in enumerate(detected_headers):
        sec_name = match["section_name"]
        start_idx = match["line_idx"]
        start_page = match["page"]
        
        if k + 1 < len(detected_headers):
            next_match = detected_headers[k+1]
            next_start_idx = next_match["line_idx"]
            
            end_idx = next_start_idx - 1
            end_page = doc_lines[end_idx]["page"]
        else:
            end_page = pages[-1]["page_number"] if pages else start_page
            end_idx = total_lines - 1
            
        raw_candidate_lines = [doc_lines[idx]["text"] for idx in range(start_idx + 1, end_idx + 1)]
        section_is_hindi = _is_predominantly_devanagari("\n".join(raw_candidate_lines), threshold=0.15)
        content_lines = [
            line for line in raw_candidate_lines
            if section_is_hindi or not _is_predominantly_devanagari(line)
        ]
        content = "\n".join(content_lines)
        
        if sec_name not in sections:
            sections[sec_name] = {
                "section_name": sec_name,
                "start_page": start_page,
                "end_page": end_page,
                "content": content,
                "strong_match": True
            }
        else:
            existing = sections[sec_name]
            existing["start_page"] = min(existing["start_page"], start_page)
            existing["end_page"] = max(existing["end_page"], end_page)
            existing["content"] += "\n" + content
            
    # 3. Fallback Strategy for Missing Sections
    for sec_name in HEADING_KEYWORDS.keys():
        if sec_name not in sections:
            fallback_pages = []
            for p in pages:
                p_text = p["text"]
                if classify_page_fallback(p_text, sec_name):
                    fallback_pages.append(p)
                    
            if fallback_pages:
                start_p = fallback_pages[0]["page_number"]
                end_p = fallback_pages[-1]["page_number"]
                raw_fallback_lines = [
                    line for p in fallback_pages for line in p["text"].splitlines()
                ]
                section_is_hindi = _is_predominantly_devanagari("\n".join(raw_fallback_lines), threshold=0.15)
                content = "\n".join(
                    line for line in raw_fallback_lines
                    if section_is_hindi or not _is_predominantly_devanagari(line)
                )
                sections[sec_name] = {
                    "section_name": sec_name,
                    "start_page": start_p,
                    "end_page": end_p,
                    "content": content,
                    "strong_match": False
                }
                
    return sections


def detect_document_sections_with_fallback(full_text, pages, case_type=None):
    sections = detect_document_sections(full_text, pages)  # existing keyword pass
    missing_core = not sections.get("grounds_section") and not sections.get("award_operative_section")
    if missing_core:
        from backend.llm_client import classify_sections_via_llm  # new function
        sections = classify_sections_via_llm(full_text) or sections
    return sections


def find_exact_page(value, start_page, end_page, pages):
    """Finds the exact page number that contains a value within a page range."""
    if not value:
        return start_page
    val_str = str(value).lower().strip()
    for p in pages:
        p_num = p["page_number"]
        if start_page <= p_num <= end_page:
            if val_str in p["text"].lower():
                return p_num
    return start_page


def score_page_importance(page_text, page_num):
    """
    Computes an importance/confidence score for a page.
    Drastically suppresses priority if legal citation and precedent keywords are matched.
    """
    text_lower = page_text.lower()
    score = 0.5
    
    heading_kws = [
        "index", "chronological", "appeal", "award", "vakalatnama", "claimant", "accident",
        "compensation", "relief", "grounds", "prayer", "other relevant facts", "relevant facts",
        "(vii)", "(viii)", "(ix)", "(x)"
    ]
    if any(kw in text_lower for kw in heading_kws):
        score += 0.15
        
    if any(kw in text_lower for kw in ["form", "petition under", "s/o", "d/o", "w/o", "aged about"]):
        score += 0.20
        
    dates = re.findall(r'\b\d{1,2}[-/\.]\d{1,2}[-/\.]\d{4}\b', page_text)
    if len(dates) >= 2 and any(kw in text_lower for kw in ["accident", "filed", "passed"]):
        score += 0.20
        
    comp_kws = ["loss of dependency", "multiplier", "consortium", "funeral expenses", "medical expenses", "pain and suffering"]
    if sum(1 for kw in comp_kws if kw in text_lower) >= 2:
        score += 0.25
        
    # Legal Citation Suppression Rule
    citation_patterns = [
        r'\b\d{4}\s+(?:SCC|ACJ)\s+\d+\b',
        r'\(\d{4}\)\s+\d+\s+(?:SCC|ACJ)\s+\d+\b',
        r'\bvs\b',
        r'\bversus\b',
        r'\breported\s+in\b'
    ]
    has_citation = any(re.search(pat, page_text, re.IGNORECASE) for pat in citation_patterns)
    precedent_terms = ["precedent", "judgment", "ruling", "held in", "cited", "referred to", "supreme court", "high court"]
    precedent_count = sum(1 for term in precedent_terms if term in text_lower)
    
    if has_citation or precedent_count >= 3:
        score = 0.10 # Drastic suppression
        
    return min(1.0, max(0.05, round(score, 3)))


def parse_chronological_events(text):
    """
    DATE -> EVENT chronological parser.
    Parses events like:
    25.12.2021 -> Date of accident
    """
    events = {
        "date_of_accident": "",
        "claim_petition_date": "",
        "award_date": ""
    }
    date_pattern = r'\b(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{4})\b'
    lines = text.split("\n")
    for line in lines:
        m = re.search(date_pattern, line)
        if m:
            try:
                d_str = f"{int(m.group(1)):02d}-{int(m.group(2)):02d}-{m.group(3)}"
                event_text = line.replace(m.group(0), "").lower().strip()
                event_text = re.sub(r'^[\s\.\:\-\–\—\→\>\|\/\\\t\?]+|[\s\.\:\-\–\—\→\>\|\/\\\t\?]+$', '', event_text)
                
                if any(kw in event_text for kw in [
                    "accident", "collision", "crash", "incident", "occurrence",
                    "took place", "succumbed", "injured", "injury", "mishap", "met with"
                ]):
                    if not events["date_of_accident"]:
                        events["date_of_accident"] = d_str
                elif any(kw in event_text for kw in ["petition filed", "claim petition", "mcop filed", "m.c.o.p", "filed"]):
                    if not events["claim_petition_date"]:
                        events["claim_petition_date"] = d_str
                elif any(kw in event_text for kw in ["award passed", "judgment", "decree", "order", "passed", "disposed"]):
                    if not events["award_date"]:
                        events["award_date"] = d_str
            except ValueError:
                pass
    return events


def extract_last_currency_value(line_lower):
    """
    Extracts the last numeric value on the line that looks like a currency amount.
    Handles multiple values on a single line (like formula multipliers).

    Guard: date fragments like "13.10.2009" are stripped before scanning,
    so a line such as "Date from which interest is awarded : 13.10.2009"
    doesn't have its year (2009) misread as a rupee amount just because
    the line also contains the word "award(ed)".
    """
    cleaned = re.sub(r'\b\d{1,2}[\.\-/]\d{1,2}[\.\-/]\d{2,4}\b', ' ', line_lower)
    matches = re.findall(r'(?:rs\.?|inr|rupees)?\s*([\d,]{4,12}(?:\.\d+)?)\s*(?:rs\.?|inr|rupees|\/\-)?', cleaned)
    if matches:
        for m_val in reversed(matches):
            val = parse_indian_rupee_value(m_val)
            if val > 0:
                return val
    return 0.0


def extract_compensation_table_fields(section_content, case_type=None):
    """
    Extracts structured compensation fields strictly from the isolated compensation table area.
    Optimized for Table-First Extraction and strict role/pleading avoidance.
    """
    fields = {
        "monthly_income": None,
        "monthly_income_method": None,
        "future_prospect": None,
        "deduction": None,
        "annual_loss_dependency": None,
        "multiplier": None,
        "funeral_expenses": None,
        "consortium": None,
        "total_compensation": None
    }
    
    if not section_content:
        return fields
        
    lines = section_content.split("\n")
    for line in lines:
        line_lower = line.strip().lower()
        if not line_lower:
            continue
            
        # Avoid advocate arguments, cited values, claimant demands, or insurer objections
        avoid_kws = [
            "claimant claimed", "claimant's demand", "pleaded", "averred", "sought", "demanded",
            "advocate", "counsel", "contended", "argued", "submissions", "according to", "deposition of",
            "sarlavarma", "pranaysethi", "reported in", "scc", "acj", "versus", "appeal by", "insurance co",
            "deposit", "interest @", "rate of interest", "claim amount", "appeal amount", "precedent", "cited case", "judgment cited", "petition valuation"
        ]
        if any(kw in line_lower for kw in avoid_kws):
            continue

        val = extract_last_currency_value(line_lower)
        
        mult_match = re.search(r'\bmultiplier\b.*?\b(\d{1,2})\b', line_lower)
        if mult_match:
            fields["multiplier"] = int(mult_match.group(1))
            
        pros_pct_match = re.search(r'\bfuture\s+prospects?\b.*?\b(\d{1,2}(?:\.\d+)?)\s*%', line_lower)
        if pros_pct_match:
            fields["future_prospect"] = float(pros_pct_match.group(1))
            
        ded_pct_match = re.search(r'\bdeduction\b.*?\b(\d+(?:\.\d+)?)\s*(?:%|/|\b)', line_lower)
        if ded_pct_match:
            fields["deduction"] = float(ded_pct_match.group(1))
            
        if val > 0:
            is_monthly = "monthly" in line_lower and any(kw in line_lower for kw in ["income", "salary", "earnings", "wage", "notional"])
            is_annual = "annual" in line_lower and any(kw in line_lower for kw in ["income", "salary", "earnings", "wage", "notional"])
            if is_monthly:
                fields["monthly_income"] = val
                fields["monthly_income_method"] = "Compensation Table Extraction"
            elif is_annual:
                fields["monthly_income"] = round(val / 12.0, 2)
                fields["monthly_income_method"] = "Compensation Table Extraction (Annual->Monthly)"
            elif any(kw in line_lower for kw in ["loss of dependency", "annual loss", "dependency"]):
                fields["annual_loss_dependency"] = val
            elif any(kw in line_lower for kw in ["funeral", "last rites", "last rituals"]):
                # Guard: standard rate is Rs.15,000. Accept only if <=50000.
                if val <= 50000:
                    fields["funeral_expenses"] = val
            elif any(kw in line_lower for kw in ["consortium", "cohabitation"]):
                # Guard: reject aggregate tribunal totals (e.g. 2,20,000 for 5 claimants).
                # Per Pranay Sethi the per-person rate is Rs.40,000. Accept only if <=100000.
                if val <= 100000:
                    fields["consortium"] = val
            elif any(kw in line_lower for kw in ["total", "award", "awarded sum", "total compensation"]):
                # Ensure no false positives for claim/interest/petition valuation
                if not any(kw in line_lower for kw in [
                    "claim", "petition", "sought", "prayed", "valuation", "demand",
                    "interest", "date from which", "rate at which", "rate of interest",
                ]):
                    fields["total_compensation"] = val
                
    if case_type == "injury":
        for f in ["future_prospect", "deduction", "annual_loss_dependency", "multiplier", "funeral_expenses", "consortium"]:
            fields[f] = None
    return fields


def extract_conventional_heads_list(text):
    """
    Dedicated parser that looks for a sentence listing conventional head amounts and labels:
    "entitled to <amt1>, <amt2> and <amt3> ... on account of <label1>, <label2> and <label3> ... respectively"
    and maps them to consortium, estate_loss, and funeral_expenses by keyword matching.
    """
    results = {}
    if not text:
        return results
        
    text_lower = text.lower()
    
    # Find "entitled to"
    for m_ent in re.finditer(r'entitled\s+to', text_lower):
        start_pos = m_ent.start()
        end_pos = text_lower.find(".", start_pos)
        if end_pos == -1:
            end_pos = min(len(text_lower), start_pos + 400)
        else:
            end_pos = min(end_pos + 1, start_pos + 400)
            
        sentence = text[start_pos:end_pos]
        sentence_lower = sentence.lower()
        
        # Check if it has "respectively"
        if "respectively" not in sentence_lower:
            continue
            
        # Extract amounts in the sentence
        amounts = []
        for amt_match in re.finditer(r'\b(?:rs\.?|inr|हैं|%|₹)?\s*([\d,]{4,7})\b', sentence, re.IGNORECASE):
            val = parse_indian_rupee_value(amt_match.group(1))
            if 1980 <= val <= 2050:
                continue
            if val > 0:
                amounts.append((val, amt_match.start()))
                
        if len(amounts) == 3:
            has_cons = "consortium" in sentence_lower
            has_est = "estate" in sentence_lower
            has_fun = "funeral" in sentence_lower
            
            if has_cons and has_est and has_fun:
                pos_cons = sentence_lower.find("consortium")
                pos_est = sentence_lower.find("estate")
                pos_fun = sentence_lower.find("funeral")
                
                heads = sorted([
                    ("consortium", pos_cons),
                    ("estate_loss", pos_est),
                    ("funeral_expenses", pos_fun)
                ], key=lambda x: x[1])
                
                sorted_amounts = sorted(amounts, key=lambda x: x[1])
                
                temp_results = {}
                for i in range(3):
                    temp_results[heads[i][0]] = sorted_amounts[i][0]
                    
                return temp_results
                
    return results


def _score_award_context(text, match_start):
    """
    Evaluates the preceding context (~80 chars) of a candidate conventional head match.
    Prefers case-specific award context (score > 0) over general legal precedent statement context (score < 0).
    """
    start_pos = max(0, match_start - 150)
    preceding_context = text[start_pos:match_start].lower()
    
    score = 0
    # Positive indicator phrases (score +1 for each match)
    positives = ["entitled to", "awarded", "awards", "granted", "claimants are entitled"]
    for p in positives:
        if p in preceding_context:
            score += 1
            
    # Negative indicator phrases (score -1 for each match)
    negatives = [
        "held that", "namely", "prescribed", "as per pranay sethi", 
        "reasonable figures on conventional heads should be",
        "reasonable figures on conventional heads"
    ]
    for n in negatives:
        if n in preceding_context:
            score -= 1
            
    return score


def get_personal_deduction_pct(marital_status, dependents):
    """
    Computes the personal expense deduction percentage using standard Sarla Verma / Pranay Sethi bands.
    Lookup is driven by dependent count first, with marital status as tiebreaker/fallback.
    """
    status = str(marital_status).strip().lower() if marital_status else ""
    try:
        dep_cnt = int(dependents) if dependents is not None else 0
    except (ValueError, TypeError):
        dep_cnt = 0
        
    is_single = status in ("single", "bachelor", "unmarried", "b", "s")
    if is_single:
        if dep_cnt <= 1:
            return 0.50
        else:
            return 1.0 / 3.0
    else:
        if dep_cnt <= 3:
            return 1.0 / 3.0
        elif dep_cnt <= 6:
            return 0.25
        else:
            return 0.20


CLAIM_LANGUAGE_KEYWORDS = [
    "claim", "claiming", "claimed", "sought", "demand", "demanded", 
    "prayed", "prayer", "valuation", "valued at", "claim before the tribunal", 
    "appeal valued at"
]


def contextual_extract(patterns, sections, priority_list, type_cast=str, default_val=None, field_name=None, debug_info=None, pages=None, sections_metadata=None, page_importances=None):
    """
    Upgraded Contextual Entity Extraction with dynamic section priority and page-importance tracking.
    """
    STOP_LABELS = [
        "date of birth", "dob", "d.o.b", "born on",
        "age", "aged",
        "occupation", "employed as", "working as",
        "monthly income", "salary", "earning", "income",
        "disability", "permanent disability",
        "dependents", "no. of dependents",
        "address", "resident of",
        "marital status",
        "prayer", "relief",
        "award", "awarded",
        "s/o", "d/o", "w/o", "son of", "daughter of", "wife of"
    ]
    
    if debug_info is None:
        debug_info = {}
        
    is_scored_field = field_name in [
        "consortium", "funeral_expenses", "estate_loss", "loss_estate",
        "monthly_income", "annual_loss_dependency"
    ]
    candidates = []

    for sec_name, base_weight in priority_list:
        text = sections.get(sec_name, "")
        if not text:
            continue
            
        for pat in patterns:
            for m in re.finditer(pat, text, re.IGNORECASE | re.MULTILINE):
                if field_name == "total_compensation":
                    # Suppress matching claimed/prayer amounts as total compensation
                    start_pos = max(0, m.start() - 50)
                    pre_ctx = text[start_pos:m.start()].lower()
                    if any(kw in pre_ctx for kw in CLAIM_LANGUAGE_KEYWORDS):
                        continue
                elif field_name in ("monthly_income", "annual_loss_dependency"):
                    # Suppress matching claimed/prayer amounts for income fields
                    start_pos = max(0, m.start() - 80)
                    pre_ctx = text[start_pos:m.start()].lower()
                    if any(kw in pre_ctx for kw in CLAIM_LANGUAGE_KEYWORDS):
                        continue
                elif field_name in ("claimant_name", "deceased_name", "father_name"):
                    # Honorific-only patterns (\bsmt\b, \bshri\b, \bmr\b, \bmrs\b,
                    # \bkumari\b) have no role anchor, so they'll happily match a
                    # tribunal member's or judge's name -- e.g. "The name of the
                    # Member : Smt Krishna Paraste" -- instead of the actual party.
                    # Reject matches whose same-line context names a judicial
                    # officer/advocate rather than a claimant/appellant/respondent.
                    line_start = text.rfind('\n', 0, m.start()) + 1
                    line_ctx = text[line_start:m.start()].lower()
                    if any(kw in line_ctx for kw in [
                        "member", "judge", "justice", "coram", "presided", "presiding",
                        "decided by", "advocate", "counsel", "bench", "hon'ble", "honble",
                    ]):
                        continue
                matched_source = m.group(0)
                raw_val = m.group(1).strip()
                
                active_stop_labels = []
                for sl in STOP_LABELS:
                    if field_name == "father_name" and sl in ["s/o", "d/o", "w/o", "son of", "daughter of", "wife of"]:
                        continue
                    active_stop_labels.append(sl)
                    
                truncated_val = raw_val
                stop_token_triggered = "None (EOL/EOF)"
                
                is_text_field = (type_cast == str) and field_name in ["claimant_name", "deceased_name", "father_name", "occupation", "address"]
                
                if is_text_field:
                    comma_pos = truncated_val.find(",")
                    if comma_pos != -1:
                        truncated_val = truncated_val[:comma_pos]
                        stop_token_triggered = ", (comma)"
                        
                newline_pos = re.search(r'[\r\n]', truncated_val)
                if newline_pos:
                    truncated_val = truncated_val[:newline_pos.start()]
                    stop_token_triggered = "Newline boundary"
                    
                date_pos = re.search(r'\b\d{1,2}[-/\.]\d{1,2}[-/\.]\d{4}\b', truncated_val)
                if date_pos:
                    truncated_val = truncated_val[:date_pos.start()]
                    stop_token_triggered = f"Date pattern ({date_pos.group(0)})"
                    
                for sl in active_stop_labels:
                    sl_match = re.search(r'\b' + re.escape(sl) + r'\b', truncated_val, re.IGNORECASE)
                    if sl_match:
                        if sl_match.start() < len(truncated_val):
                            truncated_val = truncated_val[:sl_match.start()]
                            stop_token_triggered = f"Stop label '{sl}'"
                            
                if is_text_field:
                    num_meta_match = re.search(r'\b\d+\s*(?:years|yrs|percent|%|\b)', truncated_val, re.IGNORECASE)
                    if num_meta_match:
                        truncated_val = truncated_val[:num_meta_match.start()]
                        stop_token_triggered = f"Numeric metadata boundary ({num_meta_match.group(0)})"
                        
                final_val = re.sub(r'\s+', ' ', truncated_val).strip()
                if is_text_field:
                    final_val = clean_legal_name(final_val)
                    
                # Determine source page
                sec_meta = sections_metadata.get(sec_name, {}) if sections_metadata else {}
                start_p = sec_meta.get("start_page", 1)
                end_p = sec_meta.get("end_page", 1)
                matched_page = find_exact_page(final_val, start_p, end_p, pages) if pages else start_p
                
                # Base confidence score
                confidence = round(base_weight / 100.0, 2)
                
                # Boost confidence if the section is strongly matched
                if sec_meta.get("strong_match", False):
                    confidence = min(0.99, confidence + 0.15)
                    
                # Boost confidence for early pages
                if matched_page <= 3:
                    confidence = min(0.99, confidence + 0.10)
                else:
                    confidence = max(0.10, confidence - 0.15)
                    
                # Adjust confidence based on Page Importance / Suppression
                if page_importances and matched_page in page_importances:
                    page_importance = page_importances[matched_page]
                    if page_importance <= 0.15:
                        confidence = max(0.05, confidence - 0.40)
                    else:
                        confidence = min(0.99, confidence * (0.5 + 0.5 * page_importance))
                        
                if is_text_field:
                    confidence = validate_name_confidence(final_val, confidence)
                    
                valid_candidate = False
                val_to_store = None
                
                if type_cast == float:
                    val = parse_indian_rupee_value(final_val)
                    if val > 0:
                        valid_candidate = True
                        val_to_store = val
                elif type_cast == int:
                    digit_match = re.search(r'\d+', final_val)
                    if digit_match:
                        try:
                            val = int(digit_match.group(0))
                            valid_candidate = True
                            val_to_store = val
                        except ValueError:
                            pass
                else:
                    if len(final_val) > 2:
                        valid_candidate = True
                        val_to_store = final_val
                        
                if valid_candidate:
                    candidate_debug = {
                        "matched_source_text": matched_source.strip(),
                        "regex_used": pat,
                        "stop_token_triggered": stop_token_triggered,
                        "raw_captured": raw_val.strip(),
                        "final_extracted": final_val
                    }
                    if is_scored_field:
                        if field_name in ("monthly_income", "annual_loss_dependency"):
                            start_ctx = max(0, m.start() - 80)
                            end_ctx = min(len(text), m.end() + 80)
                            context_lower = (text[start_ctx:m.start()] + " " + text[m.end():end_ctx]).lower()
                            tribunal_keywords = [
                                "assessed", "adjudged", "taken", "held", "fixed", "determined",
                                "notional income", "as per the tribunal", "as awarded"
                            ]
                            has_positive_signal = any(kw in context_lower for kw in tribunal_keywords)
                            score = float(base_weight) + (5.0 if has_positive_signal else 0.0)
                        else:
                            score = _score_award_context(text, m.start())
                        priority_idx = next((i for i, (s, _) in enumerate(priority_list) if s == sec_name), 999)
                        candidates.append({
                            "val": val_to_store,
                            "confidence": round(confidence, 2),
                            "sec_name": sec_name,
                            "matched_page": matched_page,
                            "score": score,
                            "priority": priority_idx,
                            "pos": m.start(),
                            "debug": candidate_debug
                        })
                    else:
                        if field_name:
                            debug_info[field_name] = candidate_debug
                        return val_to_store, round(confidence, 2), sec_name, matched_page

    # Targeted raw_ocr document-wide search fallback
    raw_ocr_text = sections.get("raw_ocr", "")
    if raw_ocr_text and not any(sec_name == "raw_ocr" for sec_name, _ in priority_list):
        for pat in patterns:
            for m in re.finditer(pat, raw_ocr_text, re.IGNORECASE):
                if field_name in ("monthly_income", "annual_loss_dependency"):
                    start_pos = max(0, m.start() - 80)
                    pre_ctx = raw_ocr_text[start_pos:m.start()].lower()
                    if any(kw in pre_ctx for kw in CLAIM_LANGUAGE_KEYWORDS):
                        continue
                matched_source = m.group(0)
                raw_val = m.group(1).strip()
                
                active_stop_labels = []
                for sl in STOP_LABELS:
                    if field_name == "father_name" and sl in ["s/o", "d/o", "w/o", "son of", "daughter of", "wife of"]:
                        continue
                    active_stop_labels.append(sl)
                    
                truncated_val = raw_val
                is_text_field = (type_cast == str) and field_name in ["claimant_name", "deceased_name", "father_name", "occupation", "address"]
                
                if is_text_field:
                    comma_pos = truncated_val.find(",")
                    if comma_pos != -1:
                        truncated_val = truncated_val[:comma_pos]
                newline_pos = re.search(r'[\r\n]', truncated_val)
                if newline_pos:
                    truncated_val = truncated_val[:newline_pos.start()]
                for sl in active_stop_labels:
                    sl_match = re.search(r'\b' + re.escape(sl) + r'\b', truncated_val, re.IGNORECASE)
                    if sl_match:
                        truncated_val = truncated_val[:sl_match.start()]
                
                final_val = re.sub(r'\s+', ' ', truncated_val).strip()
                if is_text_field:
                    final_val = clean_legal_name(final_val)
                    
                if final_val:
                    matched_page = find_exact_page(final_val, 1, len(pages) if pages else 1, pages) if pages else 1
                    confidence = 0.50
                    if is_text_field:
                        confidence = validate_name_confidence(final_val, confidence)
                    
                    valid_candidate = False
                    val_to_store = None
                    
                    if type_cast == float:
                        val = parse_indian_rupee_value(final_val)
                        if val > 0:
                            valid_candidate = True
                            val_to_store = val
                    elif type_cast == int:
                        digit_match = re.search(r'\d+', final_val)
                        if digit_match:
                            try:
                                val = int(digit_match.group(0))
                                valid_candidate = True
                                val_to_store = val
                            except ValueError:
                                pass
                    else:
                        if len(final_val) > 2:
                            valid_candidate = True
                            val_to_store = final_val
                            
                    if valid_candidate:
                        candidate_debug = {
                            "matched_source_text": matched_source.strip(),
                            "regex_used": pat,
                            "stop_token_triggered": "raw_ocr_fallback",
                            "raw_captured": raw_val.strip(),
                            "final_extracted": final_val
                        }
                        if is_scored_field:
                            if field_name in ("monthly_income", "annual_loss_dependency"):
                                start_ctx = max(0, m.start() - 80)
                                end_ctx = min(len(raw_ocr_text), m.end() + 80)
                                context_lower = (raw_ocr_text[start_ctx:m.start()] + " " + raw_ocr_text[m.end():end_ctx]).lower()
                                tribunal_keywords = [
                                    "assessed", "adjudged", "taken", "held", "fixed", "determined",
                                    "notional income", "as per the tribunal", "as awarded"
                                ]
                                has_positive_signal = any(kw in context_lower for kw in tribunal_keywords)
                                score = 50.0 + (5.0 if has_positive_signal else 0.0)
                            else:
                                score = _score_award_context(raw_ocr_text, m.start())
                            candidates.append({
                                "val": val_to_store,
                                "confidence": confidence,
                                "sec_name": "raw_ocr_fallback",
                                "matched_page": matched_page,
                                "score": score,
                                "priority": 999,
                                "pos": m.start(),
                                "debug": candidate_debug
                            })
                        else:
                            if field_name:
                                debug_info[field_name] = candidate_debug
                            return val_to_store, confidence, "raw_ocr_fallback", matched_page

    if is_scored_field and candidates:
        # Sort candidates:
        # 1. score descending
        # 2. priority ascending (lower index is better priority)
        # 3. pos descending (prefer last match)
        candidates.sort(key=lambda x: (-x["score"], x["priority"], -x["pos"]))
        best = candidates[0]
        if field_name:
            debug_info[field_name] = best["debug"]
        return best["val"], best["confidence"], best["sec_name"], best["matched_page"]

    fallback_confidence = 0.30
    return default_val, fallback_confidence, "raw_ocr", 1


def real_text_recovery(petitioner_details, prayer_section, compensation_paragraphs, award_section, case_type):
    """
    Layer 4: Real-Text Recovery.
    """
    logger.info("Executing Real-Text Recovery on isolated sections...")
    recovered = {}

    name_m = re.search(r'\b(?:injured|deceased|claimant|petitioner|late shri|late smt|shri|smt|mr|mrs|kumari)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})', petitioner_details)
    if name_m:
        recovered["name"] = name_m.group(1).strip()

    # Try more specific patterns first to avoid capturing relative/claimant ages
    age_m = re.search(r'\b(?:age\s+of\s+deceased|deceased\s+aged|deceased\s+was\s+aged|age\s+of\s+injured|injured\s+aged|injured\s+was\s+aged|age\s+at\s+the\s+time\s+of\s+accident)\s*[:\-]?\s*(\d{1,2})\b', petitioner_details + " " + compensation_paragraphs, re.IGNORECASE)
    if not age_m:
        age_m = re.search(r'\b(?:age|aged|approximately)\s*(\d{1,2})\b', petitioner_details + " " + compensation_paragraphs, re.IGNORECASE)
    if age_m:
        recovered["age"] = int(age_m.group(1))

    # Extremely robust monthly income extraction that handles commas and currencies
    inc_m = re.search(r'\b(?:monthly\s+income|salary|earning|coolie|wages?)\b\s*(?:is|was|of|@)?\s*(?:rs\.?|inr|rupees)?\s*([\d,]{4,10})\b', compensation_paragraphs, re.IGNORECASE)
    if not inc_m:
        # Fallback regex with broad search
        inc_m = re.search(r'\b(?:monthly\s+income|salary|earning|coolie|wages?)\b.*?([\d,]{4,10})\b', compensation_paragraphs, re.IGNORECASE)
        
    if inc_m:
        recovered["monthly_income"] = parse_indian_rupee_value(inc_m.group(1))

    dep_m = re.search(r'\b(\d{1,2})\s*(?:dependents?|family\s+members)\b', petitioner_details)
    if dep_m:
        recovered["dependents"] = int(dep_m.group(1))

    # Extremely robust award amount extraction that handles commas and currencies
    aw_m = re.search(r'\b(?:awarded|compensation|award|sum\s+of)\s*(?:of|is|was|amounting\s+to)?\s*(?:rs\.?|inr|rupees)?\s*([\d,]{5,11})\b', award_section, re.IGNORECASE)
    if not aw_m:
        # Fallback regex with broad search
        aw_m = re.search(r'\b(?:awarded|compensation\s+of\s+rs\.?|tribunal\s+awards)\s*([\d,\.]+)\b', award_section, re.IGNORECASE)
        
    if aw_m:
        recovered["award_amount"] = parse_indian_rupee_value(aw_m.group(1))

    return recovered


def extract_dates_with_context(text):
    date_pattern = r'\b(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{4})\b'
    matches = []
    for m in re.finditer(date_pattern, text):
        try:
            d_str = f"{int(m.group(1)):02d}-{int(m.group(2)):02d}-{m.group(3)}"
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 12)
            context = text[start:end].lower()
            matches.append((d_str, context))
        except ValueError:
            pass
    return matches


def deduce_notional_income(award_amount, age, marital_status, dependents, future_prospect=None, multiplier=None, award_date=None):
    """
    Algebraically deduces a clean monthly notional income from the award_amount using standard legal formulas.
    Used when explicit monthly income is missing in the judgment text.
    """
    if not award_amount or award_amount <= 0:
        return 5000.0 # standard fallback
        
    # Standard conventional heads: Consortium (40k base), Funeral (15k base), Estate (15k base) enhanced dynamically
    from datetime import date
    from backend.calculator import get_conventional_heads_enhanced
    
    ref_date = None
    if award_date:
        for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                ref_date = datetime.strptime(award_date.strip(), fmt).date()
                break
            except ValueError:
                continue
    if not ref_date:
        ref_date = date.today()
        
    consortium = get_conventional_heads_enhanced(40000.0, ref_date)
    funeral = get_conventional_heads_enhanced(15000.0, ref_date)
    estate = get_conventional_heads_enhanced(15000.0, ref_date)
    conventional_heads = consortium + funeral + estate
    
    # Estimate loss of dependency
    loss_of_dependency = max(0.0, award_amount - conventional_heads)
    if loss_of_dependency <= 0:
        return 3000.0 if award_amount < 100000 else 5000.0
        
    # Multiplier
    if not multiplier:
        age_int = int(age) if (isinstance(age, int) or (isinstance(age, str) and age.isdigit())) else 30
        if age_int <= 15: expected_multiplier = 20
        elif age_int <= 25: expected_multiplier = 18
        elif age_int <= 30: expected_multiplier = 17
        elif age_int <= 35: expected_multiplier = 16
        elif age_int <= 40: expected_multiplier = 15
        elif age_int <= 45: expected_multiplier = 14
        elif age_int <= 50: expected_multiplier = 13
        elif age_int <= 55: expected_multiplier = 11
        elif age_int <= 60: expected_multiplier = 9
        elif age_int <= 65: expected_multiplier = 7
        else: expected_multiplier = 5
        multiplier = expected_multiplier
        
    # Deduction
    deduct_pct = get_personal_deduction_pct(marital_status, dependents)
        
    # Prospects
    if future_prospect is None or future_prospect == "":
        age_int = int(age) if (isinstance(age, int) or (isinstance(age, str) and age.isdigit())) else 30
        if age_int < 40: expected_prospects = 40.0
        elif age_int < 50: expected_prospects = 25.0
        elif age_int < 60: expected_prospects = 10.0
        else: expected_prospects = 0.0
        future_prospect = expected_prospects
        
    # Reconstruct monthly income
    # loss_of_dependency = (monthly_income * 12 * (1 + prospects/100) * (1 - deduct_pct)) * multiplier
    denominator = 12.0 * (1.0 + float(future_prospect) / 100.0) * (1.0 - deduct_pct) * multiplier
    if denominator > 0:
        monthly_income = loss_of_dependency / denominator
        if monthly_income > 0:
            # Round to nearest 500 for legal consistency
            rounded = round(monthly_income / 500.0) * 500.0
            if abs(rounded - monthly_income) < 400:
                return float(rounded)
            return round(monthly_income, 2)
            
    return 5000.0


def _extract_cause_title_block(top_pages_text):
    """
    Multi-line cause-title fallback for the common MP HC layout where the
    party name sits on its own line under an 'APPELLANT :' / 'RESPONDENT :'
    label with a standalone 'VERSUS' line in between -- as opposed to a
    compact single-line 'X -Vs- Y' scrutiny-report heading, which not every
    bundle attaches (older-format filings in particular often omit it).
    Returns (appellant_raw, respondent_raw) or None.
    """
    lines = top_pages_text.split("\n")
    appellant_label_re = re.compile(r'\b(?:APPELLANT|PETITIONER|APPLICANT)\b', re.IGNORECASE)
    respondent_label_re = re.compile(r'\b(?:RESPONDENTS?|NON[\s\-]?APPLICANTS?)\b', re.IGNORECASE)
    versus_line_re = re.compile(r'^\s*(?:VERSUS|VS\.?)\s*$', re.IGNORECASE)

    pending_appellant = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if versus_line_re.match(stripped) and pending_appellant:
            for j in range(i + 1, min(i + 5, len(lines))):
                r_line = lines[j].strip()
                if not r_line:
                    continue
                if respondent_label_re.search(r_line):
                    parts = re.split(r'[:\-]', r_line, maxsplit=1)
                    r_candidate = parts[1].strip() if len(parts) > 1 else respondent_label_re.sub('', r_line).strip(" :-")
                    if r_candidate:
                        return pending_appellant, r_candidate
                break
            pending_appellant = None
        elif appellant_label_re.search(stripped):
            parts = re.split(r'[:\-]', stripped, maxsplit=1)
            candidate = parts[1].strip() if len(parts) > 1 else appellant_label_re.sub('', stripped).strip(" :-")
            if candidate:
                pending_appellant = candidate
    return None


def parse_extracted_text(text_lines, case_type=None):
    """
    Highly advanced Section-Aware Legal Semantic Parser / Legal Document Intelligence Engine.
    Uses fuzzy heading matching, dynamic section boundary detection, fallback layout-hint clustering,
    section priority rules, entity contamination filters, page importance/citation suppression,
    chronological parsing, compensation table extraction, and detailed confidence tracking.
    """
    print("[PARSE DEBUG] First 60 lines of raw text:")
    for i, line in enumerate(text_lines[:60]):
        try:
            print(f"  Line {i+1:>2}: {line.strip()}")
        except UnicodeEncodeError:
            safe_line = line.strip().encode('ascii', errors='replace').decode('ascii')
            print(f"  Line {i+1:>2}: {safe_line}")

    full_text = "\n".join(text_lines)
    if case_type is None:
        from backend.llm_client import classify_case_type_by_ocr_text
        case_type = classify_case_type_by_ocr_text(full_text)

    # 1. Segment text_lines into pages
    pages = []
    current_page_num = 1
    current_page_lines = []
    
    for line in text_lines:
        line_strip = line.strip()
        if line_strip.startswith("--- PAGE"):
            if current_page_lines:
                pages.append({
                    "page_number": current_page_num,
                    "lines": current_page_lines,
                    "text": "\n".join(current_page_lines)
                })
            m = re.search(r'PAGE\s+(\d+)', line_strip, re.IGNORECASE)
            if m:
                current_page_num = int(m.group(1))
            current_page_lines = []
        else:
            current_page_lines.append(line)
            
    if current_page_lines or not pages:
        pages.append({
            "page_number": current_page_num,
            "lines": current_page_lines,
            "text": "\n".join(current_page_lines)
        })

    # 2. Compute Page Importances & Legal Citation Suppression
    page_importances = {}
    for p in pages:
        page_importances[p["page_number"]] = score_page_importance(p["text"], p["page_number"])

    # 3. Dynamic Section Detection & Boundary Determination
    merged_lines = merge_ocr_lines_to_paragraphs(text_lines)
    full_text = "\n".join(merged_lines)
    full_text_lower = full_text.lower()

    is_hindi_doc = _is_predominantly_devanagari(full_text, threshold=0.15)

    # English-only version used for autofill field extraction (grounds, prayer, petition).
    # Strips any line where ≥50 % of alphabetic characters are Devanagari so Hindi award
    # tables don't interfere with regex-based English parsers.
    merged_lines_english = [
        line for line in merged_lines
        if is_hindi_doc or not _is_predominantly_devanagari(line)
    ]
    
    sections_metadata = detect_document_sections_with_fallback(full_text, pages)
    sections = {name: info["content"] for name, info in sections_metadata.items()}
    sections["raw_ocr"] = full_text

    # 3b. MACT Tabular Form Extraction (Label: Value rows in petition forms)
    # Runs in O(n) with no external dependencies — safe on low-RAM servers
    tabular_fields = parse_mact_tabular_form(text_lines)
    if tabular_fields:
        logger.info(f"Tabular form parser extracted {len(tabular_fields)} fields: {list(tabular_fields.keys())}")

    # Populate backward-compatible blocks (English-only fallbacks)
    petition_block = sections.get("claimant_section", "") or sections.get("chronological_events_section", "") or sections.get("accident_section", "")
    prayer_block = sections.get("relief_section", "")
    award_block = sections.get("compensation_section", "") or sections.get("award_copy_section", "")
    facts_block = sections.get("facts_section", "")
    
    total_lines = len(merged_lines_english)
    if not petition_block:
        cutoff = max(10, int(total_lines * 0.35))
        petition_block = "\n".join(merged_lines_english[:cutoff])
        
    if not prayer_block:
        start_idx = int(total_lines * 0.3)
        end_idx = int(total_lines * 0.7)
        prayer_block = "\n".join(merged_lines_english[start_idx:end_idx])
        
    if not award_block:
        start_idx = int(total_lines * 0.6) if total_lines >= 50 else 0
        award_block = "\n".join(merged_lines_english[start_idx:])

    if not facts_block:
        start_idx = int(total_lines * 0.1)
        end_idx = int(total_lines * 0.5)
        facts_block = "\n".join(merged_lines_english[start_idx:end_idx])

    # Store blocks back to sections dictionary for contextual extraction and compatibility
    sections["petition_block"] = petition_block
    sections["prayer_block"] = prayer_block
    sections["award_block"] = award_block
    sections["facts_section"] = facts_block

    # Helper for contextual extraction parameters
    parser_debug = {}
    anomalies_detected = []
    claimant_relationship_to_deceased = ""
    conf_claimant_relationship = 0.0
    future_type = 2
    conf_future_type = 0.50
    sec_future_type = "raw_ocr"
    page_future_type = 1
    method_future_type = "Default Heuristic"

    # ── HIGH COURT PARTICULARS BLOCK HEURISTIC PARSER ────────────────────────
    block_date = None
    block_place = None
    block_dec_name = None
    block_age = None
    block_father_name = None
    block_occupation = None
    block_earning_daily = None

    # 1. Accident block
    accident_match = re.search(
        r'\bPARTICULARS\s+OF\s+(?:THE\s+)?ACCIDENT\b.*?(?=\bPARTICULARS\b|\bNAME\s+AND\s+DESCRIPTION\b|\bDETAILS\b|\bIN\s+FATAL\s+ACCIDENT\b|\(\s*[I|V|X|L|C|D|M]+\s*\)|$)',
        full_text,
        re.IGNORECASE | re.DOTALL
    )
    if accident_match:
        acc_block_text = accident_match.group(0)
        # Extract date of accident
        date_match = re.search(r'\b(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{4})\b', acc_block_text)
        if date_match:
            try:
                block_date = f"{int(date_match.group(1)):02d}-{int(date_match.group(2)):02d}-{date_match.group(3)}"
            except ValueError:
                pass
            
        # Extract place of accident
        sub_fields = []
        for label in ["Place Near", "Place of Accident", "Place", "Village/Locality", "Village", "Locality", "Tehsil", "District", "P.S.", "Police Station"]:
            m_label = re.search(rf'\b{re.escape(label)}\b\s*[:\-;\u2022]\s*(.*)', acc_block_text, re.IGNORECASE)
            if m_label:
                first_line = m_label.group(1).strip()
                if first_line:
                    val = first_line
                else:
                    start_pos = m_label.end()
                    remainder = acc_block_text[start_pos:]
                    lines = remainder.split("\n")
                    captured_lines = []
                    for line in lines:
                        cleaned_line = line.strip()
                        if not cleaned_line:
                            continue
                        if re.match(r'^(?:\d+\.|\(\s*[I|V|X|L|C|D|M]+\s*\))', cleaned_line):
                            break
                        if any(cleaned_line.lower().startswith(l.lower()) for l in ["Registration", "Time and date", "PARTICULARS"]):
                            break
                        captured_lines.append(cleaned_line)
                    val = " ".join(captured_lines)
                val = " ".join(val.split())
                if val:
                    sub_fields.append((label, val))

        super_fields = [v for l, v in sub_fields if l in ["Place Near", "Place of Accident", "Place"]]
        if super_fields:
            base_place = super_fields[0]
            extra_vals = []
            for l, v in sub_fields:
                if l not in ["Place Near", "Place of Accident", "Place"]:
                    if v.lower() not in base_place.lower():
                        extra_vals.append(v)
            if extra_vals:
                block_place = base_place + ", " + ", ".join(extra_vals)
            else:
                block_place = base_place
        elif sub_fields:
            sub_fields.sort(key=lambda x: acc_block_text.find(x[0]))
            block_place = ", ".join([v for l, v in sub_fields])

    # 2. Deceased block
    deceased_match = re.search(
        r'\b(?:NAME\s+AND\s+DESCRIPTION\s+OF\s+THE\s+(?:INJURED/)?DECEASED|DECEASED\s+PERSON|DESCRIPTION\s+OF\s+DECEASED)\b.*?(?=\bIN\s+FATAL\s+ACCIDENT\b|\bDETAILS\b|\(\s*[I|V|X|L|C|D|M]+\s*\)|$)',
        full_text,
        re.IGNORECASE | re.DOTALL
    )
    if deceased_match:
        dec_block_text = deceased_match.group(0)
        
        # Deceased Name
        name_match = re.search(r'\b(?:1\.?\s*Name)\s*[:\-;\u2022]\s*([^\n]+)', dec_block_text, re.IGNORECASE)
        if name_match:
            cand_name = clean_legal_name(name_match.group(1).strip())
            if cand_name:
                block_dec_name = cand_name.title()
            
        # Age
        age_match = re.search(r'\b(?:2\.?\s*Age)\s*[:\-;\u2022]\s*(\d{1,2})\b', dec_block_text, re.IGNORECASE)
        if age_match:
            block_age = int(age_match.group(1))
            
        # Father / Husband Name
        fh_match = re.search(r'\b(?:3\.?\s*(?:Father|Husband)(?:’|\')?s?\s*Name)\s*[:\-;\u2022]\s*([^\n]+)', dec_block_text, re.IGNORECASE)
        if fh_match:
            cand_fh = clean_legal_name(fh_match.group(1).strip())
            if cand_fh:
                block_father_name = cand_fh.title()

        # Occupation
        occ_match = re.search(r'\b(?:4\.?\s*Occupation)\s*[:\-;\u2022]\s*([^\n]+)', dec_block_text, re.IGNORECASE)
        if occ_match:
            block_occupation = occ_match.group(1).strip()
            
        # Claimed Daily Wage
        earning_match = re.search(r'\b(?:5\.?\s*Earning)\s*[:\-;\u2022]\s*([^\n]+)', dec_block_text, re.IGNORECASE)
        if earning_match:
            block_earning_daily = earning_match.group(1).strip()

    # Cause Title Claimant Extraction (e.g. "Insurance vs Claimant" or "Claimant vs Driver")
    cause_title_claimant = None
    cause_title_conf = 0.0
    cause_title_page = 1
    cause_title_sec = "raw_ocr"
    
    # Search for Vs patterns in the first 5 pages of full_text
    top_pages_text = "\n".join(p["text"] for p in pages[:5]) if pages else full_text[:4000]
    for vs_pattern in [r'\bversus\b', r'\bvs\b\.?', r'\bv\b\.?']:
        # Match lines containing Vs
        for line in top_pages_text.split("\n"):
            if re.search(vs_pattern, line, re.IGNORECASE):
                parts = re.split(vs_pattern, line, flags=re.IGNORECASE)
                part1 = parts[0].strip()
                part2 = parts[1].strip() if len(parts) > 1 else ""
                
                # Clean role words like APPELLANT, RESPONDENT, etc.
                part1_clean = clean_legal_name(part1)
                part2_clean = clean_legal_name(part2)
                
                # Check if part1 is an insurance company
                part1_lower = part1.lower()
                is_ins = any(kw in part1_lower for kw in ["insurance", "insur", "ins.", "co.", "ltd", "limited", "corp", "corporation", "gic", "hdi", "magma", "general"])
                
                if is_ins and part2_clean and len(part2_clean) > 2:
                    cause_title_claimant = part2_clean
                    cause_title_conf = 0.95
                    cause_title_page = find_exact_page(part2_clean, 1, 5, pages) if pages else 1
                    cause_title_sec = "cause_title"
                    logger.info(f"Cause title extraction: found claimant '{cause_title_claimant}' after insurance company '{part1_clean}'")
                    break
                elif part1_clean and len(part1_clean) > 2 and not is_ins:
                    # Let's check roles for part1 and part2 in the document text!
                    role_part1 = determine_name_role(part1_clean, full_text)
                    role_part2 = determine_name_role(part2_clean, full_text)
                    
                    logger.info(f"Cause title roles check: '{part1_clean}' -> {role_part1}, '{part2_clean}' -> {role_part2}")
                    
                    if role_part1 == "non-claimant" and role_part2 == "claimant":
                        cause_title_claimant = part2_clean
                        cause_title_conf = 0.95
                        cause_title_page = find_exact_page(part2_clean, 1, 5, pages) if pages else 1
                        cause_title_sec = "cause_title"
                        logger.info(f"Cause title extraction (role resolved): chose claimant '{cause_title_claimant}' over non-claimant '{part1_clean}'")
                        break
                    elif role_part2 == "non-claimant" and role_part1 == "claimant":
                        cause_title_claimant = part1_clean
                        cause_title_conf = 0.95
                        cause_title_page = find_exact_page(part1_clean, 1, 5, pages) if pages else 1
                        cause_title_sec = "cause_title"
                        logger.info(f"Cause title extraction (role resolved): chose claimant '{cause_title_claimant}' over non-claimant '{part2_clean}'")
                        break
                    elif role_part1 == "claimant" and role_part2 != "claimant":
                        cause_title_claimant = part1_clean
                        cause_title_conf = 0.95
                        cause_title_page = find_exact_page(part1_clean, 1, 5, pages) if pages else 1
                        cause_title_sec = "cause_title"
                        logger.info(f"Cause title extraction (role resolved): chose claimant '{cause_title_claimant}' because part1 is claimant and part2 is not")
                        break
                    elif role_part2 == "claimant" and role_part1 != "claimant":
                        cause_title_claimant = part2_clean
                        cause_title_conf = 0.95
                        cause_title_page = find_exact_page(part2_clean, 1, 5, pages) if pages else 1
                        cause_title_sec = "cause_title"
                        logger.info(f"Cause title extraction (role resolved): chose claimant '{cause_title_claimant}' because part2 is claimant and part1 is not")
                        break
                    elif role_part1 == "non-claimant" and role_part2 != "non-claimant":
                        if part2_clean and len(part2_clean) > 2:
                            cause_title_claimant = part2_clean
                            cause_title_conf = 0.90
                            cause_title_page = find_exact_page(part2_clean, 1, 5, pages) if pages else 1
                            cause_title_sec = "cause_title"
                            logger.info(f"Cause title extraction (role resolved): chose part2 '{cause_title_claimant}' because part1 is non-claimant")
                            break
                    elif role_part2 == "non-claimant" and role_part1 != "non-claimant":
                        if part1_clean and len(part1_clean) > 2:
                            cause_title_claimant = part1_clean
                            cause_title_conf = 0.90
                            cause_title_page = find_exact_page(part1_clean, 1, 5, pages) if pages else 1
                            cause_title_sec = "cause_title"
                            logger.info(f"Cause title extraction (role resolved): chose part1 '{cause_title_claimant}' because part2 is non-claimant")
                            break
                    else:
                        cause_title_claimant = part1_clean
                        cause_title_conf = 0.90
                        cause_title_page = find_exact_page(part1_clean, 1, 5, pages) if pages else 1
                        cause_title_sec = "cause_title"
                        logger.info(f"Cause title extraction (default): found claimant '{cause_title_claimant}' before vs")
                        break
        if cause_title_claimant:
            break

    if not cause_title_claimant:
        # Fallback: standard MP HC cause-title layout where the party name
        # is on its own line under an 'APPELLANT :' / 'RESPONDENT :' label
        # with a standalone 'VERSUS' line in between. This is what carries
        # older-format bundles (no compact "X -Vs- Y" scrutiny-report page)
        # through correctly instead of falling through to the honorific-only
        # claimant_patterns below, which can misfire on a tribunal member's
        # or judge's name.
        block_result = _extract_cause_title_block(top_pages_text)
        if block_result:
            appellant_raw, respondent_raw = block_result
            appellant_clean = clean_legal_name(appellant_raw)
            respondent_clean = clean_legal_name(respondent_raw)
            is_ins = any(kw in appellant_raw.lower() for kw in [
                "insurance", "insur", "ins.", "co.", "ltd", "limited", "corp", "corporation", "gic", "hdi", "magma", "general"
            ])
            chosen = None
            if is_ins and respondent_clean and len(respondent_clean) > 2:
                chosen = respondent_clean
            elif appellant_clean and len(appellant_clean) > 2 and not is_ins:
                role_a = determine_name_role(appellant_clean, full_text)
                role_r = determine_name_role(respondent_clean, full_text) if respondent_clean else "unknown"
                if role_a == "non-claimant" and role_r == "claimant":
                    chosen = respondent_clean
                elif role_r == "non-claimant" and role_a == "claimant":
                    chosen = appellant_clean
                elif role_a == "claimant" and role_r != "claimant":
                    chosen = appellant_clean
                elif role_r == "claimant" and role_a != "claimant":
                    chosen = respondent_clean
                elif role_a == "non-claimant" and respondent_clean:
                    chosen = respondent_clean
                elif role_r == "non-claimant" and appellant_clean:
                    chosen = appellant_clean
                else:
                    chosen = appellant_clean
            elif respondent_clean:
                chosen = respondent_clean

            if chosen and len(chosen) > 2:
                cause_title_claimant = chosen
                cause_title_conf = 0.90
                cause_title_page = find_exact_page(chosen, 1, 5, pages) if pages else 1
                cause_title_sec = "cause_title"
                logger.info(
                    f"Cause title extraction (multi-line block): chose claimant "
                    f"'{cause_title_claimant}' (appellant='{appellant_clean}', respondent='{respondent_clean}')"
                )

    # 1. Claimant Name extraction
    claimant_patterns = [
        r'^(?:\d+[\.\)\-][ \t]*)?\b(?:claimant|injured|victim)\b[ \t]*(?:name)?[ \t]*[:\-][ \t]*(.*)',
        r'\b(?:name\s+of\s+)(?:claimant|injured|victim)\b[ \t]*[:\-][ \t]*(.*)',
        r'^(?:\d+[\.\)\-][ \t]*)?\bpetitioner\b[ \t]*(?:name)?[ \t]*[:\-][ \t]*(.*)',
        r'\b(?:name\s+of\s+)petitioner\b[ \t]*[:\-][ \t]*(.*)',
        r'^(?:\d+[\.\)\-][ \t]*)?\bappellant\b[ \t]*(?:name)?[ \t]*[:\-][ \t]*(.*)',
        r'\b(?:name\s+of\s+)appellant\b[ \t]*[:\-][ \t]*(.*)',
        r'^(?:\d+[\.\)\-][ \t]*)?\brespondent\b[ \t]*(?:name)?[ \t]*[:\-][ \t]*(.*)',
        r'\b(?:name\s+of\s+)respondent\b[ \t]*[:\-][ \t]*(.*)',
        r'^[ \t]*\d+[\.\)\-][ \t]*(?:name)?[ \t]*[:\-][ \t]*(.*)',
        r'^[ \t]*\d+[\.\)\-][ \t]*((?-i:[A-Z][a-zA-Z\s\.\-]+))',
        r'\bsmt\b[ \t]*(.*)',
        r'\bshri\b[ \t]*(.*)',
        r'\bmr\b[ \t]*(.*)',
        r'\bmrs\b[ \t]*(.*)',
        r'\bkumari\b[ \t]*(.*)',
        r'^[ \t]*1\.[ \t]*((?-i:[A-Z][a-zA-Z\s\.\-]+))'
    ]
    
    if cause_title_claimant:
        claimant_name = cause_title_claimant
        conf_claimant_name = cause_title_conf
        sec_claimant_name = cause_title_sec
        page_claimant_name = cause_title_page
        method_claimant_name = "Cause Title Parser"
    else:
        claimant_name, conf_claimant_name, sec_claimant_name, page_claimant_name = contextual_extract(
            claimant_patterns, sections, [("claimant_section", 90), ("facts_section", 85), ("memo_of_appeal_section", 80)], type_cast=str,
            field_name="claimant_name", debug_info=parser_debug, pages=pages, sections_metadata=sections_metadata, page_importances=page_importances
        )
        method_claimant_name = "Section-Aware Contextual Regex"
        
    if claimant_name: claimant_name = claimant_name.title()

    # 2. Deceased Name extraction
    if block_dec_name:
        deceased_name = block_dec_name
        conf_deceased_name = 0.99
        sec_deceased_name = "particulars_block"
        page_deceased_name = 1
        method_deceased_name = "High Court Particulars Block"
    else:
        dec_patterns = [
            r'^(?:\d+[\.\)\-][ \t]*)?\bdeceased\b[ \t]*(?:name)?[ \t]*[:\-][ \t]*(.*)',
            r'\b(?:name\s+of\s+)deceased\b[ \t]*[:\-][ \t]*(.*)',
            r'^(?:\d+[\.\)\-][ \t]*)?\bdeath\s+of\s+(.*)',
            r'\blate\b[ \t]*(?:shri|smt)?[ \t]*(.*)',
            r'\b((?-i:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*))[ \t]*(?:\(deceased\)|deceased)\b',
            r'\b(?:deceased)[ \t]+((?-i:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*))\b',
            r'\bdeath[ \t]+of[ \t]+(?:shri|smt|late)?[ \t]*((?-i:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*))\b',
            r'\b((?-i:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*))[ \t]*(?:died|expired)\b'
        ]
        deceased_name, conf_deceased_name, sec_deceased_name, page_deceased_name = contextual_extract(
            dec_patterns, sections, [("claimant_section", 90), ("facts_section", 85), ("memo_of_appeal_section", 80)], type_cast=str,
            field_name="deceased_name", debug_info=parser_debug, pages=pages, sections_metadata=sections_metadata, page_importances=page_importances
        )
        method_deceased_name = "Section-Aware Contextual Regex"
        if deceased_name: deceased_name = deceased_name.title()

    # Deceased Block Extraction (Page 8 - High Court Factual Details)
    deceased_block_match = re.search(
        r'\b(?:deceased\s+person|description\s+of\s+deceased|name\s+and\s+description\s+of\s+the\s+deceased)\b.*?\b(?:name)\s*[|\s]*[:\-;\u2022][|\s]*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})',
        full_text,
        re.IGNORECASE | re.DOTALL
    )
    if deceased_block_match:
        deceased_name = deceased_block_match.group(1).strip().title()
        conf_deceased_name = 0.99
        sec_deceased_name = "compensation_section"
        page_deceased_name = find_exact_page(deceased_name, 1, len(pages), pages) if pages else 8
        method_deceased_name = "Deceased Block Extraction"
        parser_debug["deceased_name"] = {
            "matched_source_text": deceased_block_match.group(0).strip(),
            "regex_used": "Deceased Block Extraction (Name)",
            "stop_token_triggered": "Block Match",
            "raw_captured": deceased_block_match.group(1),
            "final_extracted": deceased_name
        }

    # Apply Deceased overrides (Requirement 6)
    if claimant_name and any(kw in claimant_name.lower() for kw in ["late shri", "late smt", "late "]):
        if not deceased_name:
            deceased_name = claimant_name
            conf_deceased_name = conf_claimant_name
            sec_deceased_name = sec_claimant_name
            page_deceased_name = page_claimant_name
            method_deceased_name = method_claimant_name
        claimant_name = None
        conf_claimant_name = 0.0
        sec_claimant_name = "claimant_section"
        page_claimant_name = 1
        method_claimant_name = "Deceased Override Check"

    # 3. Father / Husband Name
    if block_father_name:
        father_name = block_father_name
        conf_father_name = 0.99
        sec_father_name = "particulars_block"
        page_father_name = 1
        method_father_name = "High Court Particulars Block"
    else:
        father_patterns = [
            r'(?:father|husband)\s*(?:[\'’]?s\s*)?name\s*[:\-]\s*(.*)',
            r'(?:father|husband)\s*[/\\]\s*(?:husband|father)\s*(?:name|[\'’]?s\s*name)?\s*[:\-]\s*(.*)',
            r'\bs[\./\s\\]*o\b\s*(?:shri|late\s+shri|late)?\s*(.*)',
            r'\bd[\./\s\\]*o\b\s*(?:shri|smt|kumari|late)?\s*(.*)',
            r'\bw[\./\s\\]*o\b\s*(?:shri|late\s+shri|late)?\s*(.*)',
            r'\bh[\./\s\\]*o\b\s*(?:shri|late\s+shri|late)?\s*(.*)',
            r'\bc[\./\s\\]*o\b\s*(?:shri|smt)?\s*(.*)',
            r'\bson\s+of\b\s*(?:shri|late)?\s*(.*)',
            r'\bdaughter\s+of\b\s*(?:shri|smt|late)?\s*(.*)',
            r'\bwife\s+of\b\s*(?:shri|late)?\s*(.*)',
            r'\bhusband\s+of\b\s*(?:shri|late)?\s*(.*)',
            r'\bcare\s+of\b\s*(?:shri|smt|late)?\s*(.*)',
        ]
        father_name, conf_father_name, sec_father_name, page_father_name = contextual_extract(
            father_patterns, sections, [("claimant_section", 90), ("facts_section", 85), ("memo_of_appeal_section", 80)], type_cast=str,
            field_name="father_name", debug_info=parser_debug, pages=pages, sections_metadata=sections_metadata, page_importances=page_importances
        )
        method_father_name = "Section-Aware Contextual Regex"
        if father_name: father_name = father_name.title()

    # Tabular form fallback for father_name
    if not father_name and tabular_fields.get("father_name"):
        raw_fn = tabular_fields["father_name"]
        cleaned_fn = clean_legal_name(raw_fn)
        if cleaned_fn:
            father_name = cleaned_fn.title()
            conf_father_name = 0.88
            sec_father_name = "tabular_form"
            page_father_name = 1
            method_father_name = "Tabular Form Extraction"

    # Splitting Claimant Inline Relationship
    source_line = sections.get("claimant_section", "")
    split_res = extract_relationship_entities(source_line)
    if split_res:
        c_split, rel_type, f_split = split_res
        if rel_type:
            # Bug/Feature: Verify f_split against deceased_name
            is_match = False
            if deceased_name:
                def clean_name(n):
                    n = n.lower()
                    n = re.sub(r'\b(?:late|shri|smt|mr|mrs|sh\.?|deceased)\b', '', n)
                    n = re.sub(r'[^a-z0-9\s]', '', n)
                    return [t.strip() for t in n.split() if t.strip()]
                t1 = clean_name(f_split)
                t2 = clean_name(deceased_name)
                if t1 and t2:
                    overlap = set(t1).intersection(set(t2))
                    if len(overlap) >= min(len(t1), len(t2), 2):
                        is_match = True
            
            if is_match:
                claimant_relationship_to_deceased = rel_type
                conf_claimant_relationship = 0.95
            else:
                # Try to infer the real relationship from surviving-dependents language elsewhere in the document.
                inferred_rel = None
                search_text = (sections.get("claimant_section", "") + " " + sections.get("chronological_events_section", "") + " " + full_text).lower()
                
                claimant_fn = ""
                if c_split:
                    tokens = [t for t in c_split.split() if len(t) > 2]
                    if tokens:
                        claimant_fn = tokens[0].lower()
                
                if claimant_fn:
                    pos = 0
                    while True:
                        idx = search_text.find(claimant_fn, pos)
                        if idx == -1:
                            break
                        w_start = max(0, idx - 75)
                        w_end = min(len(search_text), idx + len(claimant_fn) + 75)
                        window = search_text[w_start:w_end]
                        
                        if re.search(r'\b(?:mother\s+of\s+deceased|mother\s+of\s+the\s+deceased|mother)\b', window):
                            inferred_rel = "Mother of"
                            break
                        elif re.search(r'\b(?:father\s+of\s+deceased|father\s+of\s+the\s+deceased|father)\b', window):
                            inferred_rel = "Father of"
                            break
                        elif re.search(r'\b(?:wife\s+of\s+deceased|wife\s+of\s+the\s+deceased|wife|widow)\b', window):
                            inferred_rel = "Wife of"
                            break
                        elif re.search(r'\b(?:husband\s+of\s+deceased|husband\s+of\s+the\s+deceased|husband)\b', window):
                            inferred_rel = "Husband of"
                            break
                        elif re.search(r'\b(?:son\s+of\s+deceased|son\s+of\s+the\s+deceased)\b', window):
                            inferred_rel = "Son of"
                            break
                        elif re.search(r'\b(?:daughter\s+of\s+deceased|daughter\s+of\s+the\s+deceased)\b', window):
                            inferred_rel = "Daughter of"
                            break
                        elif re.search(r'\b(?:brother\s+of\s+deceased|brother\s+of\s+the\s+deceased|brother)\b', window):
                            inferred_rel = "Brother of"
                            break
                        elif re.search(r'\b(?:sister\s+of\s+deceased|sister\s+of\s+the\s+deceased|sister)\b', window):
                            inferred_rel = "Sister of"
                            break
                        
                        pos = idx + len(claimant_fn)
                
                if not inferred_rel:
                    if re.search(r'\b(?:claimant\s+is\s+the\s+mother|petitioner\s+is\s+the\s+mother|mother\s+of\s+the\s+deceased|mother\s+of\s+deceased)\b', search_text):
                        inferred_rel = "Mother of"
                    elif re.search(r'\b(?:claimant\s+is\s+the\s+father|petitioner\s+is\s+the\s+father|father\s+of\s+the\s+deceased|father\s+of\s+deceased)\b', search_text):
                        inferred_rel = "Father of"
                    elif re.search(r'\b(?:wife\s+of\s+the\s+deceased|wife\s+of\s+deceased|widow\s+of\s+the\s+deceased|widow\s+of\s+deceased)\b', search_text):
                        inferred_rel = "Wife of"
                    elif re.search(r'\b(?:son\s+of\s+the\s+deceased|son\s+of\s+deceased)\b', search_text):
                        inferred_rel = "Son of"
                    elif re.search(r'\b(?:daughter\s+of\s+the\s+deceased|daughter\s+of\s+deceased)\b', search_text):
                        inferred_rel = "Daughter of"

                if inferred_rel:
                    claimant_relationship_to_deceased = inferred_rel
                    conf_claimant_relationship = 0.85
                else:
                    claimant_relationship_to_deceased = ""
                    conf_claimant_relationship = 0.0
        if c_split:
            claimant_name = c_split.title()
            conf_claimant_name = max(conf_claimant_name, 0.95)
            sec_claimant_name = "claimant_section"
            method_claimant_name = "Relationship Splitting"
            if "claimant_name" in parser_debug:
                parser_debug["claimant_name"]["final_extracted"] = claimant_name
                parser_debug["claimant_name"]["stop_token_triggered"] = f"Relationship split '{rel_type}'"
        if f_split and (not father_name or len(father_name) < 3 or "date" in father_name.lower()):
            father_name = f_split.title()
            conf_father_name = max(conf_father_name, 0.95)
            sec_father_name = "claimant_section"
            page_father_name = find_exact_page(father_name, 1, 10, pages)
            method_father_name = "Relationship Splitting"
            parser_debug["father_name"] = {
                "matched_source_text": source_line[:200].strip(),
                "regex_used": "Relationship split from Claimant",
                "stop_token_triggered": f"Relationship split '{rel_type}'",
                "raw_captured": f_split,
                "final_extracted": father_name
            }

    # 4. Age only from claimant/petition section or chronological events
    if block_age:
        age = block_age
        conf_age = 0.99
        sec_age = "particulars_block"
        page_age = 1
        method_age = "High Court Particulars Block"
    elif case_type == "death":
        age = ""
        conf_age = 0.0
        sec_age = "raw_ocr"
        page_age = 1
        method_age = "Fallback"

        # A. Search specifically within a "Name and Description of the Deceased person" section/heading
        # or equivalent phrasing in full_text
        dec_sec_match = re.search(
            r'\b(?:name\s+and\s+description\s+of\s+(?:the\s+)?deceased(?:\s+person)?|description\s+of\s+(?:the\s+)?deceased(?:\s+person)?|deceased\s+person|fatal\s+accident\s+case)\b',
            full_text,
            re.IGNORECASE
        )
        if dec_sec_match:
            start_pos = dec_sec_match.end()
            end_pos = min(len(full_text), start_pos + 600)
            deceased_block = full_text[start_pos:end_pos]
            
            for pat in [
                r'\b(?:age|aged)\s*(?:about|is|was)?\s*[:\-;]?\s*(\d{1,2})\b',
                r'\b(\d{1,2})\s*(?:years|yrs)\b'
            ]:
                m = re.search(pat, deceased_block, re.IGNORECASE)
                if m:
                    val = int(m.group(1))
                    if 5 <= val <= 100:
                        age = val
                        conf_age = 0.99
                        sec_age = "deceased_section"
                        page_age = find_exact_page(str(age), 1, len(pages), pages) if pages else 1
                        method_age = "Deceased Section Extraction"
                        parser_debug["age"] = {
                            "matched_source_text": dec_sec_match.group(0) + " ... " + m.group(0),
                            "regex_used": pat,
                            "stop_token_triggered": "Section Match",
                            "raw_captured": m.group(1),
                            "final_extracted": age
                        }
                        break

        # B. Contextual extraction from non-claimant sections using death patterns
        if not age:
            death_age_patterns = [
                r'\b(?:deceased|victim|deceased\s+person|description\s+of\s+deceased)\b.*?\b(?:age|aged)\s*(?:about|is|was)?\s*[:\-;]?\s*(\d{1,2})\b',
                r'\b(?:age|aged)\s+of\s+(?:the\s+)?(?:deceased|victim)\s+(?:was|is)?\s*[:\-]?\s*(\d{1,2})\b',
                r'\b(?:deceased|victim)\s+(?:was\s+)?aged?\s*(?:about|is)?\s*(\d{1,2})\b',
                r'\b(?:deceased|victim)\b.*?\baged?\s*[:\-]?\s*(\d{1,2})\b',
                r'\bage\s+of\s+the?\s*deceased\s*[:\-]?\s*(\d{1,2})\b',
                r'\bdeceased\s+was\s+aged\s*(?:about)?\s*(\d{1,2})\b',
                r'\bdeceased\s+aged\s*(?:about)?\s*(\d{1,2})\b',
                r'\bage\s+at\s+the?\s*time\s+of\s+(?:the\s+)?accident\s*[:\-]?\s*(\d{1,2})\b',
            ]
            age, conf_age, sec_age, page_age = contextual_extract(
                death_age_patterns, sections, [("chronological_events_section", 90), ("facts_section", 85), ("compensation_section", 80), ("award_copy_section", 70)], default_val="", type_cast=int,
                field_name="age", debug_info=parser_debug, pages=pages, sections_metadata=sections_metadata, page_importances=page_importances
            )
            if age:
                method_age = "Section-Aware Contextual Regex"
            else:
                age, conf_age, sec_age, page_age = contextual_extract(
                    death_age_patterns, sections, [("facts_section", 85), ("grounds_section", 80), ("relief_section", 70)], default_val="", type_cast=int,
                    field_name="age", debug_info=parser_debug, pages=pages, sections_metadata=sections_metadata, page_importances=page_importances
                )
                if age:
                    method_age = "Section-Aware Contextual Regex"

        # C. Fallback: search for age value near the deceased's name specifically
        if not age and deceased_name:
            name_tokens = [t for t in deceased_name.split() if len(t) > 2]
            if name_tokens:
                search_term = name_tokens[0]
                pos = 0
                while True:
                    idx = full_text.lower().find(search_term.lower(), pos)
                    if idx == -1:
                        break
                    w_start = max(0, idx - 150)
                    w_end = min(len(full_text), idx + len(search_term) + 150)
                    window = full_text[w_start:w_end]
                    
                    for pat in [
                        r'\b(?:age|aged)\s*(?:about|is|was)?\s*[:\-;]?\s*(\d{1,2})\b',
                        r'\b(\d{1,2})\s*(?:years|yrs)\b'
                    ]:
                        m = re.search(pat, window, re.IGNORECASE)
                        if m:
                            val = int(m.group(1))
                            if 5 <= val <= 100:
                                age = val
                                conf_age = 0.95
                                sec_age = "near_deceased_name"
                                page_age = find_exact_page(str(age), 1, len(pages), pages) if pages else 1
                                method_age = "Proximity to Deceased Name"
                                parser_debug["age"] = {
                                    "matched_source_text": window,
                                    "regex_used": pat,
                                    "stop_token_triggered": "Name Proximity",
                                    "raw_captured": m.group(1),
                                    "final_extracted": age
                                }
                                break
                    if age:
                        break
                    pos = idx + len(search_term)

    else:
        # Injury case (applicant is the injured person, keep original logic)
        age_patterns = [
            r'\bage\s+of\s+the?\s*deceased\s*[:\-]?\s*(\d{1,2})\b',
            r'\bage\s+of\s+the?\s*injured\s*[:\-]?\s*(\d{1,2})\b',
            r'\bdeceased\s+was\s+aged\s*(?:about)?\s*(\d{1,2})\b',
            r'\binjured\s+was\s+aged\s*(?:about)?\s*(\d{1,2})\b',
            r'\bdeceased\s+aged\s*(?:about)?\s*(\d{1,2})\b',
            r'\binjured\s+aged\s*(?:about)?\s*(\d{1,2})\b',
            r'\bage\s+at\s+the?\s*time\s+of\s+(?:the\s+)?accident\s*[:\-]?\s*(\d{1,2})\b',
            r'\bdate\s+of\s+accident\s+age\s*[:\-]?\s*(\d{1,2})\b',
            r'(?:aged\s+about|age\s+of\s+claimant|aged|approximately)\s*[:\-]?\s*(\d{1,2})\b',
            r'\b([1-9]\d)\s*years\s*(?:old)?\b',
            r'\bage\s*[:\-]\s*(\d{1,2})\s*(?:years|yrs)?\b',
            r'(?:is|was)\s+(\d{1,2})\s+years\s+(?:of\s+age|old)\b',
            r'\bage\s*[:\-]?\s*(\d{1,2})\b',
            r'\baged\s+(\d{1,2})\b',
        ]
        age, conf_age, sec_age, page_age = contextual_extract(
            age_patterns, sections, [("claimant_section", 95), ("facts_section", 85), ("chronological_events_section", 80)], default_val="", type_cast=int,
            field_name="age", debug_info=parser_debug, pages=pages, sections_metadata=sections_metadata, page_importances=page_importances
        )
        method_age = "Section-Aware Contextual Regex"

    # Guard: reject implausible ages (e.g. paragraph numbers matched as age)
    if isinstance(age, int) and age < 6:
        age = ""
        conf_age = 0.0
        sec_age = "raw_ocr"
        method_age = "Fallback"

    # Tabular form fallback for age (case-type-aware)
    if not age:
        age_raw = None
        if case_type == "death":
            age_raw = tabular_fields.get("age_deceased") or tabular_fields.get("age")
        else:
            age_raw = tabular_fields.get("age_claimant") or tabular_fields.get("age")

        if age_raw:
            age_m = re.search(r'(\d{1,2})', age_raw)
            if age_m and int(age_m.group(1)) >= 6:
                age = int(age_m.group(1))
                conf_age = 0.88
                sec_age = "tabular_form"
                page_age = 1
                method_age = "Tabular Form Extraction"

    # Deceased Block Extraction (Age) Fallback
    if not age:
        deceased_age_match = re.search(
            r'\b(?:deceased\s+person|description\s+of\s+deceased)\b.*?\b(?:age)\s*[:\-;]\s*(\d{1,2})\b',
            full_text,
            re.IGNORECASE | re.DOTALL
        )
        if deceased_age_match:
            age = int(deceased_age_match.group(1))
            conf_age = 0.99
            sec_age = "compensation_section"
            page_age = find_exact_page(str(age), 1, len(pages), pages) if pages else 8
            method_age = "Deceased Block Extraction"
            parser_debug["age"] = {
                "matched_source_text": deceased_age_match.group(0).strip(),
                "regex_used": "Deceased Block Extraction (Age)",
                "stop_token_triggered": "Block Match",
                "raw_captured": deceased_age_match.group(1),
                "final_extracted": age
            }

    # 5. Occupation only from claimant/petition section
    occ_patterns = [
        r'occupation\s*[:\-]\s*(.*)',
        r'employed\s+as\s+(.*)',
        r'working\s+as\s+(.*)',
        r'earning\s+as\s+(.*)',
        r'profession\s*[:\-]\s*(.*)',
        r'trade\s*[:\-]\s*(.*)',
        r'vocation\s*[:\-]\s*(.*)',
        r'nature\s+of\s+(?:work|job|employment)\s*[:\-]\s*(.*)',
        r'by\s+(?:profession|occupation|trade)\b\s*(?:is\s+a?|was\s+a?)?\s*(.*)',
        r'(?:he|she)\s+(?:was|is)\s+(?:a|an)\s+([A-Za-z][A-Za-z\s]+?)\s+(?:by\s+(?:profession|occupation)|earning|working)',
        r'\bby\s+occupation\s+(?:is|was)?\s*(.*)',
        r'\bself\s+employed\b\s*(.*)',
        r'\bself-employed\b\s*(.*)',
    ]
    occupation, conf_occupation, sec_occupation, page_occupation = contextual_extract(
        occ_patterns, sections, [("claimant_section", 90), ("facts_section", 85), ("memo_of_appeal_section", 80)], default_val="", type_cast=str,
        field_name="occupation", debug_info=parser_debug, pages=pages, sections_metadata=sections_metadata, page_importances=page_importances
    )
    method_occupation = "Section-Aware Contextual Regex"
    if occupation: occupation = normalize_occupation(occupation).title()

    # Tabular form fallback for occupation
    if not occupation and tabular_fields.get("occupation"):
        occ_raw = clean_legal_name(tabular_fields["occupation"])
        if occ_raw and len(occ_raw) > 1:
            occupation = normalize_occupation(occ_raw).title()
            conf_occupation = 0.88
            sec_occupation = "tabular_form"
            page_occupation = 1
            method_occupation = "Tabular Form Extraction"

    # Deceased Block Extraction (Occupation)
    deceased_occ_match = re.search(
        r'\b(?:deceased\s+person|description\s+of\s+deceased)\b.*?\b(?:occupation)\s*[:\-;]\s*([A-Za-z\s]+)\b',
        full_text,
        re.IGNORECASE | re.DOTALL
    )
    if deceased_occ_match:
        occupation = normalize_occupation(deceased_occ_match.group(1).strip()).title()
        conf_occupation = 0.99
        sec_occupation = "compensation_section"
        page_occupation = find_exact_page(occupation, 1, len(pages), pages) if pages else 8
        method_occupation = "Deceased Block Extraction"
        parser_debug["occupation"] = {
            "matched_source_text": deceased_occ_match.group(0).strip(),
            "regex_used": "Deceased Block Extraction (Occupation)",
            "stop_token_triggered": "Block Match",
            "raw_captured": deceased_occ_match.group(1),
            "final_extracted": occupation
        }

    # 6. Place of accident
    if block_place:
        place_of_accident = block_place
        conf_place_of_accident = 0.99
        sec_place_of_accident = "particulars_block"
        page_place_of_accident = 1
        method_place_of_accident = "High Court Particulars Block"
    else:
        place_of_accident = None
        conf_place_of_accident = 0.0
        sec_place_of_accident = "particulars_block"
        page_place_of_accident = 1
        method_place_of_accident = "Not Found"

    # 7. Dependents only from claimant/petition section
    dependents_patterns = [
        r'\b(\d{1,2})\s*dependents\b',
        r'\bno\.\s*of\s*dependents?\s*(?:is|:)?\s*(\d{1,2})\b',
        r'\bnumber\s*of\s*dependents?\s*(?:is|:)?\s*(\d{1,2})\b'
    ]
    dependents, conf_dependents, sec_dependents, page_dependents = contextual_extract(
        dependents_patterns, sections, [("claimant_section", 95), ("facts_section", 85), ("memo_of_appeal_section", 80)], default_val="", type_cast=int,
        field_name="dependents", debug_info=parser_debug, pages=pages, sections_metadata=sections_metadata, page_importances=page_importances
    )
    method_dependents = "Section-Aware Contextual Regex"

    # 8. Marital Status from claimant, facts, and memo_of_appeal sections
    marital_status = ""
    conf_marital_status = 0.0
    sec_marital_status = "raw_ocr"
    page_marital_status = 1
    method_marital_status = "Default Heuristic"
    marital_patterns = {
        "married": ["married", "wife of deceased", "wife of the deceased", "widow of deceased", "widow of the deceased", "husband of deceased", "husband of the deceased"],
        "single": ["single", "unmarried", "bachelor", "spinster"]
    }
    
    # Check claimant_section, facts_section, memo_of_appeal_section for keywords
    for sec_name in ["claimant_section", "facts_section", "memo_of_appeal_section"]:
        sec_text = sections.get(sec_name, "")
        if not sec_text:
            continue
        sec_text_lower = sec_text.lower()
        
        # Check married/single keywords first
        for status, keywords in marital_patterns.items():
            for kw in keywords:
                if re.search(rf'\b{re.escape(kw)}\b', sec_text_lower):
                    marital_status = status
                    conf_marital_status = 0.90
                    sec_marital_status = sec_name
                    sec_meta = sections_metadata.get(sec_name, {})
                    page_marital_status = find_exact_page(kw, sec_meta.get("start_page", 1), sec_meta.get("end_page", 1), pages)
                    method_marital_status = f"Keyword Matching ({kw})"
                    break
            if method_marital_status != "Default Heuristic":
                break
        
        if method_marital_status != "Default Heuristic":
            break
            
        # Check "W/o" or "Wife of" relation to claimant name
        if claimant_name and deceased_name:
            clean_cname = claimant_name.lower().strip()
            escaped_cname = re.escape(clean_cname)
            wo_patterns = [
                (rf'\bw/o\b[\s,:\(\)-]*(?:smt\.?|mrs\.?)?\s*{escaped_cname}', "prefix"),
                (rf'\bwife\s+of\s+[\s,:\(\)-]*(?:smt\.?|mrs\.?)?\s*{escaped_cname}', "prefix"),
                (rf'{escaped_cname}[\s,:\(\)-]*(?:is\s+)?\bw/o\b', "suffix"),
                (rf'{escaped_cname}[\s,:\(\)-]*(?:is\s+)?\bwife\s+of\b', "suffix")
            ]
            for pat, pat_type in wo_patterns:
                for line in sec_text_lower.split('\n'):
                    m = re.search(pat, line)
                    if m:
                        husband_candidate = ""
                        if pat_type == "suffix":
                            # Extract the text after "w/o" or "wife of" on this line
                            suffix_match = re.search(rf'\b(?:w/o|wife\s+of)\b[\s\.]*(?:shri|late)?\s*(.*?)(?:\b(?:age|aged|resident|r/o|address|occupation)\b|$)', line)
                            if suffix_match:
                                husband_candidate = suffix_match.group(1).strip()
                        else:
                            # Extract the text before "w/o" or "wife of" on this line
                            prefix_match = re.search(rf'(.*?)\b(?:w/o|wife\s+of)\b', line)
                            if prefix_match:
                                husband_candidate = prefix_match.group(1).strip()
                        
                        # Clean up punctuation
                        husband_candidate = re.sub(r'[\s,\.\-\(\)\/\|]+$', '', husband_candidate).strip()
                        husband_candidate = re.sub(r'^[\s,\.\-\(\)\/\|]+', '', husband_candidate).strip()
                        
                        is_husband_deceased = False
                        if husband_candidate and deceased_name:
                            def clean_name(n):
                                n = n.lower()
                                n = re.sub(r'\b(?:late|shri|smt|mr|mrs|sh\.?|deceased)\b', '', n)
                                n = re.sub(r'[^a-z0-9\s]', '', n)
                                return [t.strip() for t in n.split() if t.strip()]
                            t1 = clean_name(husband_candidate)
                            t2 = clean_name(deceased_name)
                            if t1 and t2:
                                overlap = set(t1).intersection(set(t2))
                                if len(overlap) >= min(len(t1), len(t2), 2):
                                    is_husband_deceased = True
                        
                        if is_husband_deceased:
                            marital_status = "married"
                            conf_marital_status = 0.90
                            sec_marital_status = sec_name
                            sec_meta = sections_metadata.get(sec_name, {})
                            page_marital_status = find_exact_page(m.group(0), sec_meta.get("start_page", 1), sec_meta.get("end_page", 1), pages)
                            method_marital_status = "Claimant Wife/Widow Relation Match"
                            break
                if method_marital_status != "Default Heuristic":
                    break
                    
        if method_marital_status != "Default Heuristic":
            break

    # Fallback to single if young deceased, with parents/siblings claimants, and late father
    if method_marital_status == "Default Heuristic":
        # Check if father is Late
        father_name_lower = father_name.lower() if father_name else ""
        is_father_late = "late" in father_name_lower
        
        combined_rel_text = (sections.get("claimant_section", "") + "\n" + 
                             sections.get("facts_section", "") + "\n" + 
                             sections.get("memo_of_appeal_section", "")).lower()
                             
        has_so_late = is_father_late
        if not has_so_late and father_name:
            escaped_fname = re.escape(father_name.lower().strip())
            if re.search(rf'\blate\b[\s,:\(\)-]*(?:shri|smt)?\s*{escaped_fname}', combined_rel_text):
                has_so_late = True
                
        if not has_so_late and deceased_name:
            escaped_dname = re.escape(deceased_name.lower().strip())
            d_so_patterns = [
                rf'{escaped_dname}[\s,:\(\)-]*\bs/o\b[\s,:\(\)-]*(?:late|shri|sh\.?)*\s+late',
                rf'\bs/o\b[\s,:\(\)-]*(?:late|shri|sh\.?)*\s+late[\s\w,:\(\)-]*?{escaped_dname}',
                rf'{escaped_dname}[\s,:\(\)-]*\bson\s+of\s+[\s,:\(\)-]*(?:late|shri|sh\.?)*\s+late',
            ]
            for sec_name in ["claimant_section", "facts_section", "memo_of_appeal_section"]:
                sec_text = sections.get(sec_name, "").lower()
                if any(re.search(pat, sec_text) for pat in d_so_patterns):
                    has_so_late = True
                    break
        
        is_young = False
        if age:
            try:
                val_age = float(age)
                if val_age <= 30:
                    is_young = True
            except (ValueError, TypeError):
                pass
                
        combined_rel_text = (sections.get("claimant_section", "") + "\n" + 
                             sections.get("facts_section", "") + "\n" + 
                             sections.get("memo_of_appeal_section", "")).lower()
                             
        parent_sibling_keywords = [
            "mother of deceased", "father of deceased", "parents of deceased",
            "brother of deceased", "sister of deceased", "siblings of deceased",
            "mother of the deceased", "father of the deceased", "parents of the deceased",
            "brother of the deceased", "sister of the deceased", "siblings of the deceased",
            "mother of late", "father of late", "parents of late", "parents (mother",
            "mother & father", "siblings"
        ]
        
        spouse_child_keywords = [
            "wife of deceased", "husband of deceased", "spouse of deceased",
            "widow of deceased", "son of deceased", "daughter of deceased",
            "children of deceased", "wife of the deceased", "husband of the deceased",
            "spouse of the deceased", "widow of the deceased", "son of the deceased",
            "daughter of the deceased", "children of the deceased", "wife of late",
            "widow of late", "son of late", "daughter of late", "children of late"
        ]
        
        has_parent_sibling = any(kw in combined_rel_text for kw in parent_sibling_keywords)
        if not has_parent_sibling:
            for word in ["mother", "father", "parents", "brother", "sister", "sibling", "siblings"]:
                if re.search(r'\b' + re.escape(word) + r'\b', combined_rel_text):
                    has_parent_sibling = True
                    break
                    
        has_spouse_child = False
        for kw in spouse_child_keywords:
            if kw in combined_rel_text:
                has_spouse_child = True
                break
                
        if has_so_late and is_young and has_parent_sibling and not has_spouse_child:
            marital_status = "single"
            conf_marital_status = 0.75
            sec_marital_status = "claimant_section" if sections.get("claimant_section", "") else "memo_of_appeal_section"
            page_marital_status = 1
            method_marital_status = "Fallback Heuristic (Single Young Deceased with Parent/Sibling Claimants)"

        if case_type == "death" and marital_status not in ["single", "bachelor"]:
            has_wife_inf = any(w in combined_rel_text for w in ["wife of deceased", "w/o deceased", "w/o the deceased", "widow of", "widow of deceased", "widow of the deceased", "claimant is the widow", "petitioner is the widow"])
            has_child_inf = any(w in combined_rel_text for w in ["son of deceased", "daughter of deceased", "children of", "minor son", "minor daughter", "daughter of the deceased", "son of the deceased"])
            has_parents_inf = any(w in combined_rel_text for w in ["mother of deceased", "father of deceased", "mother of the deceased", "father of the deceased", "parents of", "petitioner is the mother", "claimant is the mother", "appellant is the mother"])
            
            if has_wife_inf:
                marital_status = "married"
                conf_marital_status = 0.90
                method_marital_status = "Parental/Spousal Context Inference (Wife)"
            elif has_parents_inf and not (has_wife_inf or has_child_inf):
                marital_status = "single"
                conf_marital_status = 0.90
                method_marital_status = "Parental/Spousal Context Inference (Bachelor)"
            else:
                marital_status = "married"
                conf_marital_status = 0.50
                method_marital_status = "Parental/Spousal Context Inference (Default)"


    # 8.2 Future Type from compensation or award section
    future_type_patterns = {
        1: ["permanent job", "permanent employment", "government employee", "govt employee",
            "government job", "permanent service", "regular employment"],
        2: ["self employed", "self-employed", "fixed salary", "not in any permanent employment",
            "daily wage", "no permanent job"],
    }
    comp_sec_text = sections.get("compensation_section", "").lower()
    award_sec_text = sections.get("award_copy_section", "").lower()
    found_ftype = None
    found_sec = None
    found_kw = None
    for ftype, keywords in future_type_patterns.items():
        for kw in keywords:
            if kw in comp_sec_text:
                found_ftype = ftype
                found_sec = "compensation_section"
                found_kw = kw
                break
        if found_ftype:
            break
    if not found_ftype:
        for ftype, keywords in future_type_patterns.items():
            for kw in keywords:
                if kw in award_sec_text:
                    found_ftype = ftype
                    found_sec = "award_copy_section"
                    found_kw = kw
                    break
            if found_ftype:
                break
    if found_ftype is not None:
        future_type = found_ftype
        conf_future_type = 0.90
        sec_future_type = found_sec
        sec_meta = sections_metadata.get(found_sec, {})
        page_future_type = find_exact_page(found_kw, sec_meta.get("start_page", 1), sec_meta.get("end_page", 1), pages)
        method_future_type = "Keyword Matching"

    if case_type == "death" and future_type == 2:
        occ_str = str(block_occupation or occupation or "").lower()
        if any(kw in occ_str for kw in ["service", "govt", "government", "company", "increment", "increments"]):
            future_type = 1
            conf_future_type = 0.90
            method_future_type = "Occupation Inferred (Service/Govt)"
        else:
            future_type = 2
            conf_future_type = 0.90
            method_future_type = "Occupation Inferred (Self-Employed/Other)"

    # ======================================================
    # QUANTITATIVE AND COMPENSATION TABLE EXTRACTION
    # ======================================================

    comp_fields = extract_compensation_table_fields(sections.get("compensation_section", "") or sections.get("award_copy_section", ""), case_type)
    
    # 9.1 Monthly Income (with multi-pass annual/monthly extraction)
    monthly_income = comp_fields["monthly_income"]
    if monthly_income:
        conf_monthly_income = 0.98
        sec_monthly_income = "compensation_section"
        sec_meta = sections_metadata.get("compensation_section", {}) or sections_metadata.get("award_copy_section", {})
        page_monthly_income = find_exact_page(int(monthly_income), sec_meta.get("start_page", 1), sec_meta.get("end_page", 1), pages)
        method_monthly_income = comp_fields.get("monthly_income_method") or "Compensation Table Extraction"
    else:
        # Temporary debug log of sections.keys() and sections containing 'annual income'
        logger.info(f"Sections keys: {list(sections.keys())}")
        for sec_k, sec_v in sections.items():
            if re.search(r'annual\s+income', sec_v, re.IGNORECASE):
                logger.info(f"Section '{sec_k}' contains matching line for annual income")

        annual_patterns = [
            r'\b(?:annual|yearly)\s+income(?:\s+of\s+(?:the\s+)?(?:deceased|victim|appellant|petitioner|claimant)?(?:\s+[\w\.\-]+){0,3})?(?:\s*\([^)]*\))?\s*[^a-zA-Z\d\r\n]*(?:[\r\n]+[^a-zA-Z\d\r\n]*)?(?:rs\.?|inr|rupees?|हैं|₹|[a-zA-Z])?\s*([\d,\.\s]+lakhs?|[\d,\.\s]+lacs?|(?:\d[\d,\.\s]*\d|\d))\b',
            r'\bincome(?:\s+of\s+(?:the\s+)?(?:deceased|victim|appellant|petitioner|claimant)?(?:\s+[\w\.\-]+){0,3})?\s*\(\s*(?:annual|yearly)\s*\)\s*[^a-zA-Z\d\r\n]*(?:[\r\n]+[^a-zA-Z\d\r\n]*)?(?:rs\.?|inr|rupees?|हैं|₹|[a-zA-Z])?\s*([\d,\.\s]+lakhs?|[\d,\.\s]+lacs?|(?:\d[\d,\.\s]*\d|\d))\b'
        ]
        
        income_patterns = [
            r'(?:monthly\s+income|salary|earning|notional\s+income|coolie|wages?)\s*(?:is|was|has\s+been)?\s*(?:assessed|taken|fixed|determined)?\s*(?:at|as|of|@)?\s*(?:rs\.?|inr|rupees?|हैं|₹|[a-zA-Z])?\s*([\d,\.\s]+lakhs?|[\d,\.\s]+lacs?|(?:\d[\d,\.\s]*\d|\d))\b',
            r'\b(?:rs\.?|inr)?\s*([\d,\.]+)\s*(?:rs\.?|inr)?\s*(?:per\s*month|\/pm|\/-\s*pm|p\.m\.)',
            r'per\s*month\b.*?([\d,\.]+)\b',
            r'income\s+is\s+assessed\s+at\s+rs\.?\s*([\d,\.]+)\b',
            r'assessed\s+(?:the\s+)?monthly\s+income\s+(?:of\s+the\s+deceased\s+)?at\s*(?:rs\.?|inr)?\s*([\d,\.]+)\b',
            r'monthly\s+income\s+of\s+the\s+deceased\s+(?:is|was)\s*(?:assessed|taken|fixed|determined)\s*(?:at|as)?\s*(?:rs\.?|inr)?\s*([\d,\.]+)\b',
            r'\b(?:rs\.?|inr|rupees?|हैं|₹|[a-zA-Z])?\s*(\d[\d,\.\s]*\d|\d)\s*p\.m\.\b'
        ]

        non_grounds_sections = [
            ("compensation_section", 95),
            ("award_copy_section", 90),
            ("memo_of_appeal_section", 88),
            ("facts_section", 85)
        ]
        
        # Pass 1: Search ANNUAL-income patterns in non-grounds sections
        annual_val, conf, sec, page = contextual_extract(
            annual_patterns, sections, non_grounds_sections, default_val=None, type_cast=float,
            field_name="monthly_income", debug_info=parser_debug, pages=pages, sections_metadata=sections_metadata, page_importances=page_importances
        )
        if annual_val is not None and annual_val > 0:
            monthly_income = round(annual_val / 12.0, 2)
            conf_monthly_income = conf
            sec_monthly_income = sec
            page_monthly_income = page
            method_monthly_income = "Section-Aware Contextual Regex (Annual to Monthly)"
        else:
            # Pass 2: Search MONTHLY income_patterns in non-grounds sections
            m_val, conf, sec, page = contextual_extract(
                income_patterns, sections, non_grounds_sections, default_val=None, type_cast=float,
                field_name="monthly_income", debug_info=parser_debug, pages=pages, sections_metadata=sections_metadata, page_importances=page_importances
            )
            if m_val is not None and m_val > 0:
                monthly_income = m_val
                conf_monthly_income = conf
                sec_monthly_income = sec
                page_monthly_income = page
                method_monthly_income = "Section-Aware Contextual Regex"
            else:
                # Pass 3: Search ANNUAL-income patterns in grounds_section only (weight ~75)
                annual_val, conf, sec, page = contextual_extract(
                    annual_patterns, sections, [("grounds_section", 75)], default_val=None, type_cast=float,
                    field_name="monthly_income", debug_info=parser_debug, pages=pages, sections_metadata=sections_metadata, page_importances=page_importances
                )
                if annual_val is not None and annual_val > 0:
                    monthly_income = round(annual_val / 12.0, 2)
                    conf_monthly_income = conf
                    sec_monthly_income = sec
                    page_monthly_income = page
                    method_monthly_income = "Section-Aware Contextual Regex (Annual to Monthly, Grounds Fallback)"
                else:
                    # Pass 4: Search MONTHLY income_patterns in grounds_section only
                    m_val, conf, sec, page = contextual_extract(
                        income_patterns, sections, [("grounds_section", 75)], default_val=None, type_cast=float,
                        field_name="monthly_income", debug_info=parser_debug, pages=pages, sections_metadata=sections_metadata, page_importances=page_importances
                    )
                    if m_val is not None and m_val > 0:
                        monthly_income = m_val
                        conf_monthly_income = conf
                        sec_monthly_income = sec
                        page_monthly_income = page
                        method_monthly_income = "Section-Aware Contextual Regex (Grounds Fallback)"
                    else:
                        # Pass 5: Fallback to 0.0
                        monthly_income = 0.0
                        conf_monthly_income = 0.30
                        sec_monthly_income = "raw_ocr"
                        page_monthly_income = 1
                        method_monthly_income = "Default Fallback"

    if case_type == "death":
        pri_income = None
        pri_method = ""

        # 1. Adjudged annual income
        for m_inc in re.finditer(r'Annual\s+Income\s+(?:of\s+(?:the\s+)?deceased)?', full_text, re.IGNORECASE):
            start = max(0, m_inc.start() - 50)
            end = min(len(full_text), m_inc.end() + 200)
            window = full_text[start:end]
            if any(kw in window.lower() for kw in ["adjudged", "determined", "assessed", "tribunal"]):
                pre_match = window[:m_inc.start() - start].lower()
                if any(kw in pre_match for kw in ["stated", "claimed", "pleaded", "asserted", "contended", "according to", "claim of", "case of"]):
                    continue
                amt_m = re.search(r'(?:Rs\.?|INR)?\s*([\d,]+)', window[m_inc.end() - start:], re.IGNORECASE)
                if amt_m:
                    try:
                        adjudged_val = float(amt_m.group(1).replace(",", ""))
                        pri_income = round(adjudged_val / 12.0, 2)
                        pri_method = "Adjudged Annual Income / 12"
                        break
                    except ValueError:
                        pass

        # 2. Notional/flat annual from dependency
        if pri_income is None:
            for m_dep in re.finditer(r'dependency', full_text, re.IGNORECASE):
                start = max(0, m_dep.start() - 50)
                end = min(len(full_text), m_dep.end() + 150)
                window = full_text[start:end]
                notional_m = re.search(r'(\d{1,3}(?:,\d{3})+|\d{4,6})\s*[xX*]\s*(\d{1,2})', window, re.IGNORECASE)
                if notional_m:
                    try:
                        notional_val = float(notional_m.group(1).replace(",", ""))
                        pri_income = round(notional_val / 12.0, 2)
                        pri_method = "Notional Flat Annual Income / 12"
                        break
                    except ValueError:
                        pass

        # 3. Daily wage
        if pri_income is None:
            daily_match = re.search(
                r'earning.*?([\d,]+).*?(?:per\s+day|daily|/-\s+per\s+day)',
                full_text,
                re.IGNORECASE
            )
            if daily_match:
                try:
                    daily_val = float(daily_match.group(1).replace(",", ""))
                    pri_income = round(daily_val * 26.0, 2)
                    pri_method = "Daily Claimed Wage * 26"
                except ValueError:
                    pass
            elif block_earning_daily:
                daily_m = re.search(r'(?:Rs\.?|INR)?\s*([\d,]+)', block_earning_daily, re.IGNORECASE)
                if daily_m:
                    try:
                        daily_val = float(daily_m.group(1).replace(",", ""))
                        pri_income = round(daily_val * 26.0, 2)
                        pri_method = "Daily Claimed Wage (Block) * 26"
                    except ValueError:
                        pass

        if pri_income is not None:
            monthly_income = pri_income
            conf_monthly_income = 0.99
            sec_monthly_income = "particulars_block"
            page_monthly_income = 1
            method_monthly_income = pri_method

    # 9.2 Multiplier
    multiplier = comp_fields["multiplier"]
    if multiplier:
        conf_multiplier = 0.98
        sec_multiplier = "compensation_section"
        sec_meta = sections_metadata.get("compensation_section", {}) or sections_metadata.get("award_copy_section", {})
        page_multiplier = find_exact_page(int(multiplier), sec_meta.get("start_page", 1), sec_meta.get("end_page", 1), pages)
        method_multiplier = "Compensation Table Extraction"
    else:
        multiplier_patterns = [
            r'multiplier\s*(?:of|is|applied)?\s*(\d{1,2})\b',
            r'applied\s+multiplier\s+of\s*(\d{1,2})\b',
            r'\b(\d{1,2})\s*multiplier\b'
        ]
        multiplier, conf_multiplier, sec_multiplier, page_multiplier = contextual_extract(
            multiplier_patterns, sections, [("compensation_section", 95), ("award_copy_section", 90), ("facts_section", 85)], default_val="", type_cast=int,
            field_name="multiplier", debug_info=parser_debug, pages=pages, sections_metadata=sections_metadata, page_importances=page_importances
        )
        method_multiplier = "Section-Aware Contextual Regex"

    # 9.3 Future Prospect
    future_prospect = comp_fields["future_prospect"]
    if future_prospect:
        conf_future_prospect = 0.98
        sec_future_prospect = "compensation_section"
        sec_meta = sections_metadata.get("compensation_section", {}) or sections_metadata.get("award_copy_section", {})
        page_future_prospect = find_exact_page(int(future_prospect), sec_meta.get("start_page", 1), sec_meta.get("end_page", 1), pages)
        method_future_prospect = "Compensation Table Extraction"
    else:
        prospects_patterns = [
            r'future\s+prospects?\s*(?:of|at|is|@)?\s*(\d{1,2})\s*%',
            r'addition\s+of\s*(\d{1,2})\s*%\s*(?:towards)?\s*future\s+prospects'
        ]
        future_prospect, conf_future_prospect, sec_future_prospect, page_future_prospect = contextual_extract(
            prospects_patterns, sections, [("compensation_section", 95), ("award_copy_section", 90), ("facts_section", 85)], default_val="", type_cast=float,
            field_name="future_prospect", debug_info=parser_debug, pages=pages, sections_metadata=sections_metadata, page_importances=page_importances
        )
        method_future_prospect = "Section-Aware Contextual Regex"

    # 9.35 Respectively-based Triple conventional heads extraction
    resp_consortium = None
    resp_funeral = None
    resp_estate = None
    resp_consortium_score = -999999
    
    # We search the compensation/award copy sections or full_text for "respectively"
    # and patterns matching 3 amounts and the conventional head keywords.
    search_text_resp = (sections.get("compensation_section", "") or sections.get("award_copy_section", "") or full_text)
    
    for m_resp in re.finditer(r'\brespectively\b', search_text_resp, re.IGNORECASE):
        start = max(0, m_resp.start() - 250)
        end = min(len(search_text_resp), m_resp.end() + 250)
        window = search_text_resp[start:end]
        window_lower = window.lower()
        
        amounts = []
        for amt_match in re.finditer(r'\b(?:rs\.?|inr|हैं|%|₹)?\s*([\d,]{4,7})\b', window, re.IGNORECASE):
            val = parse_indian_rupee_value(amt_match.group(1))
            if 1980 <= val <= 2050:
                continue
            if val > 0:
                amounts.append((val, amt_match.start()))
                
        if len(amounts) >= 3:
            has_cons = "consortium" in window_lower
            has_est = "estate" in window_lower
            has_fun = "funeral" in window_lower
            
            if has_cons and has_est and has_fun:
                pos_cons = window_lower.find("consortium")
                pos_est = window_lower.find("estate")
                pos_fun = window_lower.find("funeral")
                
                heads = sorted([
                    ("consortium", pos_cons),
                    ("estate", pos_est),
                    ("funeral", pos_fun)
                ], key=lambda x: x[1])
                
                sorted_amounts = sorted(amounts, key=lambda x: x[1])[:3]
                
                mapping = {}
                for i in range(3):
                    mapping[heads[i][0]] = sorted_amounts[i][0]
                    
                score = _score_award_context(search_text_resp, m_resp.start())
                if score >= resp_consortium_score:
                    resp_consortium = mapping["consortium"]
                    resp_estate = mapping["estate"]
                    resp_funeral = mapping["funeral"]
                    resp_consortium_score = score

    # 9.36 Conventional heads list extraction
    conv_list_vals = extract_conventional_heads_list(search_text_resp)

    # 9.4 Consortium
    consortium = comp_fields["consortium"]
    if consortium:
        conf_consortium = 0.98
        sec_consortium = "compensation_section"
        sec_meta = sections_metadata.get("compensation_section", {}) or sections_metadata.get("award_copy_section", {})
        page_consortium = find_exact_page(int(consortium), sec_meta.get("start_page", 1), sec_meta.get("end_page", 1), pages)
        method_consortium = "Compensation Table Extraction"
    else:
        if conv_list_vals and "consortium" in conv_list_vals:
            consortium = conv_list_vals["consortium"]
            conf_consortium = 0.95
            sec_consortium = "compensation_section" if sections.get("compensation_section", "") else "award_copy_section"
            sec_meta = sections_metadata.get(sec_consortium, {})
            page_consortium = find_exact_page(int(consortium), sec_meta.get("start_page", 1), sec_meta.get("end_page", 1), pages)
            method_consortium = "Conventional Heads List Extraction"
        elif resp_consortium is not None:
            consortium = resp_consortium
            conf_consortium = 0.95
            sec_consortium = "compensation_section" if sections.get("compensation_section", "") else "award_copy_section"
            sec_meta = sections_metadata.get(sec_consortium, {})
            page_consortium = find_exact_page(int(consortium), sec_meta.get("start_page", 1), sec_meta.get("end_page", 1), pages)
            method_consortium = "Respectively Sentence Extraction"
        else:
            cons_patterns = [r'consortium\s*(?:of|is|was|to|@)?\s*(?:rs\.?|inr|rupees)?\s*([\d,]{4,7})\b']
            consortium, conf_consortium, sec_consortium, page_consortium = contextual_extract(
                cons_patterns, sections, [("compensation_section", 95), ("award_copy_section", 90)], default_val=48400.0 if case_type == "death" else 0.0, type_cast=float,
                field_name="consortium", debug_info=parser_debug, pages=pages, sections_metadata=sections_metadata, page_importances=page_importances
            )
            method_consortium = "Section-Aware Contextual Regex"

    # 9.5 Funeral Expenses
    funeral_expenses = comp_fields["funeral_expenses"]
    if funeral_expenses:
        conf_funeral_expenses = 0.98
        sec_funeral_expenses = "compensation_section"
        sec_meta = sections_metadata.get("compensation_section", {}) or sections_metadata.get("award_copy_section", {})
        page_funeral_expenses = find_exact_page(int(funeral_expenses), sec_meta.get("start_page", 1), sec_meta.get("end_page", 1), pages)
        method_funeral_expenses = "Compensation Table Extraction"
    else:
        if conv_list_vals and "funeral_expenses" in conv_list_vals:
            funeral_expenses = conv_list_vals["funeral_expenses"]
            conf_funeral_expenses = 0.95
            sec_funeral_expenses = "compensation_section" if sections.get("compensation_section", "") else "award_copy_section"
            sec_meta = sections_metadata.get(sec_funeral_expenses, {})
            page_funeral_expenses = find_exact_page(int(funeral_expenses), sec_meta.get("start_page", 1), sec_meta.get("end_page", 1), pages)
            method_funeral_expenses = "Conventional Heads List Extraction"
        elif resp_funeral is not None:
            funeral_expenses = resp_funeral
            conf_funeral_expenses = 0.95
            sec_funeral_expenses = "compensation_section" if sections.get("compensation_section", "") else "award_copy_section"
            sec_meta = sections_metadata.get(sec_funeral_expenses, {})
            page_funeral_expenses = find_exact_page(int(funeral_expenses), sec_meta.get("start_page", 1), sec_meta.get("end_page", 1), pages)
            method_funeral_expenses = "Respectively Sentence Extraction"
        else:
            fun_patterns = [r'funeral\s*(?:expenses?|rites?|rituals?)?\s*(?:of|is|was|to|@)?\s*(?:rs\.?|inr|rupees)?\s*([\d,]{4,7})\b']
            funeral_expenses, conf_funeral_expenses, sec_funeral_expenses, page_funeral_expenses = contextual_extract(
                fun_patterns, sections, [("compensation_section", 95), ("award_copy_section", 90)], default_val=18150.0 if case_type == "death" else 0.0, type_cast=float,
                field_name="funeral_expenses", debug_info=parser_debug, pages=pages, sections_metadata=sections_metadata, page_importances=page_importances
            )
            method_funeral_expenses = "Section-Aware Contextual Regex"

    # 9.6 Total Compensation
    total_compensation = comp_fields["total_compensation"]
    if total_compensation:
        conf_total_compensation = 0.98
        sec_total_compensation = "compensation_section"
        sec_meta = sections_metadata.get("compensation_section", {}) or sections_metadata.get("award_copy_section", {})
        page_total_compensation = find_exact_page(int(total_compensation), sec_meta.get("start_page", 1), sec_meta.get("end_page", 1), pages)
        method_total_compensation = "Compensation Table Extraction"
    else:
        award_patterns = [
            r'\b(?:total\s+)?(?:awarded|compensation|award|sum)\s*(?:amount|sum)?\s*(?:of|is|was|amounting\s+to|by\s+the\s+tribunal|by\s+tribunal)?\s*(?:rs\.?|inr|rupees)?\s*([\d,\.\s]+lakhs?|[\d,\.\-\/]+)\b',
            r'\b(?:total\s+compensation\s+of|compensation\s+amount\s+of)\s*(?:rs\.?|inr|rupees)?\s*([\d,\.\-\/]+)\b'
        ]
        total_compensation, conf_total_compensation, sec_total_compensation, page_total_compensation = contextual_extract(
            award_patterns, sections, [("compensation_section", 95), ("award_copy_section", 90)], default_val="", type_cast=float,
            field_name="total_compensation", debug_info=parser_debug, pages=pages, sections_metadata=sections_metadata, page_importances=page_importances
        )
        method_total_compensation = "Section-Aware Contextual Regex"

    # 9.7 Disability
    disability_patterns = [
        r'\b(\d{1,2}(?:\.\d+)?)\s*%\s*(?:permanent)?\s*disability\b',
        r'\bdisability\b\s*(?:of|is|:)?\s*(\d{1,2}(?:\.\d+)?)\s*%'
    ]
    disability, conf_disability, sec_disability, page_disability = contextual_extract(
        disability_patterns, sections, [("compensation_section", 95), ("award_copy_section", 90)], default_val="", type_cast=float,
        field_name="disability", debug_info=parser_debug, pages=pages, sections_metadata=sections_metadata, page_importances=page_importances
    )
    method_disability = "Section-Aware Contextual Regex"

    # 9.8 Estate Loss
    if conv_list_vals and "estate_loss" in conv_list_vals:
        estate_loss = conv_list_vals["estate_loss"]
        conf_estate_loss = 0.95
        sec_estate_loss = "compensation_section" if sections.get("compensation_section", "") else "award_copy_section"
        sec_meta = sections_metadata.get(sec_estate_loss, {})
        page_estate_loss = find_exact_page(int(estate_loss), sec_meta.get("start_page", 1), sec_meta.get("end_page", 1), pages)
        method_estate_loss = "Conventional Heads List Extraction"
    elif resp_estate is not None:
        estate_loss = resp_estate
        conf_estate_loss = 0.95
        sec_estate_loss = "compensation_section" if sections.get("compensation_section", "") else "award_copy_section"
        sec_meta = sections_metadata.get(sec_estate_loss, {})
        page_estate_loss = find_exact_page(int(estate_loss), sec_meta.get("start_page", 1), sec_meta.get("end_page", 1), pages)
        method_estate_loss = "Respectively Sentence Extraction"
    else:
        est_patterns = [r'(?:loss\s+of\s+)?estate\s*(?:of|is|was|to|@)?\s*(?:rs\.?|inr|rupees)?\s*([\d,]{4,7})\b']
        estate_loss, conf_estate_loss, sec_estate_loss, page_estate_loss = contextual_extract(
            est_patterns, sections, [("compensation_section", 95), ("award_copy_section", 90)], default_val=18150.0 if case_type == "death" else 0.0, type_cast=float,
            field_name="estate_loss", debug_info=parser_debug, pages=pages, sections_metadata=sections_metadata, page_importances=page_importances
        )
        method_estate_loss = "Section-Aware Contextual Regex"

    # ======================================================
    # 10. NEW STRUCTURED FIELDS: FIR, Policy, Vehicle, Insurance
    # ======================================================

    # 10a. FIR Number
    _fir_patterns = [
        r'\b(?:fir|f\s*\.\s*i\s*\.\s*r\s*\.?)\s*(?:no\.?|number|#)\s*[:\-]?\s*([\w/\-]+(?:/\d{4})?)',
        r'\b(?:fir|f\s*\.\s*i\s*\.\s*r\s*\.?)\s*(?:no\.?|number|#)?\s*[:\-]?\s*([\w/\-]+(?:\s+of\s+\d{4})?)',
        r'\bcrime\s*(?:no\.?|number)\s*[:\-]?\s*([\w/\-]+(?:/\d{4})?)',
        r'\b(?:crime|cr)\s*(?:case\s*)?(?:no\.?|number)\s*[:\-]?\s*([\w/\-]+(?:\s+of\s+\d{4})?)',
        r'\bcr\.?\s*(?:no\.?|case\s*no\.?)\s*[:\-]?\s*([\w/\-]+)',
        r'\bpolice\s+(?:station\s+)?report\s*(?:no\.?|number)?\s*[:\-]?\s*([\w/\-]+)',
    ]
    fir_number = ""
    conf_fir_number = 0.0
    for _pat in _fir_patterns:
        _m = re.search(_pat, full_text, re.IGNORECASE)
        if _m:
            fir_number = _m.group(1).strip().upper()
            fir_number = re.sub(r'[^A-Z0-9/\-\s]', '', fir_number).strip()
            conf_fir_number = 0.85
            break
    if not fir_number and tabular_fields.get("fir_number"):
        fir_number = tabular_fields["fir_number"]
        conf_fir_number = 0.90

    # 10b. Policy Number
    _policy_patterns = [
        r'\bpolicy\s*(?:no\.?|number|#)\s*[:\-]?\s*([\w\-\./]+)',
        r'\bpolicy\s+bearing\s*(?:no\.?|number)?\s*[:\-]?\s*([\w\-\./]+)',
        r'\binsurance\s+policy\s*(?:no\.?|number|#)\s*[:\-]?\s*([\w\-\./]+)',
        r'\bcover\s*(?:note)?\s*(?:no\.?|number)?\s*[:\-]?\s*([\w\-\./]+)',
    ]
    policy_number = ""
    conf_policy_number = 0.0
    for _pat in _policy_patterns:
        _m = re.search(_pat, full_text, re.IGNORECASE)
        if _m:
            policy_number = _m.group(1).strip()
            policy_number = re.sub(r'[^a-zA-Z0-9\-\./\s]', '', policy_number).strip()
            conf_policy_number = 0.85
            break
    if not policy_number and tabular_fields.get("policy_number"):
        policy_number = tabular_fields["policy_number"]
        conf_policy_number = 0.90

    # 10c. Vehicle / Registration Number (Indian format: AB 00 CD 0000)
    _veh_num_re = r'[A-Za-z|l|I|1]{2}[\s\-\.]?\d{1,2}[\s\-\.]?[A-Za-z0-9|l|I|1]{1,4}[\s\-\.]?\d{1,4}'
    _vehicle_patterns = [
        rf'\b(?:vehicle|veh\.?)\s*(?:reg(?:istration)?\.?)?\s*(?:no\.?|number)\s*[:\-]?\s*({_veh_num_re})',
        rf'\breg(?:istration)?\.?\s*(?:no\.?|number)\s*[:\-]?\s*({_veh_num_re})',
        rf'\bbearing\s+(?:reg(?:istration)?\.?\s*)?(?:no\.?|number)\s*[:\-]?\s*({_veh_num_re})',
        rf'(?:car|truck|bus|lorry|motorcycle|bike|tempo|jeep|auto|motor\s*cycle)\s*(?:no\.?|number|bearing)?\s*[:\-]?\s*({_veh_num_re})',
        rf'\boffending\s+vehicle\b.*?({_veh_num_re})',
    ]
    vehicle_number = ""
    conf_vehicle_number = 0.0
    for _pat in _vehicle_patterns:
        _m = re.search(_pat, full_text, re.IGNORECASE)
        if _m:
            raw_veh = _m.group(1).strip().upper()
            cleaned_veh = re.sub(r'[^A-Z0-9\-\s\.]', '', raw_veh)
            vehicle_number = re.sub(r'\s+', ' ', cleaned_veh).strip()
            conf_vehicle_number = 0.85
            break
    if not vehicle_number and tabular_fields.get("vehicle_number"):
        _veh_raw = tabular_fields["vehicle_number"]
        _veh_m = re.search(_veh_num_re, _veh_raw, re.IGNORECASE)
        vehicle_number = _veh_m.group(0).upper() if _veh_m else _veh_raw
        vehicle_number = re.sub(r'[^A-Z0-9\-\s\.]', '', vehicle_number).strip()
        conf_vehicle_number = 0.90

    # 10d. Insurance Company
    _known_insurers = [
        "national insurance", "oriental insurance", "new india assurance",
        "united india insurance", "bajaj allianz", "hdfc ergo", "icici lombard",
        "reliance general", "tata aig", "cholamandalam", "future generali",
        "iffco tokio", "universal sompo", "royal sundaram", "magma hdi",
        "shriram general", "sbi general", "go digit", "acko general",
        "united india", "oriental insurance co", "national insurance co",
        "chola ms", "icici lombard general", "bajaj allianz general",
        "tata aig general", "reliance general insurance", "sbi general insurance",
        "iffco-tokio", "shriram general insurance"
    ]
    insurance_company = ""
    conf_insurance_company = 0.0
    for _ins_name in _known_insurers:
        if _ins_name.lower() in full_text_lower:
            _ins_m = re.search(
                rf'({re.escape(_ins_name)}[A-Za-z\s\.\,&]*?(?:co\.?|ltd\.?|corporation|company|insurance)?)',
                full_text, re.IGNORECASE
            )
            if _ins_m:
                insurance_company = _ins_m.group(1).strip().title()
                insurance_company = re.sub(r'[^a-zA-Z\s\.\,\&]', '', insurance_company).strip()
                conf_insurance_company = 0.90
                break
    if not insurance_company:
        _ins_patterns = [
            r'(?:insurance\s+company|insurer)\s*[:\-]\s*([A-Za-z][A-Za-z\s\.\,&]+?(?:ltd\.?|limited|corporation|co\.?|company))(?:\.|,|\n|$)',
            r'(?:respondent|opposite\s+party)\s*(?:no\.?\s*\d+)?\s*[:\-]\s*([A-Za-z][A-Za-z\s\.\,&]*?insurance(?:\s+(?:co(?:mpany)?|ltd|limited|corp|corporation))?)\b',
        ]
        for _pat in _ins_patterns:
            _ins_m = re.search(_pat, full_text, re.IGNORECASE)
            if _ins_m:
                _cand = _ins_m.group(1).strip()
                if len(_cand) <= 60:
                    insurance_company = _cand.title()
                    insurance_company = re.sub(r'[^a-zA-Z\s\.\,\&]', '', insurance_company).strip()
                    conf_insurance_company = 0.75
                    break
    if not insurance_company and tabular_fields.get("insurance_company"):
        _ins_tab_val = tabular_fields["insurance_company"]
        if not re.search(r'[|\[\]{}\\]', _ins_tab_val) and _ins_tab_val.isascii() and len(_ins_tab_val) <= 80:
            insurance_company = _ins_tab_val
            insurance_company = re.sub(r'[^a-zA-Z\s\.\,\&]', '', insurance_company).strip()
            conf_insurance_company = 0.85

    # 10e. Prayer Amount / Prayer Section
    prayer_patterns = [
        r'(?:prayer|relief\s+claimed|claims?\s+compensation\s+of|prays\s+for)\s*(?:rs\.?|inr)?\s*([\d,\.\s]+lakhs?|[\d,\.\-\/]+)\b',
        r'\b(?:claims?\s+sum\s+of|seeking\s+compensation\s+of)\s*(?:rs\.?|inr)?\s*([\d,\.\-\/]+)\b'
    ]
    prayer, conf_prayer, sec_prayer, page_prayer = contextual_extract(
        prayer_patterns, sections, [("relief_section", 95)], default_val="", type_cast=str,
        field_name="prayer", debug_info=parser_debug, pages=pages, sections_metadata=sections_metadata, page_importances=page_importances
    )
    method_prayer = "Section-Aware Contextual Regex"

    # ======================================================
    # CHRONOLOGICAL DATES EXTRACTION
    # ======================================================
    
    chronology = parse_chronological_events(
        sections.get("chronological_events_section", "")
        or sections.get("memo_of_appeal_section", "")
        or sections.get("index_section", "")
        or full_text
    )
    
    # Accident Date
    if block_date:
        date_of_accident = block_date
        conf_date_of_accident = 0.99
        sec_date_of_accident = "particulars_block"
        page_date_of_accident = 1
        method_date_of_accident = "High Court Particulars Block"
    else:
        date_of_accident = chronology["date_of_accident"]
        if date_of_accident:
            conf_date_of_accident = 0.98
            sec_date_of_accident = "chronological_events_section"
            sec_meta = sections_metadata.get("chronological_events_section", {})
            page_date_of_accident = find_exact_page(date_of_accident, sec_meta.get("start_page", 1), sec_meta.get("end_page", 1), pages)
            method_date_of_accident = "Chronological Event Extraction"
        else:
            date_of_accident = ""
            conf_date_of_accident = 0.40
            sec_date_of_accident = "raw_ocr"
            page_date_of_accident = 1
            method_date_of_accident = "Fallback Contextual Search"
            
            acc_dates = extract_dates_with_context(sections.get("claimant_section", "") or full_text)
            for d_val, ctx in acc_dates:
                if any(kw in ctx for kw in ["accident", "incident", "occurrence", "happened on", "occurred on", "collision", "crash", "fir"]):
                    date_of_accident = d_val
                    conf_date_of_accident = 0.95
                    sec_date_of_accident = "claimant_section" if d_val in sections.get("claimant_section", "") else "raw_ocr"
                    page_date_of_accident = find_exact_page(d_val, 1, 10, pages)
                    break

    # Award Date
    award_date = chronology["award_date"]
    if award_date:
        conf_award_date = 0.98
        sec_award_date = "chronological_events_section"
        sec_meta = sections_metadata.get("chronological_events_section", {})
        page_award_date = find_exact_page(award_date, sec_meta.get("start_page", 1), sec_meta.get("end_page", 1), pages)
        method_award_date = "Chronological Event Extraction"
    else:
        award_date = ""
        conf_award_date = 0.40
        sec_award_date = "raw_ocr"
        page_award_date = 1
        method_award_date = "Fallback Contextual Search"
        
        aw_dates = extract_dates_with_context(
            sections.get("award_copy_section", "")
            or sections.get("memo_of_appeal_section", "")
            or full_text
        )
        for d_val, ctx in aw_dates:
            if any(kw in ctx for kw in ["passed", "disposed", "decided", "judgment", "award", "decree", "order"]):
                award_date = d_val
                conf_award_date = 0.95
                sec_award_date = "award_copy_section" if d_val in sections.get("award_copy_section", "") else ("memo_of_appeal_section" if d_val in sections.get("memo_of_appeal_section", "") else "raw_ocr")
                page_award_date = find_exact_page(d_val, 1, 10, pages)
                break

    # Birth Date
    date_of_birth = ""
    conf_date_of_birth = 0.40
    sec_date_of_birth = "raw_ocr"
    page_date_of_birth = 1
    method_date_of_birth = "Fallback Contextual Search"
    
    # Bug 1 Fix: Only match DOB directly following a valid label via regex
    dob_target_text = sections.get("claimant_section", "")
    dob_match = re.search(
        r'\b(?:date\s+of\s+birth|dob|d\.o\.b\.?|born\s+on|birth\s+date)\s*[:\-]?\s*(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{4})\b',
        dob_target_text,
        re.IGNORECASE
    )
    if not dob_match:
        # Fallback to full_text but must be direct label match
        dob_match = re.search(
            r'\b(?:date\s+of\s+birth|dob|d\.o\.b\.?|born\s+on|birth\s+date)\s*[:\-]?\s*(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{4})\b',
            full_text,
            re.IGNORECASE
        )
    if dob_match:
        d_val = f"{int(dob_match.group(1)):02d}-{int(dob_match.group(2)):02d}-{dob_match.group(3)}"
        date_of_birth = d_val
        conf_date_of_birth = 0.95
        sec_date_of_birth = "claimant_section" if d_val in (sections.get("claimant_section", "") or "") else "raw_ocr"
        page_date_of_birth = find_exact_page(d_val, 1, 10, pages)
        method_date_of_birth = "Direct Label Pattern Matching"

    # Tabular form fallback for date_of_birth
    if not date_of_birth and tabular_fields.get("date_of_birth"):
        _dob_raw = tabular_fields["date_of_birth"]
        _dob_m = re.search(r'(\d{1,2})[/\.\-](\d{1,2})[/\.\-](\d{4})', _dob_raw)
        if _dob_m:
            date_of_birth = f"{int(_dob_m.group(1)):02d}-{int(_dob_m.group(2)):02d}-{_dob_m.group(3)}"
            conf_date_of_birth = 0.90
            sec_date_of_birth = "tabular_form"
            page_date_of_birth = 1
            method_date_of_birth = "Tabular Form Extraction"

    # Tabular form fallback for date_of_accident
    if not date_of_accident and tabular_fields.get("date_of_accident"):
        _doa_raw = tabular_fields["date_of_accident"]
        _doa_m = re.search(r'(\d{1,2})[/\.\-](\d{1,2})[/\.\-](\d{4})', _doa_raw)
        if _doa_m:
            date_of_accident = f"{int(_doa_m.group(1)):02d}-{int(_doa_m.group(2)):02d}-{_doa_m.group(3)}"
            conf_date_of_accident = 0.90
            sec_date_of_accident = "tabular_form"
            page_date_of_accident = 1
            method_date_of_accident = "Tabular Form Extraction"

    # Tabular form fallback for claimant_name / deceased_name
    if not claimant_name and tabular_fields.get("claimant_name"):
        _cn_raw = clean_legal_name(tabular_fields["claimant_name"])
        if _cn_raw and len(_cn_raw) > 2:
            claimant_name = _cn_raw.title()
            conf_claimant_name = max(conf_claimant_name, 0.88)
            sec_claimant_name = "tabular_form"
            page_claimant_name = 1
            method_claimant_name = "Tabular Form Extraction"
    if not deceased_name and tabular_fields.get("deceased_name"):
        _dn_raw = clean_legal_name(tabular_fields["deceased_name"])
        if _dn_raw and len(_dn_raw) > 2:
            deceased_name = _dn_raw.title()
            conf_deceased_name = max(conf_deceased_name, 0.88)
            sec_deceased_name = "tabular_form"
            page_deceased_name = 1
            method_deceased_name = "Tabular Form Extraction"

    # Tabular form fallback for monthly_income
    if not monthly_income and tabular_fields.get("monthly_income"):
        _inc_val = parse_indian_rupee_value(tabular_fields["monthly_income"])
        if _inc_val > 0:
            monthly_income = _inc_val
            conf_monthly_income = 0.88
            sec_monthly_income = "tabular_form"
            page_monthly_income = 1
            method_monthly_income = "Tabular Form Extraction"

    # Tabular form fallback for dependents
    if not dependents and tabular_fields.get("dependents"):
        _dep_m = re.search(r'(\d{1,2})', tabular_fields["dependents"])
        if _dep_m:
            dependents = int(_dep_m.group(1))
            conf_dependents = 0.88
            sec_dependents = "tabular_form"
            page_dependents = 1
            method_dependents = "Tabular Form Extraction"

    # Tabular form fallback for marital_status
    if conf_marital_status < 0.70 and tabular_fields.get("marital_status"):
        _ms_raw = tabular_fields["marital_status"].lower()
        if any(kw in _ms_raw for kw in ["married", "husband", "wife", "spouse"]):
            marital_status = "married"
            conf_marital_status = 0.88
            sec_marital_status = "tabular_form"
            method_marital_status = "Tabular Form Extraction"
        elif any(kw in _ms_raw for kw in ["single", "unmarried", "bachelor", "spinster"]):
            marital_status = "single"
            conf_marital_status = 0.88
            sec_marital_status = "tabular_form"
            method_marital_status = "Tabular Form Extraction"

    # ======================================================
    # NORMALIZATION & VALIDATION (unchanged legal logic)
    # ======================================================
    expected_multiplier = 0
    expected_prospects = 0.0
    
    if isinstance(age, int) and age > 0:
        if age <= 15: expected_multiplier = 20
        elif age <= 25: expected_multiplier = 18
        elif age <= 30: expected_multiplier = 17
        elif age <= 35: expected_multiplier = 16
        elif age <= 40: expected_multiplier = 15
        elif age <= 45: expected_multiplier = 14
        elif age <= 50: expected_multiplier = 13
        elif age <= 55: expected_multiplier = 11
        elif age <= 60: expected_multiplier = 9
        elif age <= 65: expected_multiplier = 7
        else: expected_multiplier = 5
        
        if age < 40: expected_prospects = 40.0
        elif age < 50: expected_prospects = 25.0
        elif age < 60: expected_prospects = 10.0
        else: expected_prospects = 0.0

    award_block_english = "\n".join(
        line for line in award_block.splitlines()
        if is_hindi_doc or not _is_predominantly_devanagari(line)
    )
    compensation_table = parse_compensation_table(award_block_english)
    
    # Synchronize table extraction values with compensation_table
    if not compensation_table:
        compensation_table = {}
    for k, v in comp_fields.items():
        if v and k not in ["monthly_income", "monthly_income_method", "multiplier", "future_prospect", "deduction", "total_compensation"]:
            head_title = k.replace("_", " ").title()
            compensation_table[head_title] = v

    # Classification logic — properly engineered, section-aware classifier.
    # See classify_enhancement_or_reduction() for the grounds/relief-clause
    # based logic. We keep a simplified scalar (`enhancement_reduction_request`)
    # for backward compatibility with the existing legal_ai_summary text below.
    case_classification = classify_enhancement_or_reduction(sections)
    if case_classification["verdict"] == "reduction":
        enhancement_reduction_request = "reduction"
    else:
        # Treat "not_determinable" as "enhancement" ONLY for the purposes of
        # the legacy summary sentence wording below, since that sentence
        # assumes a binary outcome. The real, accurate verdict (including
        # "not_determinable") is preserved separately in case_classification
        # and surfaced to the UI as-is.
        enhancement_reduction_request = "enhancement"

    if case_type is None:
        from backend.llm_client import classify_case_type_by_ocr_text
        case_type = classify_case_type_by_ocr_text(full_text)

    if case_type == "death":
        disability = ""
        conf_disability = 0.0

    # ==========================================
    # DEATH-CASE IDENTITY CORRECTION PASS
    # ==========================================
    if case_type == "death":
        prayer_grounds_text = (sections.get("relief_section", "") + " " + sections.get("grounds_section", "")).strip()
        
        pg_deceased_name = None
        for pat in [
            r'\b(?:the\s+)?deceased,?\s+(?:shri|smt|late)?\s*([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,3})',
            r'\bdeath\s+of\s+(?:shri|smt|late)?\s*([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,3})',
            r'\blate\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,3})'
        ]:
            for m in re.finditer(pat, prayer_grounds_text):
                cand = clean_legal_name(m.group(1).strip())
                if cand and len(cand) > 2:
                    pg_deceased_name = cand.title()
                    break
            if pg_deceased_name:
                break
                
        pg_age = None
        target_deceased_name = pg_deceased_name or deceased_name
        if target_deceased_name:
            name_tokens = [t for t in target_deceased_name.split() if len(t) > 2]
            if name_tokens:
                search_term = name_tokens[0]
                pos = 0
                while True:
                    idx = prayer_grounds_text.lower().find(search_term.lower(), pos)
                    if idx == -1:
                        break
                    w_start = max(0, idx - 150)
                    w_end = min(len(prayer_grounds_text), idx + len(search_term) + 150)
                    window = prayer_grounds_text[w_start:w_end]
                    for pat in [
                        r'\b(?:is|was|aged?)\s*(?:about|around)?\s*(\d{1,2})\s*years?\s*old\b',
                        r'\baged\s+about\s+(\d{1,2})\s*years\b',
                        r'\bage\s+of\s+the\s+deceased\s+was\s+(\d{1,2})\b',
                        r'\bage\s+of\s+deceased\s+was\s+(\d{1,2})\b',
                        r'\baged\s+(\d{1,2})\s*years\b',
                        r'\baged\s+about\s+(\d{1,2})\b',
                        r'\bage\s*[:\-]\s*(\d{1,2})\b',
                        r'\b(\d{1,2})\s*years?\s*old\b',
                        r'\baged\s+(\d{1,2})\b',
                        r'\b(\d{1,2})\s*(?:years|yrs)\b',
                    ]:
                        age_m = re.search(pat, window, re.IGNORECASE)
                        if age_m:
                            val = int(age_m.group(1))
                            if 5 <= val <= 100:
                                pg_age = val
                                break
                    if pg_age:
                        break
                    pos = idx + len(search_term)

        # Apply new extraction if found
        if pg_deceased_name:
            deceased_name = pg_deceased_name
            conf_deceased_name = 0.99
            sec_deceased_name = "relief_section" if pg_deceased_name in sections.get("relief_section", "") else "grounds_section"
            sec_meta = sections_metadata.get(sec_deceased_name, {})
            page_deceased_name = find_exact_page(deceased_name, sec_meta.get("start_page", 1), sec_meta.get("end_page", 1), pages)
            method_deceased_name = "Prayer/Grounds Extraction (Death Case)"
            
        if pg_age:
            age = pg_age
            conf_age = 0.99
            sec_age = "relief_section" if str(pg_age) in sections.get("relief_section", "") else "grounds_section"
            sec_meta = sections_metadata.get(sec_age, {})
            page_age = find_exact_page(str(age), sec_meta.get("start_page", 1), sec_meta.get("end_page", 1), pages)
            method_age = "Prayer/Grounds Extraction (Death Case)"
            
            if isinstance(age, int) and age > 0:
                if age <= 15: expected_multiplier = 20
                elif age <= 25: expected_multiplier = 18
                elif age <= 30: expected_multiplier = 17
                elif age <= 35: expected_multiplier = 16
                elif age <= 40: expected_multiplier = 15
                elif age <= 45: expected_multiplier = 14
                elif age <= 50: expected_multiplier = 13
                elif age <= 55: expected_multiplier = 11
                elif age <= 60: expected_multiplier = 9
                elif age <= 65: expected_multiplier = 7
                else: expected_multiplier = 5
                
                if age < 40: expected_prospects = 40.0
                elif age < 50: expected_prospects = 25.0
                elif age < 60: expected_prospects = 10.0
                else: expected_prospects = 0.0

        if father_name and deceased_name and clean_legal_name(father_name).lower() == clean_legal_name(deceased_name).lower():
            father_name = ""
            conf_father_name = 0.0
            method_father_name = "Rejected (Matches Deceased)"
        elif sec_father_name == "claimant_section":
            father_name = ""
            conf_father_name = 0.0
            method_father_name = "Rejected (Claimant Section)"

    tn_mcop_signal = bool(re.search(r'\bm\.?c\.?o\.?p\.?\b', full_text_lower))
    tn_city_keywords = ["high court of madras", "chennai", "coimbatore", "madurai", "salem", "trichy", "pondicherry", "tribunal, tamil nadu", "madras high court"]
    tn_city_signal = any(kw in full_text_lower for kw in tn_city_keywords)
    is_tamil_nadu = tn_mcop_signal and tn_city_signal
        
    mcop_number = ""
    tn_disability_compensation = 0.0
    if is_tamil_nadu:
        mcop_match = re.search(r'\b(?:m\.?c\.?o\.?p\.?|m\.c\.o\.p\.?)\s*(?:no\.?|case\s+no\.?)?\s*(\d+\s*(?:of|\/)\s*\d{4})\b', full_text_lower)
        if mcop_match:
            mcop_number = f"M.C.O.P. No. {mcop_match.group(1).upper()}"
            
        if case_type == "injury" and disability:
            accident_year = 2020
            if date_of_accident:
                try:
                    accident_year = int(date_of_accident.split("-")[2])
                except (ValueError, IndexError):
                    pass
            flat_rate = 5000.0 if accident_year >= 2020 else 3000.0
            tn_disability_compensation = disability * flat_rate
            
            if not compensation_table:
                compensation_table = {
                    "Disability Compensation": tn_disability_compensation,
                    "Pain And Suffering": 40000.0,
                    "Loss Of Amenities": 30000.0,
                    "Transportation Charges": 15000.0,
                    "Extra Nourishment": 15000.0,
                    "Attender Charges": 15000.0
                }

    anomalies_detected = []
    
    if date_of_birth and date_of_accident:
        try:
            dob_val = datetime.strptime(date_of_birth, "%d-%m-%Y")
            doa_val = datetime.strptime(date_of_accident, "%d-%m-%Y")
            if dob_val > doa_val:
                date_of_birth, date_of_accident = date_of_accident, date_of_birth
                conf_date_of_birth, conf_date_of_accident = conf_date_of_accident, conf_date_of_birth
                anomalies_detected.append("Chronological date swap repaired (DOB was after Accident Date).")
        except ValueError:
            pass

    if multiplier and expected_multiplier:
        if multiplier != expected_multiplier:
            anomalies_detected.append(f"Tribunal applied multiplier {multiplier} which deviates from Sarla Verma standard ({expected_multiplier}) for age {age}.")

    if date_of_birth and date_of_accident:
        try:
            dob_val = datetime.strptime(date_of_birth, "%d-%m-%Y")
            doa_val = datetime.strptime(date_of_accident, "%d-%m-%Y")
            calc_age = doa_val.year - dob_val.year
            if doa_val.month < dob_val.month or (doa_val.month == dob_val.month and doa_val.day < dob_val.day):
                calc_age -= 1
            if 0 <= calc_age <= 100:
                if age != calc_age:
                    age = calc_age
                    conf_age = max(conf_age, 0.90)
                    anomalies_detected.append("Age synchronized chronologically to match DOB & accident date.")
        except ValueError:
            pass

    functional_disability_keywords = [
        "loss of earning capacity", "inability to work", "unable to continue", "reduced earning",
        "loss of future earning", "functional disability", "earning capacity reduced",
        "affecting earning", "loss of earning ability", "multiplier method"
    ]
    has_functional_disability = bool(disability) and any(kw in full_text_lower for kw in functional_disability_keywords)

    reconstruction_keywords = [
        "loss of future income", "future income loss", "earning capacity", "earning capacity reduction",
        "affecting earning", "loss of earning capacity", "multiplier method", "future prospects",
        "sarla verma", "pranay sethi", "loss of dependency", "dependency loss"
    ]
    can_reconstruct = any(kw in full_text_lower for kw in reconstruction_keywords)
    
    compensation_mode = "simple_injury_award"
    if case_type == "death":
        compensation_mode = "death_case_formula"
    else:
        if disability and has_functional_disability:
            compensation_mode = "permanent_disability_formula"
        elif any(kw in full_text_lower for kw in ["lump sum", "lumpsum", "consolidated", "globally"]):
            compensation_mode = "lump_sum_award"
        else:
            compensation_mode = "simple_injury_award"

    reconstruction_triggered = False
    reconstructed_compensation = 0.0
    reconstruction_trigger_reason = "can_reconstruct=False (no explicit legal discussion)"

    if monthly_income and age and can_reconstruct:
        try:
            inc_val = float(monthly_income)
            mult_val = int(multiplier) if multiplier else expected_multiplier

            if compensation_mode == "death_case_formula":
                pros_pct = float(future_prospect) if future_prospect else expected_prospects
                enhanced_monthly = inc_val * (1.0 + pros_pct / 100.0)
                annual_inc = enhanced_monthly * 12.0
                deduct_pct = get_personal_deduction_pct(marital_status, dependents)
                family_contribution = annual_inc * (1.0 - deduct_pct)
                loss_of_dependency = family_contribution * mult_val
                reconstructed_compensation = loss_of_dependency + consortium + funeral_expenses + estate_loss
                reconstruction_trigger_reason = f"death_case_formula: loss_dep={int(loss_of_dependency)}, consortium={consortium}, funeral={funeral_expenses}"

            elif compensation_mode == "permanent_disability_formula":
                annual_inc = inc_val * 12.0
                dis_pct = float(disability) if disability else 0.0
                future_income_loss = annual_inc * (dis_pct / 100.0) * mult_val
                med_exp = float(compensation_table.get("Medical Expenses", compensation_table.get("Disability Compensation", 0.0)))
                pain_suf = float(compensation_table.get("Pain And Suffering", 0.0))
                trans = float(compensation_table.get("Transportation Charges", 0.0))
                diet = float(compensation_table.get("Extra Nourishment", 0.0))
                attender = float(compensation_table.get("Attender Charges", 0.0))
                loss_inc = float(compensation_table.get("Loss Of Income", 0.0))
                reconstructed_compensation = future_income_loss + med_exp + pain_suf + trans + diet + attender + loss_inc
                reconstruction_trigger_reason = f"permanent_disability_formula: future_income_loss={int(future_income_loss)}, dis={dis_pct}%, mult={mult_val}"

            if total_compensation and reconstructed_compensation > 0:
                diff = abs(total_compensation - reconstructed_compensation) / total_compensation
                if diff > 0.05:
                    reconstruction_triggered = True
                    anomalies_detected.append(
                        f"Compensation mismatch detected: Tribunal Award Rs. {int(total_compensation):,} vs Reconstructed Math Rs. {int(reconstructed_compensation):,}."
                    )
        except Exception as e:
            logger.error(f"Validation math error: {str(e)}")

    if reconstructed_compensation <= 0:
        table_sum = sum(compensation_table.values()) if compensation_table else 0.0
        if table_sum > 0:
            reconstructed_compensation = table_sum

    # AI Recovery Fallback
    ai_recovery_triggered = False
    fields_missing = not claimant_name or not monthly_income or not age or not total_compensation
    if fields_missing or reconstruction_triggered:
        ai_recovery_triggered = True
        
        recovered = real_text_recovery(
            petition_block,
            prayer_block,
            award_block,
            award_block,
            case_type
        )
        
        if not claimant_name and recovered.get("name"):
            claimant_name = recovered["name"]
            conf_claimant_name = 0.85
            sec_claimant_name = "AI Recovery"
            page_claimant_name = 1
            method_claimant_name = "AI RealTextRecovery Fallback"
            
        if not age and recovered.get("age"):
            age = recovered["age"]
            conf_age = 0.85
            sec_age = "AI Recovery"
            page_age = 1
            method_age = "AI RealTextRecovery Fallback"
            
        if not monthly_income and recovered.get("monthly_income"):
            monthly_income = recovered["monthly_income"]
            conf_monthly_income = 0.85
            sec_monthly_income = "AI Recovery"
            page_monthly_income = 1
            method_monthly_income = "AI RealTextRecovery Fallback"
            
        if not dependents and recovered.get("dependents"):
            dependents = recovered["dependents"]
            conf_dependents = 0.85
            sec_dependents = "AI Recovery"
            page_dependents = 1
            method_dependents = "AI RealTextRecovery Fallback"
            
        if (not total_compensation or total_compensation <= 0 or conf_total_compensation < 0.70) and recovered.get("award_amount"):
            total_compensation = recovered["award_amount"]
            conf_total_compensation = 0.85
            sec_total_compensation = "AI Recovery"
            page_total_compensation = 1
            method_total_compensation = "AI RealTextRecovery Fallback"

        if not age and date_of_birth and date_of_accident:
            try:
                dob_val = datetime.strptime(date_of_birth, "%d-%m-%Y")
                doa_val = datetime.strptime(date_of_accident, "%d-%m-%Y")
                age = doa_val.year - dob_val.year
                conf_age = 0.80
                sec_age = "raw_ocr"
                page_age = 1
                method_age = "Date Chronology Sync Fallback"
            except ValueError:
                pass
                
        if not age:
            if case_type == "death":
                # For death cases, avoid raw 'age is 35' in claimant lists
                m = re.search(
                    r'\b(?:deceased|victim|deceased\s+person|description\s+of\s+deceased)\b.*?\b(?:age|aged)\s*(?:about|is|was)?\s*[:\-;]?\s*(\d{1,2})\b',
                    petition_block.lower(),
                    re.IGNORECASE | re.DOTALL
                )
                if not m:
                    m = re.search(
                        r'\b(?:age|aged)\s+of\s+(?:the\s+)?(?:deceased|victim)\s+(?:was|is)?\s*[:\-]?\s*(\d{1,2})\b',
                        petition_block.lower(),
                        re.IGNORECASE
                    )
            else:
                m = re.search(r'\b(?:age|aged)\s*(?:about|is)?\s*(\d{1,2})\b', petition_block.lower())
            if m:
                age = int(m.group(1))
                conf_age = 0.75
                sec_age = "petition_block"
                page_age = 1
                method_age = "Local Age Regex Fallback"

        if not occupation:
            occ_keywords = ["service", "driver", "agriculture", "farmer", "supervisor", "teacher", "business", "laborer", "coolie", "shopkeeper", "student", "housewife"]
            for occ in occ_keywords:
                if occ in petition_block.lower():
                    occupation = occ.title()
                    conf_occupation = 0.70
                    sec_occupation = "petition_block"
                    page_occupation = 1
                    method_occupation = "Keyword Extraction Fallback"
                    break

        if not monthly_income:
            m = re.search(r'\b(?:income|salary|wage|earning|earns)\b\s*(?:is|was|of|@)?\s*(?:rs\.?|inr|rupees)?\s*([\d,]{4,10})\b', petition_block.lower())
            if not m:
                m = re.search(r'\b(?:income|salary|wage|earning|earns)\b.*?([\d,]{4,10})\b', petition_block.lower())
            if m:
                monthly_income = parse_indian_rupee_value(m.group(1))
                conf_monthly_income = 0.75
                sec_monthly_income = "petition_block"
                page_monthly_income = 1
                method_monthly_income = "Regex Local Income Fallback"

        if case_type == "death" and (not monthly_income or monthly_income <= 0) and total_compensation and total_compensation > 0:
            monthly_income = deduce_notional_income(
                total_compensation, 
                age, 
                marital_status, 
                dependents, 
                future_prospect, 
                multiplier,
                award_date=award_date
            )
            if monthly_income > 0:
                conf_monthly_income = 0.80
                sec_monthly_income = "algebraic_fallback"
                page_monthly_income = 1
                method_monthly_income = "Algebraic Notional Income Deduction"

        if not multiplier and expected_multiplier:
            multiplier = expected_multiplier
            conf_multiplier = 0.70
            sec_multiplier = "raw_ocr"
            page_multiplier = 1
            method_multiplier = "Age expected multiplier sync"

        if not future_prospect and expected_prospects:
            future_prospect = expected_prospects
            conf_future_prospect = 0.70
            sec_future_prospect = "raw_ocr"
            page_future_prospect = 1
            method_future_prospect = "Age expected prospects sync"

        if not prayer:
            prayers_kws = ["appeal allowed", "compensation be enhanced", "enhanced", "award be passed", "prays for"]
            for p_kw in prayers_kws:
                if p_kw in prayer_block.lower():
                    prayer = f"The claimant prays that the {p_kw}."
                    conf_prayer = 0.70
                    sec_prayer = "prayer_block"
                    page_prayer = 1
                    method_prayer = "Keyword Extraction Fallback"
                    break

        excessive_deviation = False
        if total_compensation and reconstructed_compensation > 0:
            ratio = float(reconstructed_compensation) / float(total_compensation)
            if ratio > 3.0 or ratio < (1.0 / 3.0):
                excessive_deviation = True
                anomalies_detected.append(
                    f"Excessive math deviation: Reconstructed formula (Rs. {int(reconstructed_compensation):,}) is >3x or <1/3x of Tribunal Award (Rs. {int(total_compensation):,})."
                )

        if (not total_compensation or total_compensation <= 0 or (conf_total_compensation < 0.70 and not excessive_deviation)) and reconstructed_compensation > 0:
            total_compensation = round(reconstructed_compensation, 2)
            conf_total_compensation = 0.80
            sec_total_compensation = "award_block"
            page_total_compensation = 1
            method_total_compensation = "Reconstructed Math Sync"

        if excessive_deviation:
            conf_total_compensation = min(conf_total_compensation, 0.60)
            reconstruction_trigger_reason = f"excessive_deviation_clamped"

    award_validation_ratio = 0.0
    if total_compensation and reconstructed_compensation > 0:
        try:
            award_validation_ratio = round(float(reconstructed_compensation) / float(total_compensation), 3)
        except Exception:
            pass

    parser_debug["_meta"] = {
        "functional_disability_detected": has_functional_disability,
        "can_reconstruct": can_reconstruct,
        "compensation_mode": compensation_mode,
        "reconstruction_trigger_reason": reconstruction_trigger_reason,
        "reconstruction_triggered": reconstruction_triggered,
        "award_validation_ratio": award_validation_ratio,
        "section_confidence": {
            "petition_block": round(len(petition_block) / max(len(full_text), 1), 3),
            "prayer_block": round(len(prayer_block) / max(len(full_text), 1), 3),
            "award_block": round(len(award_block) / max(len(full_text), 1), 3),
            "facts_block": round(len(facts_block) / max(len(full_text), 1), 3)
        },
        "is_tamil_nadu": is_tamil_nadu,
        "tn_signals": {"mcop": tn_mcop_signal, "city": tn_city_signal} if is_tamil_nadu else {"mcop": tn_mcop_signal, "city": tn_city_signal}
    }

    # Citations
    citation_patterns = [
        r'\b\d{4}\s+(?:SCC|ACJ)\s+\d+\b',
        r'\(\d{4}\)\s+\d+\s+(?:SCC|ACJ)\s+\d+\b',
        r'\b(?:[A-Z][A-Za-z\s]+)\s+vs\.?\s+(?:[A-Z][A-Za-z\s]+)\b'
    ]
    known_precedents = ["Pranay Sethi", "Sarla Verma", "Satinder Kaur", "Syed Basheer Ahmed"]
    
    unique_citations = set()
    for pat in citation_patterns:
        m = re.findall(pat, full_text)
        for cite in m:
            unique_citations.add(cite.strip())
            
    for pred in known_precedents:
        if pred.lower() in full_text_lower:
            m = re.search(rf'([^.\n]*?{re.escape(pred)}[^.\n]*)', full_text, re.IGNORECASE)
            if m:
                unique_citations.add(m.group(1).strip())
            else:
                unique_citations.add(pred)
                
    citations = sorted(list(unique_citations))
    conf_citations = 0.95 if citations else 0.0

    deduct_pct = get_personal_deduction_pct(marital_status, dependents)
    dependency_deduction = round(deduct_pct * 100, 2)

    if not monthly_income: monthly_income = ""
    if not future_prospect: future_prospect = ""
    if not multiplier: multiplier = ""
    if not total_compensation: total_compensation = ""

    # Legal AI Summary
    summary_name = deceased_name if (case_type == "death" and deceased_name) else (claimant_name or "claimant")
    summary_case = "death" if case_type == "death" else "injury"
    summary_action = "enhancement" if enhancement_reduction_request == "enhancement" else "reduction"
    
    summary_blocks = [
        f"This appeal challenges the MACT motor claim compensation awarded for the {summary_case} of {summary_name}.",
        f"The profile involves a {age}-year-old individual, historically working as a {occupation or 'Worker'}."
    ]
    if is_tamil_nadu:
        summary_blocks.append(f"The case was identified as a Judicial System proceeding under {mcop_number or 'MCOP Tribunal'}.")
    if monthly_income:
        summary_blocks.append(f"The court evaluated a monthly income of Rs. {int(float(monthly_income)):,} per month.")
    if multiplier:
        summary_blocks.append(f"A multiplier of {multiplier} was applied in accordance with Sarla Verma standards.")
    if future_prospect:
        summary_blocks.append(f"Future prospects were calculated at {future_prospect}% following Pranay Sethi rules.")
    if total_compensation:
        summary_blocks.append(f"The total judicial compensation awarded stands at Rs. {int(float(total_compensation)):,}.")
    summary_blocks.append(f"The insurance/claimant appeal requests a {summary_action} of the compensation award.")
    if anomalies_detected:
        summary_blocks.append(f"Validation checks: {'; '.join(anomalies_detected)}")
    legal_ai_summary = " ".join(summary_blocks)

    # Set flat 'name' field for the calculator
    flat_name = claimant_name
    if case_type == "death" and deceased_name:
        flat_name = deceased_name

    # Helper to extract flat values from compensation_table
    def get_table_value(keys):
        for k in keys:
            for t_key, t_val in compensation_table.items():
                if k.lower() in t_key.lower():
                    return t_val
        return None

    # Map table/heuristic values to flat fields
    _raw_estate = get_table_value(["estate"]) or estate_loss
    loss_estate_val = _raw_estate if (_raw_estate and _raw_estate <= 50000) else (18150.0 if case_type == "death" else 0.0)
    
    # Granular consortium extraction
    extracted_conlum = get_table_value(["consortium-lumpsum", "lumpsum consortium", "consortium lumpsum"])
    extracted_conspo = get_table_value(["consortium-spouse", "spouse consortium", "consortium spouse", "consortium to spouse"])
    extracted_conpar = get_table_value(["consortium-parental", "parental consortium", "consortium parental", "parental"])
    extracted_conchil = get_table_value(["consortium-children", "children consortium", "consortium children"])
    extracted_conwif = get_table_value(["consortium-wife", "wife consortium", "consortium wife"])
    extracted_conmo = get_table_value(["consortium-mother", "mother consortium", "consortium mother"])
    extracted_confath = get_table_value(["consortium-father", "father consortium", "consortium father"])
    extracted_conhus = get_table_value(["consortium-husband", "husband consortium", "consortium husband"])
    extracted_conbro = get_table_value(["consortium-brother", "brother consortium", "consortium brother"])
    extracted_consis = get_table_value(["consortium-sister", "sister consortium", "consortium sister"])

    # Granular injury extraction
    extracted_coliti = get_table_value(["cost of litigation", "litigation cost", "litigation expense", "litigation"])
    extracted_misex = get_table_value(["miscellaneous expenditure", "miscellaneous expense", "miscellaneous"])
    extracted_loamiti = get_table_value(["loss of amenities", "loss of amenity", "amenities in life", "amenities"])
    extracted_lopmarri = get_table_value(["prospects of marriage", "prospect of marriage", "marriage prospects", "marriage"])
    extracted_loexlife = get_table_value(["expectation of life", "loss of expectation", "expectation"])
    extracted_loveaff = get_table_value(["love and affection", "love & affection"])
    extracted_lossofenjoy = get_table_value(["enjoyment of life", "loss of enjoyment"])

    extracted_future_medical = get_table_value([
        "future medical", "future treatment", "future medical expenses",
        "future medical cost", "future medical exp"
    ])
    extracted_medical = None
    for t_key, t_val in compensation_table.items():
        if "medical" in t_key.lower() and "future" not in t_key.lower():
            extracted_medical = t_val
            break
    if not extracted_medical:
        extracted_medical = get_table_value([
            "medical expenses", "medical exp", "medical bill", "medical cost",
            "hospital expenses", "hospital bill", "treatment expenses",
            "treatment cost", "medical", "hospitalisation",
            "expenses on treatment", "treatment",
            # Hindi
            "चिकित्सा व्यय", "चिकित्सीय व्यय", "इलाज व्यय",
            "उपचार व्यय", "इलाज पर खर्च", "चिकित्सा खर्च",
            "अस्पताल व्यय", "इलाज में खर्च"
        ])

    extracted_pain = get_table_value([
        "pain and suffering", "pain & suffering", "pain and agony",
        "pain, suffering", "physical pain", "mental agony",
        "pain and mental agony", "pain",
        # Hindi
        "शारीरिक एवं मानसिक पीडा", "शारीरिक एवं मानसिक कष्ट",
        "शारीरिक पीडा", "मानसिक पीडा", "पीडा कष्ट",
        "शारीरिक एवं मानसिक आघात", "कष्ट एवं पीड़ा"
    ])
    extracted_transport = get_table_value([
        "transport", "transportation", "conveyance", "travelling",
        "travel expenses", "travel charges", "conveyance charges",
        # Hindi
        "आवागमन", "परिवहन व्यय", "यातायात व्यय",
        "आने जाने का खर्च", "आवागमन व्यय", "आवागमन एवं पोष्टिक आहार"
    ])
    extracted_diet = get_table_value([
        "nourishment", "diet", "special diet", "nutritious diet",
        "extra nourishment", "nutritional", "food expenses",
        "special food", "diet charges",
        # Hindi
        "पोष्टिक आहार", "विशेष आहार", "पौष्टिक आहार",
        "विशिष्ट आहार", "आहार व्यय", "फल पोष्टिक आहार"
    ])
    extracted_attender = get_table_value([
        "attender", "attendant", "nursing", "nursing charges",
        "attendant charges", "attender charges", "nursing expenses",
        "care taker", "caretaker", "attendant fee",
        # Hindi
        "सहायक पर व्यय", "परिचारक व्यय", "सहायक व्यय",
        "देखभाल व्यय", "सहायक पर खर्च", "परिचारक पर व्यय"
    ])
    extracted_loss_income = get_table_value([
        "loss of income", "loss of earning", "loss of wages",
        "loss of salary", "loss of employment", "income loss",
        "earning capacity loss", "loss of work", "loss of earning capacity",
        "earning", "loss of income during", "loss of pay",
        # Hindi
        "आय की हानि", "आय हानि", "उपार्जन की क्षति",
        "इलाज के दौरान आय", "उपचार के दौरान आय की हानि",
        "भविष्य की आय हानि", "भावी उपार्जन की क्षति"
    ])

    # ── LLM Recovery Trigger for High Court Track ────────────────────────────
    # Trigger if case_type is unknown, or if any core field is missing or has confidence < 0.70
    ai_recovery_triggered = False
    ai_recovery_needed = False
    
    if get_table_value(["estate"]):
        conf_loss_estate = 0.90
        method_loss_estate = "Table Extraction"
    elif estate_loss:
        conf_loss_estate = conf_estate_loss if 'conf_estate_loss' in locals() else 0.80
        method_loss_estate = method_estate_loss if 'method_estate_loss' in locals() else "Heuristic Parser"
    else:
        conf_loss_estate = 0.50
        method_loss_estate = "Default Heuristic"
    
    def is_checklist_page(p_num):
        if not pages or p_num < 1 or p_num > len(pages):
            return False
        p_text = pages[p_num - 1].get("text", "").lower()
        return "scrutiny report" in p_text or "computer sheet" in p_text or "scrutiny sheet" in p_text

    try:
        if is_checklist_page(locals().get('page_deceased_name', 0)): conf_deceased_name = 0.60
        if is_checklist_page(locals().get('page_claimant_name', 0)): conf_claimant_name = 0.60
        if is_checklist_page(locals().get('page_age', 0)): conf_age = 0.60
        if is_checklist_page(locals().get('page_monthly_income', 0)): conf_monthly_income = 0.60
        if is_checklist_page(locals().get('page_total_compensation', 0)): conf_total_compensation = 0.60
        if is_checklist_page(locals().get('page_multiplier', 0)): conf_multiplier = 0.60
        if is_checklist_page(locals().get('page_future_prospect', 0)): conf_future_prospect = 0.60
        if is_checklist_page(locals().get('page_dependents', 0)): conf_dependents = 0.60
        if is_checklist_page(locals().get('page_marital_status', 0)): conf_marital_status = 0.60
        if is_checklist_page(locals().get('page_consortium', 0)): conf_consortium = 0.60
        if is_checklist_page(locals().get('page_funeral_expenses', 0)): conf_funeral_expenses = 0.60
    except Exception as e:
        logger.error(f"Error checking checklist pages: {e}")

    # Generic year validation to reject calendar years (like 2024) matched as compensation
    try:
        val_comp = float(total_compensation) if total_compensation else 0.0
    except (ValueError, TypeError):
        val_comp = 0.0
    if 1990 <= val_comp <= 2035:
        conf_total_compensation = 0.40

    # ── Pre-Recovery Validation Cross-checks ───────────────────────────────
    from backend.calculator import get_multiplier, get_future_prospect
    try:
        age_val = int(age) if age else None
    except (ValueError, TypeError):
        age_val = None
        
    if age_val is not None and multiplier is not None and multiplier != "":
        try:
            expected_mult = get_multiplier(age_val)
            if int(multiplier) != expected_mult:
                conf_multiplier = 0.40
                conf_age = 0.40
                logger.warning(f"[PRE-RECOVERY] Multiplier mismatch: age={age_val}, multiplier={multiplier}, expected={expected_mult}. Lowering confidence.")
        except Exception as e:
            logger.error(f"Error in pre-recovery multiplier validation: {e}")
            
    if age_val is not None and future_prospect not in (None, "", "null"):
        try:
            try:
                f_type = int(future_type)
            except (ValueError, TypeError):
                f_type = 2
            expected_prospect = get_future_prospect(age_val, f_type) * 100.0
            if abs(float(future_prospect) - expected_prospect) > 0.01:
                conf_future_prospect = 0.40
                conf_age = 0.40
                logger.warning(f"[PRE-RECOVERY] Future prospect mismatch: age={age_val}, prospect={future_prospect}%, expected={expected_prospect}%. Lowering confidence.")
        except Exception as e:
            logger.error(f"Error in pre-recovery future prospect validation: {e}")

    if case_type == "death":
        if (not deceased_name or conf_deceased_name < 0.70 or
            not age or conf_age < 0.70 or
            not monthly_income or conf_monthly_income < 0.70 or
            not total_compensation or conf_total_compensation < 0.70 or
            not multiplier or conf_multiplier < 0.70 or
            not future_prospect or conf_future_prospect < 0.70):
            ai_recovery_needed = True
    elif case_type == "injury":
        if (not claimant_name or conf_claimant_name < 0.70 or
            not age or conf_age < 0.70 or
            not monthly_income or conf_monthly_income < 0.70 or
            not total_compensation or conf_total_compensation < 0.70 or
            not disability or conf_disability < 0.70):
            ai_recovery_needed = True
    else:
        ai_recovery_needed = True
        
    consortium_claimants = None
    conf_consortium_claimants = 0.0
    method_consortium_claimants = "Default Heuristic"

    if ai_recovery_needed:
        ai_recovery_triggered = True
        logger.info("Triggering LLM data recovery for high court appeal document...")
        from backend.llm_client import ai_data_recovery
        recovered = ai_data_recovery(full_text, track="high_court", case_type=case_type)
        if recovered:
            # Cross-validate heuristic age against LLM multiplier to detect incorrect age extractions (e.g. child age)
            from backend.calculator import get_multiplier
            h_age = age
            l_mult = recovered.get("multiplier")
            if h_age and l_mult:
                try:
                    h_age_val = int(h_age)
                    l_mult_val = int(l_mult)
                    expected_mult = get_multiplier(h_age_val)
                    if expected_mult != l_mult_val:
                        l_age = recovered.get("age")
                        if l_age and int(l_age) != h_age_val:
                            conf_age = 0.40
                            logger.warning(f"[MERGE VALIDATION] Heuristic age {h_age} conflicts with LLM multiplier {l_mult_val}. Lowering conf_age.")
                except Exception as e:
                    pass

            def merge_field(field_name, heuristic_val, heuristic_conf, heuristic_method, llm_val, llm_conf):
                def is_empty(val):
                    return val in (None, "", 0, 0.0, "null")
                if heuristic_conf >= 0.70 and not is_empty(heuristic_val):
                    logger.info(f"[FIELD] {field_name} = {heuristic_val}, matched_by={heuristic_method}, confidence={heuristic_conf}")
                    return heuristic_val, heuristic_conf, heuristic_method
                elif not is_empty(llm_val):
                    logger.info(f"[FIELD] {field_name} = {llm_val}, matched_by=AI Data Recovery Fallback (high_court), confidence={llm_conf}")
                    return llm_val, llm_conf, "AI Data Recovery Fallback (high_court)"
                else:
                    logger.info(f"[FIELD] {field_name} = {heuristic_val}, matched_by={heuristic_method} (fallback), confidence={heuristic_conf}")
                    return heuristic_val, heuristic_conf, heuristic_method

            llm_conf_dec = recovered.get("confidence_scores", {}).get("deceased_name", {}).get("confidence", 0.85)
            deceased_name, conf_deceased_name, method_deceased_name = merge_field(
                "deceased_name", deceased_name, conf_deceased_name, method_deceased_name, recovered.get("deceased_name"), llm_conf_dec
            )

            llm_conf_claim = recovered.get("confidence_scores", {}).get("claimant_name", {}).get("confidence", 0.85)
            claimant_name, conf_claimant_name, method_claimant_name = merge_field(
                "claimant_name", claimant_name, conf_claimant_name, method_claimant_name, recovered.get("claimant_name"), llm_conf_claim
            )

            llm_conf_age = recovered.get("confidence_scores", {}).get("age", {}).get("confidence", 0.85)
            age, conf_age, method_age = merge_field(
                "age", age, conf_age, method_age, recovered.get("age"), llm_conf_age
            )

            llm_conf_income = recovered.get("confidence_scores", {}).get("monthly_income", {}).get("confidence", 0.85)
            monthly_income, conf_monthly_income, method_monthly_income = merge_field(
                "monthly_income", monthly_income, conf_monthly_income, method_monthly_income, recovered.get("monthly_income"), llm_conf_income
            )

            llm_conf_dis = recovered.get("confidence_scores", {}).get("disability", {}).get("confidence", 0.85)
            disability, conf_disability, method_disability = merge_field(
                "disability", disability, conf_disability, method_disability, recovered.get("disability_percentage") or recovered.get("disability"), llm_conf_dis
            )

            llm_conf_mult = recovered.get("confidence_scores", {}).get("multiplier", {}).get("confidence", 0.85)
            multiplier, conf_multiplier, method_multiplier = merge_field(
                "multiplier", multiplier, conf_multiplier, method_multiplier, recovered.get("multiplier"), llm_conf_mult
            )

            llm_conf_prop = recovered.get("confidence_scores", {}).get("future_prospect", {}).get("confidence", 0.85)
            future_prospect, conf_future_prospect, method_future_prospect = merge_field(
                "future_prospect", future_prospect, conf_future_prospect, method_future_prospect, recovered.get("future_prospect"), llm_conf_prop
            )

            llm_conf_deps = recovered.get("confidence_scores", {}).get("dependents", {}).get("confidence", 0.85)
            dependents, conf_dependents, method_dependents = merge_field(
                "dependents", dependents, conf_dependents, method_dependents, recovered.get("dependents"), llm_conf_deps
            )

            llm_conf_mar = recovered.get("confidence_scores", {}).get("marital_status", {}).get("confidence", 0.85)
            marital_status, conf_marital_status, method_marital_status = merge_field(
                "marital_status", marital_status, conf_marital_status, method_marital_status, recovered.get("marital_status"), llm_conf_mar
            )

            llm_conf_comp = recovered.get("confidence_scores", {}).get("total_compensation", {}).get("confidence", 0.85)
            total_compensation, conf_total_compensation, method_total_compensation = merge_field(
                "total_compensation", total_compensation, conf_total_compensation, method_total_compensation, recovered.get("total_compensation") or recovered.get("award_amount"), llm_conf_comp
            )

            llm_conf_cons = recovered.get("confidence_scores", {}).get("consortium", {}).get("confidence", 0.85)
            consortium, conf_consortium, method_consortium = merge_field(
                "consortium", consortium, conf_consortium, method_consortium, recovered.get("consortium"), llm_conf_cons
            )

            llm_conf_fun = recovered.get("confidence_scores", {}).get("funeral_expenses", {}).get("confidence", 0.85)
            funeral_expenses, conf_funeral_expenses, method_funeral_expenses = merge_field(
                "funeral_expenses", funeral_expenses, conf_funeral_expenses, method_funeral_expenses, recovered.get("funeral_expenses"), llm_conf_fun
            )

            llm_conf_est = recovered.get("confidence_scores", {}).get("loss_estate", {}).get("confidence", 0.85)
            loss_estate_val, conf_loss_estate, method_loss_estate = merge_field(
                "loss_estate", loss_estate_val, conf_loss_estate, method_loss_estate, recovered.get("loss_estate") or recovered.get("loss_estate_val"), llm_conf_est
            )

            llm_conf_cc = recovered.get("confidence_scores", {}).get("consortium_claimants", {}).get("confidence", 0.85)
            consortium_claimants, conf_consortium_claimants, method_consortium_claimants = merge_field(
                "consortium_claimants", consortium_claimants, conf_consortium_claimants, method_consortium_claimants, recovered.get("consortium_claimants"), llm_conf_cc
            )

            # Extra normalized fields from LLM recovery
            llm_conf_fn = recovered.get("confidence_scores", {}).get("father_name", {}).get("confidence", 0.85)
            father_name, conf_father_name, method_father_name = merge_field(
                "father_name", father_name, conf_father_name, method_father_name, recovered.get("father_name"), llm_conf_fn
            )

            llm_conf_doa = recovered.get("confidence_scores", {}).get("date_of_accident", {}).get("confidence", 0.85)
            date_of_accident, conf_date_of_accident, method_date_of_accident = merge_field(
                "date_of_accident", date_of_accident, conf_date_of_accident, method_date_of_accident, recovered.get("date_of_accident"), llm_conf_doa
            )

            llm_conf_poa = recovered.get("confidence_scores", {}).get("place_of_accident", {}).get("confidence", 0.85)
            place_of_accident, conf_place_of_accident, method_place_of_accident = merge_field(
                "place_of_accident", place_of_accident, conf_place_of_accident, method_place_of_accident, recovered.get("place_of_accident"), llm_conf_poa
            )

            llm_future_type = recovered.get("future_type")
            if isinstance(llm_future_type, str):
                if any(k in llm_future_type.lower() for k in ["perm", "govt", "service", "company"]):
                    llm_future_type = 1
                else:
                    llm_future_type = 2

            llm_conf_ft = recovered.get("confidence_scores", {}).get("future_type", {}).get("confidence", 0.85)
            future_type, conf_future_type, method_future_type = merge_field(
                "future_type", future_type, conf_future_type, method_future_type, llm_future_type, llm_conf_ft
            )

    # ── Post-Merge Validation Pass ──────────────────────────────────────────
    from backend.calculator import get_multiplier, get_future_prospect, get_deduction
    multiplier_needs_manual_review = False
    
    try:
        age_val = int(age) if age else None
    except (ValueError, TypeError):
        age_val = None
        
    if age_val is not None and multiplier is not None:
        try:
            expected_multiplier = get_multiplier(age_val)
            if int(multiplier) != expected_multiplier:
                msg = f"Multiplier mismatch: extracted {multiplier}, expected {expected_multiplier} for age {age_val}."
                logger.warning(msg)
                anomalies_detected.append(msg)
                if ai_recovery_triggered:
                    # Both heuristic AND LLM recovery have independently
                    # disagreed with the table for this age -- usually means
                    # this page doesn't contain the real value at all.
                    conf_multiplier = 0.20
                    conf_age = min(conf_age, 0.20)
                    multiplier_needs_manual_review = True
                    anomalies_detected.append(
                        f"Multiplier ({multiplier}) still disagrees with the age-based table "
                        f"({expected_multiplier}) even after AI recovery -- this page likely does not "
                        f"contain the real multiplier/age; verify against the judgment manually."
                    )
                else:
                    conf_multiplier = 0.40
        except Exception as e:
            logger.error(f"Error validating multiplier: {e}")
            
    if age_val is not None and future_prospect not in (None, "", "null"):
        try:
            try:
                f_type = int(future_type)
            except (ValueError, TypeError):
                f_type = 2
            expected_prospect = get_future_prospect(age_val, f_type) * 100.0
            if abs(float(future_prospect) - expected_prospect) > 0.01:
                conf_future_prospect = 0.40
                msg = f"Future prospect mismatch: extracted {future_prospect}%, expected {expected_prospect}% for age {age_val} and type {f_type}."
                logger.warning(msg)
                anomalies_detected.append(msg)
        except Exception as e:
            logger.error(f"Error validating future prospect: {e}")
            
    if case_type == "death" and dependents is not None:
        try:
            dep_val = int(dependents)
        except (ValueError, TypeError):
            dep_val = 0
            
        status_str = str(marital_status).strip().lower() if marital_status else ""
        is_bachelor = status_str in ("single", "bachelor", "unmarried", "b", "s")
        
        if dep_val == 1 and not is_bachelor:
            conf_marital_status = 0.40
            conf_dependents = 0.40
            msg = "Sole dependent (dependents=1) case detected, but marital status is not single/bachelor. Should route to bachelor 1/2 rule, not married table."
            logger.warning(msg)
            anomalies_detected.append(msg)

    if case_type == "injury":
        deceased_name = ""
        dependents = ""
        future_prospect = ""
        future_type = ""
        multiplier = ""
        consortium = 0.0
        funeral_expenses = 0.0
        loss_estate_val = 0.0
        extracted_conlum = None
        extracted_conspo = None
        extracted_conpar = None
        extracted_conchil = None
        extracted_conwif = None
        extracted_conmo = None
        extracted_confath = None
        extracted_conhus = None
        extracted_conbro = None
        extracted_consis = None
        claimant_relationship_to_deceased = ""
    elif case_type == "death":
        disability = ""
        extracted_medical = None
        extracted_future_medical = None
        extracted_pain = None
        extracted_transport = None
        extracted_diet = None
        extracted_attender = None
        extracted_loss_income = None
        extracted_coliti = None
        extracted_misex = None
        extracted_loamiti = None
        extracted_lopmarri = None
        extracted_loexlife = None
        extracted_loveaff = None
        extracted_lossofenjoy = None

    suggestions = {
        "case_type": case_type,
        "compensation_mode": compensation_mode,
        "claimant_relationship_to_deceased": claimant_relationship_to_deceased,
        "claimant_relationship_type": claimant_relationship_to_deceased,
        "name": flat_name,
        "father_name": father_name,
        "date_of_accident": date_of_accident,
        "award_date": award_date,
        "date_of_birth": date_of_birth,
        "age": age,
        "monthly_income": monthly_income,
        "disability": disability,
        "dependents": dependents,
        "marital_status": marital_status,
        "future_type": future_type,
        "award_amount": total_compensation,
        "place_of_accident": place_of_accident,
        
        "deceased_name": deceased_name,
        "claimant_name": claimant_name,
        "occupation": occupation,
        "future_prospect": future_prospect,
        "multiplier": multiplier,
        "consortium": consortium,
        "funeral_expenses": funeral_expenses,
        "total_compensation": total_compensation,
        "prayer": prayer,
        "citations": citations,
        
        "loss_estate": loss_estate_val,
        "consortium_claimants": consortium_claimants,
        "conlum": extracted_conlum,
        "conspo": extracted_conspo,
        "conpar": extracted_conpar,
        "conchil": extracted_conchil,
        "conwif": extracted_conwif,
        "conmo": extracted_conmo,
        "confath": extracted_confath,
        "conhus": extracted_conhus,
        "conbro": extracted_conbro,
        "consis": extracted_consis,

        "coliti": extracted_coliti,
        "misex": extracted_misex,
        "loamiti": extracted_loamiti,
        "lopmarri": extracted_lopmarri,
        "loexlife": extracted_loexlife,
        "loveaff": extracted_loveaff,
        "lossofenjoy": extracted_lossofenjoy,

        "medical_expenses": extracted_medical,
        "future_medical_expenses": extracted_future_medical,
        "pain_and_suffering": extracted_pain,
        "transportation": extracted_transport,
        "special_diet": extracted_diet,
        "attender_charges": extracted_attender,
        "loss_of_income": extracted_loss_income,

        "is_tamil_nadu": is_tamil_nadu,
        "mcop_number": mcop_number,
        "compensation_table": compensation_table,

        # Structured identifier fields (Priority 2 — alias-based extraction)
        "fir_number": fir_number,
        "policy_number": policy_number,
        "vehicle_number": vehicle_number,
        "insurance_company": insurance_company,

        "ai_recovery_triggered": ai_recovery_triggered,
        "multiplier_needs_manual_review": multiplier_needs_manual_review,
        "legal_ai_summary": legal_ai_summary,
        "anomalies_detected": anomalies_detected,
        "case_classification": case_classification,
        "_debug": parser_debug,
        
        "confidence_scores": {
            "deceased_name": {
                "value": deceased_name,
                "confidence": conf_deceased_name,
                "source": sec_deceased_name,
                "source_section": sec_deceased_name,
                "source_page": page_deceased_name,
                "extraction_method": method_deceased_name
            },
            "claimant_name": {
                "value": claimant_name,
                "confidence": conf_claimant_name,
                "source": sec_claimant_name,
                "source_section": sec_claimant_name,
                "source_page": page_claimant_name,
                "extraction_method": method_claimant_name
            },
            "name": {
                "value": claimant_name or deceased_name,
                "confidence": conf_claimant_name,
                "source": sec_claimant_name,
                "source_section": sec_claimant_name,
                "source_page": page_claimant_name,
                "extraction_method": method_claimant_name
            },
            "father_name": {
                "value": father_name,
                "confidence": conf_father_name,
                "source": sec_father_name,
                "source_section": sec_father_name,
                "source_page": page_father_name,
                "extraction_method": method_father_name
            },
            "date_of_accident": {
                "value": date_of_accident,
                "confidence": conf_date_of_accident,
                "source": sec_date_of_accident,
                "source_section": sec_date_of_accident,
                "source_page": page_date_of_accident,
                "extraction_method": method_date_of_accident
            },
            "award_date": {
                "value": award_date,
                "confidence": conf_award_date,
                "source": sec_award_date,
                "source_section": sec_award_date,
                "source_page": page_award_date,
                "extraction_method": method_award_date
            },
            "date_of_birth": {
                "value": date_of_birth,
                "confidence": conf_date_of_birth,
                "source": sec_date_of_birth,
                "source_section": sec_date_of_birth,
                "source_page": page_date_of_birth,
                "extraction_method": method_date_of_birth
            },
            "age": {
                "value": age,
                "confidence": conf_age,
                "source": sec_age,
                "source_section": sec_age,
                "source_page": page_age,
                "extraction_method": method_age
            },
            "occupation": {
                "value": occupation,
                "confidence": conf_occupation,
                "source": sec_occupation,
                "source_section": sec_occupation,
                "source_page": page_occupation,
                "extraction_method": method_occupation
            },
            "monthly_income": {
                "value": monthly_income,
                "confidence": conf_monthly_income,
                "source": sec_monthly_income,
                "source_section": sec_monthly_income,
                "source_page": page_monthly_income,
                "extraction_method": method_monthly_income
            },
            "multiplier": {
                "value": multiplier,
                "confidence": conf_multiplier,
                "source": sec_multiplier,
                "source_section": sec_multiplier,
                "source_page": page_multiplier,
                "extraction_method": method_multiplier
            },
            "future_prospect": {
                "value": future_prospect,
                "confidence": conf_future_prospect,
                "source": sec_future_prospect,
                "source_section": sec_future_prospect,
                "source_page": page_future_prospect,
                "extraction_method": method_future_prospect
            },
            "consortium": {
                "value": consortium,
                "confidence": conf_consortium,
                "source": sec_consortium,
                "source_section": sec_consortium,
                "source_page": page_consortium,
                "extraction_method": method_consortium
            },
            "funeral_expenses": {
                "value": funeral_expenses,
                "confidence": conf_funeral_expenses,
                "source": sec_funeral_expenses,
                "source_section": sec_funeral_expenses,
                "source_page": page_funeral_expenses,
                "extraction_method": method_funeral_expenses
            },
            "loss_estate": {
                "value": loss_estate_val,
                "confidence": conf_loss_estate,
                "source": "raw_ocr",
                "source_section": "raw_ocr",
                "source_page": 1,
                "extraction_method": method_loss_estate
            },
            "total_compensation": {
                "value": total_compensation,
                "confidence": conf_total_compensation,
                "source": sec_total_compensation,
                "source_section": sec_total_compensation,
                "source_page": page_total_compensation,
                "extraction_method": method_total_compensation
            },
            "prayer": {
                "value": prayer,
                "confidence": conf_prayer,
                "source": sec_prayer,
                "source_section": sec_prayer,
                "source_page": page_prayer,
                "extraction_method": method_prayer
            },
            "citations": {
                "value": citations,
                "confidence": conf_citations,
                "source": "cited_judgments",
                "source_section": "cited_judgments",
                "source_page": 1,
                "extraction_method": "Citation Pattern Matching"
            },
            "place_of_accident": {
                "value": place_of_accident,
                "confidence": conf_place_of_accident,
                "source": sec_place_of_accident,
                "source_section": sec_place_of_accident,
                "source_page": page_place_of_accident,
                "extraction_method": method_place_of_accident
            },
            "disability": {
                "value": disability,
                "confidence": conf_disability,
                "source": sec_disability,
                "source_section": sec_disability,
                "source_page": page_disability,
                "extraction_method": method_disability
            },
            "fir_number": {
                "value": fir_number,
                "confidence": conf_fir_number,
                "source": "raw_ocr",
                "source_section": "raw_ocr",
                "source_page": 1,
                "extraction_method": "Regex Pattern Matching"
            },
            "policy_number": {
                "value": policy_number,
                "confidence": conf_policy_number,
                "source": "raw_ocr",
                "source_section": "raw_ocr",
                "source_page": 1,
                "extraction_method": "Regex Pattern Matching"
            },
            "vehicle_number": {
                "value": vehicle_number,
                "confidence": conf_vehicle_number,
                "source": "raw_ocr",
                "source_section": "raw_ocr",
                "source_page": 1,
                "extraction_method": "Regex Pattern Matching"
            },
            "insurance_company": {
                "value": insurance_company,
                "confidence": conf_insurance_company,
                "source": "raw_ocr",
                "source_section": "raw_ocr",
                "source_page": 1,
                "extraction_method": "Known Insurer + Regex Matching"
            },
            "dependents": {
                "value": dependents,
                "confidence": conf_dependents,
                "source": sec_dependents,
                "source_section": sec_dependents,
                "source_page": page_dependents,
                "extraction_method": method_dependents
            },
            "marital_status": {
                "value": marital_status,
                "confidence": conf_marital_status,
                "source": sec_marital_status,
                "source_section": sec_marital_status,
                "source_page": page_marital_status,
                "extraction_method": method_marital_status
            },
            "consortium_claimants": {
                "value": consortium_claimants,
                "confidence": conf_consortium_claimants,
                "source": "raw_ocr",
                "source_section": "raw_ocr",
                "source_page": 1,
                "extraction_method": method_consortium_claimants
            },
            "claimant_relationship_type": {
                "value": claimant_relationship_to_deceased,
                "confidence": conf_claimant_relationship,
                "source": "claimant_section" if claimant_relationship_to_deceased else "raw_ocr",
                "source_section": "claimant_section" if claimant_relationship_to_deceased else "raw_ocr",
                "source_page": 1,
                "extraction_method": "Relationship Splitting"
            },
            "future_type": {
                "value": future_type,
                "confidence": conf_future_type,
                "source": sec_future_type,
                "source_section": sec_future_type,
                "source_page": page_future_type,
                "extraction_method": method_future_type
            }
        }
    }

    # Page classification audit trail
    page_classifications = {}
    for p in pages:
        page_classifications[str(p["page_number"])] = classify_page_type(p["text"], p["page_number"])
    parser_debug["page_classifications"] = page_classifications

    # ── High Court Death Case Pruning / Exclusions ───────────────────────────
    if case_type == "death":
        # 1. Reset excluded fields to None
        for excl in [
            "consortium", "funeral_expenses", "loss_estate",
            "conlum", "conspo", "conpar", "conchil", "conwif",
            "conmo", "confath", "conhus", "conbro", "consis", "medical_expenses"
        ]:
            suggestions[excl] = None
            if "confidence_scores" in suggestions and excl in suggestions["confidence_scores"]:
                suggestions["confidence_scores"][excl]["value"] = None
                suggestions["confidence_scores"][excl]["confidence"] = 0.0
                suggestions["confidence_scores"][excl]["reason"] = "Excluded for death case autofill"

        # 2. Check required fields and flag if missing
        required_fields = [
            ("deceased_name", "Deceased Name not found in document"),
            ("name", "Deceased Name not found in document"),
            ("date_of_accident", "Date of accident not found in document"),
            ("age", "Age of deceased not found in document"),
            ("monthly_income", "Monthly income not found in document"),
            ("marital_status", "Marital status not found in document"),
            ("future_type", "Future prospects type not found in document")
        ]
        for field, missing_msg in required_fields:
            val = suggestions.get(field)
            if val in (None, "", "None", "null", 0, 0.0):
                suggestions[field] = None
                if "confidence_scores" in suggestions and field in suggestions["confidence_scores"]:
                    suggestions["confidence_scores"][field]["value"] = None
                    suggestions["confidence_scores"][field]["confidence"] = 0.0
                    suggestions["confidence_scores"][field]["reason"] = missing_msg

    print("[PARSE DEBUG] Final parsed key fields:")
    print(f"  Name: {suggestions.get('name')}")
    print(f"  Case Type: {suggestions.get('case_type')}")
    print(f"  Age: {suggestions.get('age')}")
    print(f"  Monthly Income: {suggestions.get('monthly_income')}")
    print(f"  Award Amount: {suggestions.get('award_amount')}")
    print(f"  Disability: {suggestions.get('disability')}")

    return suggestions


def extract_hindi_narrative_income(raw_text: str):
    if not raw_text:
        return None, None

    amount_re = re.compile(r'(\d[\d,]{2,8})\s*/?\-?\s*(?:रूपये|रुपये)\s*प्रतिमाह', re.UNICODE)
    # Split on clause boundaries so an unrelated nearby clause's keywords
    # can't bleed into the wrong amount's score.
    clauses = re.split(r'(?:जबकि|।|\n)', raw_text)

    candidates = []
    for clause in clauses:
        for m in amount_re.finditer(clause):
            try:
                amount = float(m.group(1).replace(",", ""))
            except ValueError:
                continue
            if amount < 1000 or amount > 500000:
                continue
            score = 0
            if "अभिवचनित" in clause or "मूल याचिका" in clause:
                score += 10   # explicitly pleaded in the original petition
            elif "याचिका" in clause:
                score += 2
            if "निर्धारित" in clause or "मानते हुए" in clause:
                score -= 6    # tribunal's own notional/assessed figure
            if "मुख्य परीक्षण" in clause and "अर्जित" in clause:
                score -= 3    # oral testimony figure, not the pleaded claim
            candidates.append((score, amount, clause.strip()))

    if not candidates:
        return None, None
    candidates.sort(key=lambda c: -c[0])
    _, best_amount, best_clause = candidates[0]
    return best_amount, best_clause

# ======================================================================
# LOWER COURT / HINDI TARGETED FIELD PARSER
# ======================================================================
#
# Deliberately separate from parse_extracted_text() above (which is
# English-only by design — see the Devanagari-strip note near its start).
# This parser is only ever called on the small set of heading-matched pages
# produced by backend.ocr.find_relevant_pages_by_heading() (the "केन्द्रीय
# भरण काउन्टर" cover sheet and/or the award's operative/compensation-table
# page) — a handful of dense, mostly-tabular pages, not free-flowing
# judgment prose. That's what makes regex extraction viable here.
#
# IMPORTANT: Python's \w does NOT match Devanagari combining vowel signs /
# virama (Unicode categories Mn/Mc — e.g. ि ् ू), which appear in almost
# every Hindi word. Any \w-based pattern silently fails on Hindi text.
# Always use an explicit [\u0900-\u097F] range instead. Similarly, \s
# matches newlines, so an unguarded {0,n} token span can silently jump
# across unrelated lines — the helpers below normalize horizontal
# whitespace only and keep line breaks as real boundaries.

_DEVA_RANGE = r'\u0900-\u097F'
_HI_NAME_TOK = rf'[{_DEVA_RANGE}a-zA-Z]+(?:[.\-][{_DEVA_RANGE}a-zA-Z]+)*'
_HI_NAME_SPAN = rf'{_HI_NAME_TOK}(?: {_HI_NAME_TOK}){{0,2}}'        # tight span, low-noise
_HI_NAME_SPAN_WIDE = rf'{_HI_NAME_TOK}(?: {_HI_NAME_TOK}){{0,7}}'   # wide span for labeled rows

_HI_STOPWORDS = {
    "आवेदिका", "आवेदक", "अनावेदक", "अनावेदकगण", "श्री", "श्रीमती", "कुमारी",
    "कुमार", "सुश्री", "स्व", "की", "ओर", "से", "हेतु", "द्वारा", "को", "के",
}

HINDI_HEADING_KEYWORDS = {
    # Structured cover-sheet used across MP eCourts trial-court bundles —
    # highest-value single page for autofill: name/father/age/occupation/
    # income of the claimant, in a clean numbered label:value table.
    "central_filing_counter": [
        "केन्द्रीय भरण काउन्टर", "केंद्रीय भरण काउंटर", "भरण काउन्टर",
        "central filing counter", "filing counter", "filing counter sheet",
    ],
    # District Court header details
    "district_court_hi": [
        "जिला न्यायालय", "व्यवहार न्यायालय", "district court", "civil court",
    ],
    # Claims Tribunal details / Presiding Officer
    "claims_tribunal_hi": [
        "न्यायालय श्रीमान सदस्य मोटर दुर्घटना दावा अधिकरण",
        "सदस्य मोटर दुर्घटना दावा अधिकरण",
        "दुर्घटना दावा अधिकरण",
        "motor accident claims tribunal", "claims tribunal", "mact",
    ],
    # Tribunal's own computer/registration sheet — case no., filing no.,
    # CNR, registration/institution dates.
    "computer_sheet_hi": [
        "कम्प्यूटर शीट", "संगणक पत्रक", "पंजीयन क्रमांक", "फाइलिंग नंबर",
        "computer sheet", "registration number", "institution date",
    ],
    # Operative part of the award — carries the actual compensation figure,
    # interest rate, and liability apportionment.
    "award_operative_hi": [
        "अधिनिर्णय", "अवार्ड", "अधिकरण द्वारा पारित",
        "award", "judgment", "operative part", "final order",
    ],
    # Issues + findings table — trial-court functional equivalent of an
    # HC appeal's "Grounds"; not currently parsed field-by-field, kept as
    # a heading target so callers can decide to fetch it too.
    "issues_findings_hi": [
        "वाद प्रश्न", "वादप्रश्न", "निष्कर्ष",
        "issues", "findings",
    ],
    "compensation_table_hi": [
        "क्षतिपूर्ति राशि", "कुल प्रतिकर", "कुल क्षतिपूर्ति", "मुआवजा राशि",
        "मुआवजे की राशि", "मुआवजा की राशि", "चाही गई मुआवजा राशि", "चाही गई मुआवजा की राशि",
        "compensation table", "compensation awarded", "awarded amount", "quantum of compensation",
    ],
    "prayer_hi": [
        "प्रार्थना", "निवेदन किया गया",
        "prayer", "relief claimed", "relief",
    ],
    "memo_of_appeal_section": [
        "अपील का ज्ञापन", "अपील ज्ञापन", "अपील पत्र", "विविध अपील",
        "memo of appeal", "appeal memo",
        "miscellaneous appeal", "memorandum of appeal",
    ],
    "grounds_section": [
        "अपील के आधार", "आधार", "चुनौती के आधार", "आपत्ति के आधार",
        "grounds", "grounds of appeal", "grounds of objection", "grounds of challenge",
    ],
    "relief_section": [
        "प्रार्थना", "याचना", "अनुतोष", "राहत की प्रार्थना", "अतः प्रार्थना है",
        "अतः सादर प्रार्थना है", "प्रार्थना पत्र",
        "relief", "prayer", "relief claimed", "prayer clause",
    ],
    "application_form_hi": [
        "आवेदन पत्र", "दावा आवेदन", "दावा याचिका", "याचिका",
        "claim petition", "application form", "petition",
    ],
    "case_disposal_info_hi": [
        "निराकरण पत्रक", "निराकरण", "मामला निराकरण",
        "case disposal", "disposal sheet", "disposal information",
    ],
    # Recognized but intentionally excluded from "pages we still need" —
    # registry/admin pages with no autofill-relevant content. Not searched
    # for (keys starting with "skip_" are skipped by
    # find_relevant_pages_by_heading), kept here only as documentation of
    # what NOT to bother targeting.
    "skip_admin_hi": [
        "वकालतनामा", "नोटरी", "स्टाम्प", "कोर्ट फीस रसीद",
        "vakalatnama", "notary", "court fee receipt",
    ],
}


def _hi_trim_stopwords(text: str) -> str:
    tokens = text.strip().split(" ")
    while tokens and tokens[0] in _HI_STOPWORDS:
        tokens = tokens[1:]
    while tokens and tokens[-1] in _HI_STOPWORDS:
        tokens = tokens[:-1]
    return " ".join(tokens).strip()


def _hi_clean_amount(raw: str):
    raw = raw.replace(",", "")
    m = re.search(r'\d+\.?\d*', raw)
    return float(m.group(0)) if m else None




# Helper to translate Devanagari digits to English digits
def translate_deva_digits(s: str) -> str:
    deva_to_eng = {
        '०': '0', '१': '1', '२': '2', '३': '3', '४': '4',
        '५': '5', '६': '6', '७': '7', '८': '8', '९': '9'
    }
    return "".join(deva_to_eng.get(c, c) for c in s)

# Helper to check if a currency marker is adjacent to a match
def _is_currency_adjacent(text_str: str, start: int, end: int) -> bool:
    prefix = text_str[max(0, start - 10):start]
    suffix = text_str[end:end + 10]
    currency_pattern = re.compile(r'(?:रुपये|रुपए|रू|रु|₹|Rs|Rs\.|/-)', re.IGNORECASE)
    return bool(currency_pattern.search(prefix) or currency_pattern.search(suffix))

_CURRENT_MATCH_SCORES = []

def _hi_normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = translate_deva_digits(text)
    
    # Normalize known spelling clusters
    text = text.replace("स्थाई", "स्थायी").replace("स्थाी", "स्थायी")
    text = re.sub(r'मु[आव]ा?व[जज]े', 'मुआवजा', text)
    text = re.sub(r'मुनाव[जज][ेा]', 'मुआवजा', text)
    text = text.replace("मुआवजे", "मुआवजा")
    text = text.replace("मुनावजा", "मुआवजा").replace("मुनावजे", "मुआवजा")
    
    text = text.replace("शारीरीक", "शारीरिक")
    text = text.replace("सुखों", "सुख").replace("सुखमय", "सुख")
    text = text.replace("हानी", "हानि")
    text = text.replace("चिकितसा", "चिकित्सा")
    text = text.replace("नुकसानी", "नुकसान")
    
    # Map phonetic confusions
    text = text.replace("श", "स").replace("ष", "स")
    text = text.replace("ी", "ि").replace("ू", "ु")
    
    # Collapse punctuation
    text = re.sub(r'[|:\-—=/\\._()\[\]{}?,;!]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def _hi_fuzzy_contains_with_score(text: str, phrase: str, max_edit_ratio: float = 0.15) -> tuple:
    norm_text = _hi_normalize_text(text)
    norm_phrase = _hi_normalize_text(phrase)
    
    if not norm_phrase or not norm_text:
        return False, 0.0
        
    if len(norm_phrase) <= 6:
        matched = norm_phrase in norm_text
        return matched, 100.0 if matched else 0.0

    pr = fuzz.partial_ratio(norm_phrase, norm_text)
    tsr = fuzz.token_set_ratio(norm_phrase, norm_text)
    score = max(pr, tsr)
    
    threshold = (1.0 - max_edit_ratio) * 100.0
    
    if threshold - 15.0 <= score < threshold:
        logger.info(
            f"[FUZZY-NEAR-MISS] norm_text='{norm_text}' norm_phrase='{norm_phrase}' score={score:.2f} threshold={threshold:.2f}"
        )
        
    return score >= threshold, score

def _hi_fuzzy_contains(text: str, phrase: str, max_edit_ratio: float = 0.15) -> bool:
    matched, score = _hi_fuzzy_contains_with_score(text, phrase, max_edit_ratio)
    if matched:
        _CURRENT_MATCH_SCORES.append(score)
    return matched

# Match helpers for structural table lines and totals
_LBL_PAT = re.compile(r'^\s*(?:\[|\()? *(\d+|[०-९]+|[\u0900-\u097F]) *(?:\]|\)|[\.\-\):])+ +(.*)$')
_AMT_PAT = re.compile(
    r'\s*[:|—=\-]*\s*(?:रू|रु|₹|Rs\.?)?\s*([\d,\.\-]+(?:/-)?|निरंक|शून्य|शून्य रुपये|NIL)\s*(?:\|)?\s*$', 
    re.IGNORECASE
)

def is_totals_line(line_text: str) -> bool:
    norm = line_text.strip().lower()
    totals_kws = ["कुल", "योग", "कुल योग", "कुल क्षतिपूर्ति राशि", "कुल शति", "कुल प्रतिकर", "अंकन", "total", "sum", "grand total", "aggregate"]
    if any(kw in norm for kw in totals_kws):
        return True
    if norm.startswith('(') and not any(f"({i})" in norm for i in range(1, 20)) and (
        any(x in norm for x in ['रूपये', 'रुपये', 'रू', 'रु', 'rs', 'only', '/-']) or 
        any(x in norm for x in ["हजार", "लाख", "करोड़", "सौ", "मात्र", "thousand", "lakh"])
    ):
        return True
    return False

def parse_isolated_amount(amount_str: str) -> float:
    if any(kw in amount_str.lower() for kw in ["निरंक", "शून्य", "nil"]):
        return 0.0
    cleaned = amount_str.replace(',', '').replace('/-', '')
    cleaned = re.sub(r'[^\d.]', '', cleaned)
    try:
        return float(cleaned)
    except ValueError:
        return 0.0

def check_amount_plausibility(value: float, field: str, line_text: str) -> bool:
    if value > 99999999.0:
        logger.warning(f"[SANITY-REJECT] field={field} rejected_value={value} reason=exceeds_max_digits source_line='{line_text}'")
        return False
    return True

def match_bundle_d(norm: str) -> bool:
    has_att = _hi_fuzzy_contains(norm, "देख-रेख", max_edit_ratio=0.10) or _hi_fuzzy_contains(norm, "देखरेख", max_edit_ratio=0.10)
    has_diet = _hi_fuzzy_contains(norm, "आहार", max_edit_ratio=0.10) or _hi_fuzzy_contains(norm, "पोषण", max_edit_ratio=0.10)
    has_trans = _hi_fuzzy_contains(norm, "आने-जाने", max_edit_ratio=0.10) or _hi_fuzzy_contains(norm, "अस्पताल जाने", max_edit_ratio=0.10) or bool(re.search(r'अस्पताल.*जाने', norm))
    return has_att and has_diet and has_trans

def match_bundle_b(norm: str) -> bool:
    has_future = _hi_fuzzy_contains(norm, "भविष्य", max_edit_ratio=0.10) or _hi_fuzzy_contains(norm, "भावी", max_edit_ratio=0.10) or _hi_fuzzy_contains(norm, "future", max_edit_ratio=0.10)
    has_income = any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in ["आय", "क्षति", "हानि"])
    has_med = any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in ["इलाज", "उपचार", "चिकित्सा"])
    if has_future and has_income and has_med:
        return True
    # Looser fallback:
    has_expense = any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in ["खर्च", "व्यय"])
    has_loss = any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in ["हानि", "क्षति", "नुकसानी"])
    if has_future and has_expense and has_loss:
        return True
    return False

def match_bundle_c(norm: str) -> bool:
    has_trans = any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in ["अस्पताल", "आने-जाने", "आवागमन"])
    has_att = any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in ["रुकने वाले व्यक्ति", "साथ रहने वाले", "देख-रेख करने वाला व्यक्ति", "देखरेख करने वाला व्यक्ति", "व्यक्ति का खर्च"])
    return has_trans and has_att

def match_bundle_a(norm: str) -> bool:
    has_diet = any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in ["आहार", "पौष्टिक", "विशेष आहार", "विशेष खुराक", "पोषण", "भोजन", "खुराक"])
    has_trans = any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in ["परिवहन", "आवागमन", "आने-जाने", "यात्रा", "यातायात"])
    return has_diet and has_trans

def match_standalone_future_medical(norm: str) -> bool:
    has_future = _hi_fuzzy_contains(norm, "भविष्य", max_edit_ratio=0.10) or _hi_fuzzy_contains(norm, "भावी", max_edit_ratio=0.10) or _hi_fuzzy_contains(norm, "future", max_edit_ratio=0.10)
    has_med = any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in ["इलाज", "उपचार", "चिकित्सा"])
    if any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in ["आय", "क्षति", "हानि"]):
        return False
    return has_future and has_med

def match_standalone_medical(norm: str) -> bool:
    has_doc_fee = (_hi_fuzzy_contains(norm, "डॉ", max_edit_ratio=0.10) or _hi_fuzzy_contains(norm, "doctor", max_edit_ratio=0.10)) and (_hi_fuzzy_contains(norm, "फीस", max_edit_ratio=0.10) or _hi_fuzzy_contains(norm, "fee", max_edit_ratio=0.10))
    has_med_term = any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in [
        "इलाज", "चिकित्सा", "उपचार", "दवाई", "दवा", "आपरेशन", "ऑपरेशन", "अस्पताल",
        "treatment", "medical", "medicine", "hospital", "operation"
    ])
    if not (has_doc_fee or has_med_term):
        return False
    if any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in ["भविष्य", "भावी", "future"]):
        return False
    has_diet = any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in ["आहार", "पौष्टिक", "विशेष आहार", "पोषण", "खुराक", "भोजन"])
    has_trans = any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in ["परिवहन", "आवागमन", "आने-जाने", "यात्रा", "यातायात"])
    return not (has_diet or has_trans)

def match_standalone_diet(norm: str) -> bool:
    has_diet = any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in ["विशेष आहार", "पौष्टिक आहार", "विशेष खुराक", "पौष्टिक खुराक", "आहार व्यय", "खुराक व्यय", "विशेष भोजन", "nutrition", "diet"])
    return has_diet and not match_bundle_a(norm) and not match_bundle_d(norm)

def match_standalone_transport(norm: str) -> bool:
    has_trans = any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in ["परिवहन व्यय", "परिवहन खर्च", "यातायात व्यय", "यातायात खर्च", "यात्रा व्यय", "आने-जाने", "आवागमन व्यय", "conveyance", "transportation", "transport"])
    return has_trans and not match_bundle_a(norm) and not match_bundle_c(norm) and not match_bundle_d(norm)

def match_standalone_attender(norm: str) -> bool:
    has_att = any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in ["परिचारक", "परिचर", "अटेंडेंट", "देखभाल", "सेवक", "सहायक", "सहायता", "attendant", "attender"])
    has_exp = any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in ["व्यय", "खर्च", "charges", "expenses"])
    return has_att and has_exp and not match_bundle_c(norm) and not match_bundle_d(norm)

HINDI_LOSS_OF_INCOME_KEYWORDS = [
    "आवेदक के कार्य की नुकसानी",
    "आय की हानि",
    "भविष्य में होने वाली आय की हानि",
    "भविष्य आय की हानि",
    "विकलांगता के कारण आय की हानि",
    "वेतन की हानि", "वेतन हानि", "मजदूरी की हानि", "कमाई का नुकसान", "रोजगार हानि", "उपार्जन",
    "loss of income", "loss of earnings", "loss of wages"
]

def is_loss_of_income_line(norm: str) -> bool:
    return any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in HINDI_LOSS_OF_INCOME_KEYWORDS) or (
        any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in ["आय", "वेतन", "मजदूरी", "कमाई", "रोजगार"]) and any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in ["हानि", "नुकसान", "अवधि", "क्षति", "नुकसानी"])
    )

def match_rule_1(norm: str):
    has_g1 = any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in ["स्थायी अपंगता", "स्थायी विकलांगता", "स्थायी निःशक्तता", "स्थाई अपंगता", "स्थाई विकलांगता", "स्थाई निःशक्तता"])
    has_g2 = any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in ["क्षतिपूर्ति", "पूर्ति राशि", "प्रतिकर", "मुनावजा", "मुआवजा", "हर्जाना"])
    if has_g1 and has_g2:
        return True, "1A"
    has_b = any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in ["पीड़ा", "कष्ट", "वेदना", "दर्द", "pain", "suffering"])
    if has_b:
        return True, "1B"
    return False, None

def match_rule_2(norm: str):
    has_g1 = any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in ["प्रगति", "उन्नति", "अधिक आय", "विकास", "संभावनाओं"])
    has_g2 = ("आय" in norm and "वंचित" in norm) or "हानि" in norm or "प्रतिकर" in norm
    has_g2 = (_hi_fuzzy_contains(norm, "आय", max_edit_ratio=0.10) and _hi_fuzzy_contains(norm, "वंचित", max_edit_ratio=0.10)) or _hi_fuzzy_contains(norm, "हानि", max_edit_ratio=0.10) or _hi_fuzzy_contains(norm, "प्रतिकर", max_edit_ratio=0.10)
    if has_g1 and has_g2:
        return True, "2A"
    has_b = any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in ["आनंदपूर्ण जीवन", "जीवन जीने", "जीवन के सुख", "आनंद", "सुख", "amenities", "enjoyment"]) and any(_hi_fuzzy_contains(norm, x, max_edit_ratio=0.10) for x in ["वंचित", "हानि"])
    if has_b:
        return True, "2B"
    has_c = is_loss_of_income_line(norm)
    if has_c:
        return True, "2C"
    return False, None

def classify_hindi_line(line_text: str):
    norm = line_text.replace("स्थाई", "स्थायी").replace("शारीरीक", "शारीरिक").replace("सुखों", "सुख").replace("सुखमय", "सुख")
    
    bundle_matches = []
    if match_bundle_d(norm):
        bundle_matches.append(("BUNDLE_D", None))
    if match_bundle_b(norm):
        bundle_matches.append(("BUNDLE_B", None))
    if match_bundle_c(norm):
        bundle_matches.append(("BUNDLE_C", None))
    if match_bundle_a(norm):
        bundle_matches.append(("BUNDLE_A", None))
        
    legal_head_matches = []
    r1, sub1 = match_rule_1(norm)
    if r1:
        legal_head_matches.append(("PAIN_AND_SUFFERING", sub1))
    r2, sub2 = match_rule_2(norm)
    if r2:
        legal_head_matches.append(("LOSS_OF_INCOME", sub2))
        
    standalone_matches = []
    if match_standalone_future_medical(norm):
        standalone_matches.append(("STANDALONE_FUTURE_MEDICAL", None))
    if match_standalone_medical(norm):
        standalone_matches.append(("STANDALONE_MEDICAL", None))
    if match_standalone_diet(norm):
        standalone_matches.append(("STANDALONE_DIET", None))
    if match_standalone_transport(norm):
        standalone_matches.append(("STANDALONE_TRANSPORT", None))
    if match_standalone_attender(norm):
        standalone_matches.append(("STANDALONE_ATTENDER", None))
        
    if bundle_matches:
        if len(bundle_matches) > 1:
            return "AMBIGUOUS", [m[0] for m in bundle_matches]
        return bundle_matches[0]
        
    all_matches = legal_head_matches + standalone_matches
    if not all_matches:
        return None
    if len(all_matches) > 1:
        match_types = [m[0] for m in all_matches]
        if "STANDALONE_FUTURE_MEDICAL" in match_types and "STANDALONE_MEDICAL" in match_types:
            return ("STANDALONE_FUTURE_MEDICAL", None)
        return "AMBIGUOUS", match_types
        
    return all_matches[0]


def get_damage_head_keyword(desc: str) -> str:
    norm = desc.replace("स्थाई", "स्थायी").replace("शारीरीक", "शारीरिक").replace("सुखों", "सुख").replace("सुखमय", "सुख").lower()
    
    # Check future/future medical/bundle B first
    if "भविष्य" in norm or "भावी" in norm or "future" in norm:
        return "future"
        
    # Check disability
    if any(x in norm for x in ["अपंगता", "विकलांगता", "निःशक्तता", "निर्योग्यता"]):
        return "disability"
        
    # Check pain
    if any(x in norm for x in ["पीड़ा", "कष्ट", "वेदना", "दर्द", "pain", "suffering"]):
        return "pain"
        
    # Check medical
    if any(x in norm for x in ["चिकित्सा", "इलाज", "उपचार", "दवा", "औषधि", "अस्पताल", "डॉ", "doctor", "medical", "treatment", "hospital", "operation"]):
        return "medical"
        
    # Check diet
    if any(x in norm for x in ["आहार", "पौष्टिक", "खुराक", "भोजन", "nutrition", "diet"]):
        return "diet"
        
    # Check transport
    if any(x in norm for x in ["परिवहन", "यातायात", "यात्रा", "आवागमन", "conveyance", "transportation", "transport"]):
        return "transport"
        
    # Check attender
    if any(x in norm for x in ["परिचारक", "परिचर", "अटेंडेंट", "देखभाल", "सेवक", "सहायक", "सहायता", "attendant", "attender", "nursing"]):
        return "attender"
        
    # Check loss of income
    if is_loss_of_income_line(norm):
        return "loss_of_income"
        
    return None


def check_structural_block_validity(block_lines: list) -> bool:
    items = [bl for bl in block_lines if not bl.get("is_totals")]
    n = len(items)
    if n < 4:
        return False
        
    for idx in range(n - 3):
        window = items[idx : idx + 4]
        keywords = []
        valid_window = True
        for bl in window:
            amt_str = bl.get("amount_str")
            if not amt_str:
                valid_window = False
                break
            if bl.get("is_totals"):
                valid_window = False
                break
            kw = get_damage_head_keyword(bl.get("desc", ""))
            if not kw:
                valid_window = False
                break
            keywords.append(kw)
        if valid_window and len(set(keywords)) == 4:
            return True
    return False


HI_APPLICATION_FORM_FIELDS = {
    "injured_name":        ["आवेदक का नाम", "आवेदक का नाम व पिता का नाम"],
    "father_name":         ["पिता का नाम"],
    "address":             ["आवेदक का पूरा पता", "आवेदक का पता"],
    "age":                 ["आवेदक की उम्र", "आवेदक की आयु"],
    "occupation":          ["आवेदक का व्यवसाय"],
    "monthly_income":      ["आवेदक की मासिक आय"],
    "date_of_accident":    ["घटना दिनांक", "घटना का दिनांक व समय"],
    "place_of_accident":   ["दुर्घटना स्थल का पूर्ण पता", "घटना स्थल"],
    "injury_description":  ["आवेदक को आई चोटों का विवरण"],
    "vehicle_number":      ["दुर्घटना में लिप्त वाहन का विवरण", "वाहन क्रमांक"],
    "hospital_name":       ["अस्पताल का नाम"],
    "driver_name_address": ["वाहन के चालक का नाम व पता"],
    "owner_name_address":  ["वाहन के मालिक का नाम व पता"],
    "policy_number":       ["वाहन का बीमा क्रमांक"],
    "insurance_company":   ["वाहन की बीमा कंपनी"],
    "is_income_tax_payer": ["क्या आवेदक आयकरदाता है"],
    "was_traveling":       ["क्या आवेदक वाहन में यात्रा कर रहा था"],
    "compensation_claimed":["चाही गई मुआवजा राशि", "क्षतिपूर्ति की राशि"],
    "other_case_info":     ["अन्य जानकारी जो प्रकरण के निराकरण के लिए आवश्यक है"],
    "fir_number":          ["घटना की रिपोर्ट", "थाना", "रिपोर्ट", "थाने में अपराध"],
}

def split_label_value(text: str) -> tuple:
    # Split by standard separators
    m = re.search(r'\s*[:=—–]\s*|\s+-\s+', text)
    if m:
        label = text[:m.start()].strip()
        val = text[m.end():].strip()
        return label, val
    return text, ""

def is_usable_value(val: str) -> bool:
    if not val:
        return False
    clean = re.sub(r'[\s|:\-—=/\\._()\[\]{}?,;!]', '', val)
    return len(clean) > 0

def is_section_break(line_text: str) -> bool:
    norm = line_text.strip().lower()
    break_kws = [
        "हस्ताक्षर", "signature", "प्रस्तुतकर्ता", "आवेदकगण", "वकील", "अधिवक्ता",
        "न्यायालय", "न्यायाधीश", "सदस्य", "claims tribunal", "court", "judge"
    ]
    if any(kw in norm for kw in break_kws):
        return True
    heading_kws = ["आदेश", "न्याय निर्णय", "वाद प्रश्न", "मुद्दे", "वाद-प्रश्न", "order", "issues", "judgment"]
    if any(kw in norm for kw in heading_kws):
        return True
    return False

def is_expected_index(field: str, val_num: int) -> bool:
    expected = {
        "injured_name": [1],
        "father_name": [1, 2],
        "address": [2],
        "age": [3],
        "occupation": [4],
        "monthly_income": [5],
        "date_of_accident": [6],
        "place_of_accident": [6, 7],
        "fir_number": [7, 8],
    }
    return val_num in expected.get(field, [])

def split_relational_name(text: str) -> str:
    if not text:
        return ""
    m_rel = re.search(r'(.+?)\s+(?:पुत्र|पुत्री|son of|daughter of|s/o|d/o|w/o|पत्नी|पिता|पति)\s+(?:श्री\s+|late\s+|स्व\.\s+)?(.+)', text, re.IGNORECASE)
    if m_rel:
        return m_rel.group(1).strip()
    return text.strip()

def split_name_address(text: str) -> tuple:
    if not text:
        return "", ""
    m = re.search(r'(.+?)\s+(?:निवासी|पता|निवास|नि\.|ग्राम|स्थान)\s*(.*)', text, re.IGNORECASE)
    if m:
        name = m.group(1).strip()
        address = m.group(2).strip()
        name = re.sub(r'[:\-—–]+$', '', name).strip()
        return name, address
    else:
        parts = re.split(r'[:\-—–]+', text)
        if len(parts) >= 2:
            return parts[0].strip(), parts[1].strip()
        return text.strip(), ""

def parse_yes_no(text: str) -> str:
    if not text:
        return ""
    text_clean = text.strip()
    if re.search(r'\b(?:नहीं|नही|न|no|not)\b', text_clean, re.IGNORECASE):
        return "नहीं"
    if re.search(r'\b(?:हाँ|हा|हाँ|yes|y|स्वयं)\b', text_clean, re.IGNORECASE):
        return "हाँ"
    return text_clean

def parse_amount_from_line(text: str) -> float:
    m_amt = _AMT_PAT.search(text)
    if m_amt:
        val_str = m_amt.group(1).strip()
        if any(x in val_str.lower() for x in ["निरंक", "शून्य", "nil", "shunya"]):
            return 0.0
        amt = _hi_clean_amount(val_str)
        if amt is not None:
            return amt
    text_trans = translate_deva_digits(text)
    text_trans = text_trans.replace(",", "")
    m = re.search(r'\d+(?:\.\d+)?', text_trans)
    if m:
        return float(m.group(0))
    return None

def extract_date(text: str) -> str:
    m_dt = re.search(r'(\d{1,2}[./-]\d{1,2}[./-]\d{4})', translate_deva_digits(text))
    if m_dt:
        return m_dt.group(1).replace("/", ".")
    return ""

def extract_place(text: str) -> str:
    place = None
    m_pl = re.search(r'(?:स्थान|को|स्थल)\s*[:\-]*\s*(.+)', text)
    if m_pl:
        place_cand = m_pl.group(1).strip()
        place_cand = re.sub(r'\d{1,2}[./-]\d{1,2}[./-]\d{4}', '', place_cand)
        place_cand = re.sub(r'\d{1,2}[:.]\d{2}', '', place_cand)
        place_cand = re.sub(r'(?:बजे|समय|दिनांक|के\s+पास|को)', '', place_cand)
        place_cand = re.sub(r'[ \t\.\-\–:,]+', ' ', place_cand).strip()
        if place_cand:
            place = place_cand
    return place or ""

def extract_hindi_narrative_petition(text_lines: list) -> dict:
    flat_text = " ".join(text_lines)
    flat_text = translate_deva_digits(flat_text)
    
    res = {}
    
    # 1. Date of accident
    m_dt = re.search(r'(?:घटना\s+दिनांक|दिनांक\s+को|घटना\s+तिथि)\s*([0-9/.\-]+)', flat_text)
    if m_dt:
        res["date_of_accident"] = m_dt.group(1).replace("/", ".")
        
    # 2. Vehicle Number
    m_veh = re.search(
        r'(?:वाहन|मोटर|कार|ट्रक|क्रमांक|क्र\.?)\s*([A-Z]{2}[-\s]*[0-9]{1,2}[-\s]*[A-Z]{1,2}[-\s]*[0-9]{4})', 
        flat_text, 
        re.IGNORECASE
    )
    if m_veh:
        res["vehicle_number"] = m_veh.group(1).strip()
        
    # 3. Police Station / FIR number
    m_th = re.search(r'(?:थाना|थाने)\s+([^\s,।\d]+)', flat_text)
    if m_th:
        res["police_station"] = f"थाना {m_th.group(1).strip()}"
    m_fir = re.search(r'(?:अपराध|क्र|क्रमांक|नं)\.?\s*[:\-]*\s*(\d+/\d{2,4})', flat_text)
    if m_fir:
        res["fir_number"] = m_fir.group(1).strip()
        
    # 4. Age
    m_age = re.search(r'(?:आयु|उम्र)\s*(\d+)\s*(?:वर्ष|साल)', flat_text)
    if not m_age:
        m_age = re.search(r'(\d+)\s*(?:वर्ष|साल)\s*(?:आयु|उम्र)', flat_text)
    if m_age:
        res["age"] = int(m_age.group(1))
        
    # 5. Claimant name
    m_name = re.search(r'(?:आवेदक|घायल|पीड़ित)\s+([^\s,।]+)\s+(?:पुत्र|पुत्री|पत्नी)\s+([^\s,।]+)', flat_text)
    if m_name:
        res["injured_name"] = _hi_trim_stopwords(m_name.group(1))
        res["father_name"] = _hi_trim_stopwords(m_name.group(2))
        
    return res

def extract_hindi_biographical_list(text_lines: list) -> dict:
    lines_norm = []
    for l in text_lines:
        line_clean = re.sub(r'[ \t]+', ' ', l).strip()
        lines_norm.append(line_clean)
        
    lbl_re = re.compile(r'^\s*(?:\[|\()? *([0-9]+|[०-९]+|[अ-ह]) *(?:\/[0-9]+|\/[०-९]+)? *(?:\]|\)|[\.\-\):])+ *(.*)$')
    
    extracted_fields = {}
    field_scores = {}
    consumed_indices = set()
    
    for i in range(len(lines_norm)):
        if i in consumed_indices:
            continue
        line = lines_norm[i]
        m = lbl_re.match(line)
        if not m:
            continue
            
        marker = m.group(1)
        rest = m.group(2).strip()
        
        val_num = None
        try:
            val_num = int(translate_deva_digits(marker))
        except ValueError:
            pass
            
        label_part, value_part = split_label_value(rest)
        
        best_field = None
        best_score = 0.0
        best_ratio = 0.0
        best_kw = None
        
        for field, keywords in HI_APPLICATION_FORM_FIELDS.items():
            for kw in keywords:
                matched, score = _hi_fuzzy_contains_with_score(label_part, kw)
                if matched:
                    ratio = fuzz.ratio(_hi_normalize_text(label_part), _hi_normalize_text(kw))
                    boosted_score = score + (0.1 if (val_num is not None and is_expected_index(field, val_num)) else 0.0)
                    
                    if boosted_score > best_score:
                        best_score = boosted_score
                        best_ratio = ratio
                        best_field = field
                        best_kw = kw
                    elif abs(boosted_score - best_score) < 0.01:
                        if ratio > best_ratio:
                            best_ratio = ratio
                            best_field = field
                            best_kw = kw
                            
        if best_field:
            if best_field in field_scores and field_scores[best_field] >= best_score:
                continue
            field_scores[best_field] = best_score
            if best_field not in ("other_case_info", "compensation_claimed"):
                if not is_usable_value(value_part):
                    lookahead_val = []
                    j = i + 1
                    while j < len(lines_norm) and j < i + 3:
                        if j in consumed_indices:
                            break
                        if lbl_re.match(lines_norm[j]) or is_totals_line(lines_norm[j]) or is_section_break(lines_norm[j]):
                            break
                        lookahead_val.append(lines_norm[j])
                        consumed_indices.add(j)
                        j += 1
                    if lookahead_val:
                        value_part = " ".join(lookahead_val)
                    
            if best_field == "other_case_info":
                block_lines = [value_part] if is_usable_value(value_part) else []
                j = i + 1
                while j < len(lines_norm):
                    if j in consumed_indices:
                        j += 1
                        continue
                    next_line = lines_norm[j]
                    if lbl_re.match(next_line) or is_section_break(next_line):
                        break
                    block_lines.append(next_line)
                    consumed_indices.add(j)
                    j += 1
                value_part = "\n".join(block_lines)
                
            elif best_field == "compensation_claimed":
                sub_items = []
                j = i + 1
                while j < len(lines_norm):
                    if j in consumed_indices:
                        j += 1
                        continue
                    next_line = lines_norm[j]
                    if is_section_break(next_line):
                        break
                        
                    m_next = lbl_re.match(next_line)
                    if m_next:
                        marker_next = m_next.group(1)
                        val_num_next = None
                        try:
                            val_num_next = int(translate_deva_digits(marker_next))
                        except ValueError:
                            pass
                            
                        next_label_part, _ = split_label_value(m_next.group(2).strip())
                        is_main_item = False
                        for f, kws in HI_APPLICATION_FORM_FIELDS.items():
                            if f == "compensation_claimed":
                                continue
                            for kw in kws:
                                matched, _ = _hi_fuzzy_contains_with_score(next_label_part, kw)
                                if matched:
                                    is_main_item = True
                                    break
                            if is_main_item:
                                break
                                
                        if is_main_item or (val_num_next is not None and val_num_next >= 15):
                            break
                            
                    if is_totals_line(next_line) or (m_next and (m_next.group(1) in "अबसदयरलछथजझ" or val_num_next is not None)):
                        sub_label, sub_val = "", ""
                        if m_next:
                            sub_label, sub_val = split_label_value(m_next.group(2).strip())
                        else:
                            sub_label, sub_val = split_label_value(next_line)
                            
                        if not sub_label:
                            sub_label = next_line
                        amt = parse_amount_from_line(sub_val or sub_label)
                        sub_items.append({"label": sub_label.strip(), "amount": amt if amt is not None else 0.0})
                        
                    consumed_indices.add(j)
                    j += 1
                extracted_fields["compensation_claimed_breakdown"] = sub_items
                
            extracted_fields[best_field] = value_part.strip()
            
    res = {}
    
    if "injured_name" in extracted_fields:
        name_val = extracted_fields["injured_name"]
        name_clean, name_addr = split_name_address(name_val)
        m_rel = re.search(r'(.+?)\s+(?:पुत्र|पुत्री|son of|daughter of|s/o|d/o|w/o|पत्नी|पिता|पति)\s+(?:श्री\s+|late\s+|स्व\.\s+)?(.+)', name_clean, re.IGNORECASE)
        if m_rel:
            res["injured_name"] = _hi_trim_stopwords(m_rel.group(1))
            res["father_name"] = _hi_trim_stopwords(m_rel.group(2))
        else:
            parts = re.split(r'[:\-—–]+', name_clean)
            if len(parts) >= 2:
                res["injured_name"] = _hi_trim_stopwords(parts[0])
                res["father_name"] = _hi_trim_stopwords(parts[1])
            else:
                res["injured_name"] = _hi_trim_stopwords(name_clean)
                
    if "father_name" in extracted_fields and "father_name" not in res:
        res["father_name"] = _hi_trim_stopwords(split_name_address(extracted_fields["father_name"])[0])
        
    if "address" in extracted_fields:
        res["address"] = extracted_fields["address"]
        
    if "age" in extracted_fields:
        m_age = re.search(r'(\d+)', translate_deva_digits(extracted_fields["age"]))
        if m_age:
            res["age"] = int(m_age.group(1))
            
    if "occupation" in extracted_fields:
        res["occupation"] = extracted_fields["occupation"]
        
    if "monthly_income" in extracted_fields:
        text_trans = translate_deva_digits(extracted_fields["monthly_income"])
        text_trans = re.sub(r'(?:प्रतिमाह|प्रति\s+माह|प्रतिमास|प्रति\s+मास|\/-\s*रुपये\s*प्रतिमाह|\/-\s*रूपये\s*प्रतिमाह)', '', text_trans)
        cleaned = text_trans.replace(',', '')
        m_num = re.search(r'(\d+(?:\.\d+)?)', cleaned)
        if m_num:
            try:
                res["monthly_income"] = float(m_num.group(1))
            except ValueError:
                pass
                
    if "date_of_accident" in extracted_fields:
        date_text = extracted_fields["date_of_accident"]
        dt = extract_date(date_text)
        if dt:
            res["date_of_accident"] = dt
        pl = extract_place(date_text)
        if pl:
            res["place_of_accident"] = pl
            
    if "place_of_accident" in extracted_fields:
        res["place_of_accident"] = extracted_fields["place_of_accident"]
        
    if "injury_description" in extracted_fields:
        res["injury_description"] = extracted_fields["injury_description"]
        
    if "vehicle_number" in extracted_fields:
        veh_val = extracted_fields["vehicle_number"]
        veh_val = re.sub(r'^(?:क\.-|क\-)', '', veh_val, flags=re.IGNORECASE).strip()
        veh_val = re.sub(r'\(.*?\)', '', veh_val).strip()
        res["vehicle_number"] = veh_val
        
    if "hospital_name" in extracted_fields:
        res["hospital_name"] = extracted_fields["hospital_name"]
        
    if "driver_name_address" in extracted_fields:
        d_name, d_addr = split_name_address(extracted_fields["driver_name_address"])
        if d_name:
            res["driver_name"] = _hi_trim_stopwords(split_relational_name(d_name))
        if d_addr:
            res["driver_address"] = d_addr
            
    if "owner_name_address" in extracted_fields:
        o_name, o_addr = split_name_address(extracted_fields["owner_name_address"])
        if o_name:
            res["owner_name"] = _hi_trim_stopwords(split_relational_name(o_name))
        if o_addr:
            res["owner_address"] = o_addr
            
    if "policy_number" in extracted_fields:
        res["policy_number"] = extracted_fields["policy_number"]
        
    if "insurance_company" in extracted_fields:
        res["insurance_company"] = extracted_fields["insurance_company"]
        
    if "is_income_tax_payer" in extracted_fields:
        res["is_income_tax_payer"] = parse_yes_no(extracted_fields["is_income_tax_payer"])
    if "was_traveling" in extracted_fields:
        res["was_traveling_in_vehicle"] = parse_yes_no(extracted_fields["was_traveling"])
        
    if "compensation_claimed_breakdown" in extracted_fields:
        res["compensation_claimed_breakdown"] = extracted_fields["compensation_claimed_breakdown"]
    if "other_case_info" in extracted_fields:
        res["other_case_info"] = extracted_fields["other_case_info"]
        
    if "fir_number" in extracted_fields:
        text = extracted_fields["fir_number"]
        m_fir = re.search(r'(?:अपराध|क्र|क्रमांक|नं)\.?\s*[:\-]*\s*(\d+/\d{2,4})', translate_deva_digits(text))
        if m_fir:
            res["fir_number"] = m_fir.group(1).strip()
        m_th = re.search(r'(थाना\s+[^\s,।\d]+)', text)
        if m_th:
            res["police_station"] = m_th.group(1).strip()
            
    if len(res) >= 1:
        is_claim_form = any(f in res for f in ("injured_name", "father_name", "address", "age", "occupation", "other_case_info"))
        if not is_claim_form:
            return None

        if "other_case_info" in res:
            if "fir_number" not in res:
                m_fir = re.search(r'(?:अपराध|क्र|क्रमांक|नं)\.?\s*[:\-]*\s*(\d+/\d{2,4})', translate_deva_digits(res["other_case_info"]))
                if m_fir:
                    res["fir_number"] = m_fir.group(1).strip()
            if "police_station" not in res:
                m_th = re.search(r'(थाना\s+[^\s,।\d]+)', res["other_case_info"])
                if m_th:
                    res["police_station"] = m_th.group(1).strip()

        # Build field confidences for standard biographical fields
        field_confidences = {}
        for f in list(res.keys()):
            source_field = f
            if f in ("injured_name", "father_name"):
                source_field = "injured_name" if "injured_name" in field_scores else "father_name"
            elif f == "place_of_accident":
                source_field = "place_of_accident" if "place_of_accident" in field_scores else "date_of_accident"
            elif f in ("driver_name", "driver_address"):
                source_field = "driver_name_address"
            elif f in ("owner_name", "owner_address"):
                source_field = "owner_name_address"
            elif f == "was_traveling_in_vehicle":
                source_field = "was_traveling"
                
            score = field_scores.get(source_field, 95.0)
            field_confidences[f] = min(0.99, score / 100.0)
            
        needs_manual_review = []
        
        if "compensation_claimed_breakdown" in res:
            CLAIM_FORM_COMPENSATION_HEAD_ALIASES = {
                "permanent_disability_amount": ["स्थायी अपंगता का", "स्थाई अपंगता का", "स्थायी निर्योग्यता का"],
                "pain_and_suffering":          ["दुख दर्द", "मानसिक परेशानी", "पीड़ा कष्ट"],
                "special_diet_transport_bundle": ["पौष्टिक आहार व आने जाने", "पोष्टिक आहार व आवागमन"],
                "medical_expenses":            ["इलाज", "आपरेशन", "दवाई खर्च", "दवाई का खर्च"],
                "attender_charges":            ["सहायक व्यय", "सहायक का खर्च"],
                "future_medical_expenses":     ["भविष्य में होने वाली इलाज", "भविष्य के इलाज का"],
            }
            
            # Count occurrences of each amount
            amount_counts = {}
            for item in res["compensation_claimed_breakdown"]:
                amt = item.get("amount", 0.0)
                if amt > 0:
                    amount_counts[amt] = amount_counts.get(amt, 0) + 1
                    
            for item in res["compensation_claimed_breakdown"]:
                label = item.get("label", "")
                amt = item.get("amount", 0.0)
                if not label or amt <= 0.0:
                    continue
                    
                best_field = None
                best_score = 0.0
                next_best_score = 0.0
                
                for field, aliases in CLAIM_FORM_COMPENSATION_HEAD_ALIASES.items():
                    for alias in aliases:
                        matched, score = _hi_fuzzy_contains_with_score(label, alias)
                        if matched:
                            if score > best_score:
                                next_best_score = best_score
                                best_score = score
                                best_field = field
                            elif score > next_best_score:
                                next_best_score = score
                                
                if best_field and best_score >= 80.0:
                    base_conf = min(0.99, best_score / 100.0)
                    
                    # Check for duplicate amount penalty
                    if amount_counts.get(amt, 0) > 1:
                        base_conf *= 0.7
                        needs_manual_review.append(
                            f"Low confidence: Multiple claim items share the same amount of {amt:.2f} (item label: '{label}')."
                        )
                        
                    # Check for ambiguity penalty
                    if (best_score - next_best_score) < 15.0:
                        base_conf *= 0.8
                        needs_manual_review.append(
                            f"Low confidence: Claim label '{label}' is ambiguous (next best match score close to best score)."
                        )
                    
                    # Assign to canonical fields
                    if best_field == "special_diet_transport_bundle":
                        target_field = BUNDLED_DIET_TRANSPORT_TARGET_FIELD or "special_diet"
                        if target_field not in res or field_confidences.get(target_field, 0.0) < base_conf:
                            res[target_field] = amt
                            field_confidences[target_field] = base_conf
                        
                        other_field = "transportation"
                        if other_field not in res or field_confidences.get(other_field, 0.0) < base_conf:
                            res[other_field] = 0.0
                            field_confidences[other_field] = base_conf
                    else:
                        if best_field not in res or field_confidences.get(best_field, 0.0) < base_conf:
                            res[best_field] = amt
                            field_confidences[best_field] = base_conf
                else:
                    if best_field:
                        needs_manual_review.append(
                            f"Low confidence match ignored: Claim label '{label}' matched '{best_field}' but score ({best_score:.1f}%) was below threshold."
                        )
            
            # Ensure 'disability' percentage is not incorrectly populated with an amount or wrong percentage
            res["disability"] = 0.0
            field_confidences["disability"] = 0.99

        res["field_confidences"] = field_confidences
        res["needs_manual_review"] = needs_manual_review
        return res
        
    fallback_res = extract_hindi_narrative_petition(text_lines)
    if fallback_res:
        return fallback_res
        
    return None

def _score_hindi_table_block(block: list, text_lines: list) -> tuple:
    score = 0.0
    if not block:
        return 0.0, False, False
    start_idx = block[0]["line_idx"]
    end_idx = block[-1]["line_idx"]
    
    # 1. Lookback for compensation heading keywords (up to 10 lines)
    lookback = 10
    start_lookback = max(0, start_idx - lookback)
    has_heading = False
    comp_kws = ["मुआवजा", "मुआवजे", "क्षतिपूर्ति", "प्रतिकर", "दावा", "compensation", "quantum"]
    for idx in range(start_lookback, start_idx):
        line = text_lines[idx].strip().lower()
        line_no_space = re.sub(r'\s+', '', line)
        if any(kw in line_no_space for kw in comp_kws):
            has_heading = True
            break
    if has_heading:
        score += 10.0
        
    # 2. Lookahead for end-anchor keywords (up to 10 lines)
    lookahead = 10
    end_lookahead = min(len(text_lines), end_idx + lookahead + 1)
    has_anchor = False
    
    for idx in range(end_idx + 1, end_lookahead):
        line = text_lines[idx].strip().lower()
        line_no_space = re.sub(r'\s+', '', line)
        
        # Look for "अन्य" along with an info keyword and a disposal/required keyword,
        # using fuzzed prefixes to resist OCR typos/character insertions
        has_any = any(x in line_no_space for x in ["अन्य", "anyother", "other"])
        has_info = any(x in line_no_space for x in ["जानक", "विवर", "सूचन", "detail", "info"])
        has_disp = any(x in line_no_space for x in ["निराक", "आवश्य", "अवश्य", "आवश्क", "निपटार", "required", "disposal", "necessary"])
        
        if (has_any and has_info and has_disp) or ("अन्यजानकारी" in line_no_space and "निराकरण" in line_no_space):
            has_anchor = True
            break
            
    if has_anchor:
        score += 10.0
        
    return score, has_heading, has_anchor


def extract_hindi_structural_block(text_lines: list) -> dict:
    """
    Detects a structural Hindi compensation block: a sequence of 5-9 consecutive short lines,
    matching the shape <short label><separator><description><separator><amount>, closed by a totals line.
    """
    lines_norm = []
    for l in text_lines:
        line_clean = re.sub(r'[ \t]+', ' ', l).strip()
        lines_norm.append(line_clean)
        
    total_lines = len(lines_norm)
    blocks = []
    i = 0
    while i < total_lines:
        line = lines_norm[i]
        m_lbl = _LBL_PAT.match(line)
        if m_lbl:
            label = m_lbl.group(1)
            rest = m_lbl.group(2)
            m_amt = _AMT_PAT.search(rest)
            if m_amt:
                block_lines = []
                j = i
                while j < total_lines:
                    current_line = lines_norm[j]
                    if is_totals_line(current_line):
                        block_lines.append({
                            "line_idx": j,
                            "line_text": current_line,
                            "is_totals": True
                        })
                        j += 1
                        break
                        
                    m_curr_lbl = _LBL_PAT.match(current_line)
                    if m_curr_lbl:
                        curr_label = m_curr_lbl.group(1)
                        curr_rest = m_curr_lbl.group(2)
                        m_curr_amt = _AMT_PAT.search(curr_rest)
                        if m_curr_amt:
                            curr_desc = curr_rest[:m_curr_amt.start()].strip(' |:-—=')
                            curr_amt_val = m_curr_amt.group(1)
                            block_lines.append({
                                "line_idx": j,
                                "line_text": current_line,
                                "label": curr_label,
                                "desc": curr_desc,
                                "amount_str": curr_amt_val
                            })
                            j += 1
                            continue
                    break
                
                structural_count = sum(1 for bl in block_lines if not bl.get("is_totals"))
                if 5 <= structural_count <= 9:
                    if check_structural_block_validity(block_lines):
                        blocks.append(block_lines)
                        i = j
                        continue
        i += 1
        
    if not blocks:
        return None
        
    # Score all blocks and select the highest scoring block.
    # We sort by score. Python's Timsort is stable, maintaining stability for tie-breakers (last wins).
    scored = []
    for b in blocks:
        s, hh, ha = _score_hindi_table_block(b, lines_norm)
        scored.append((s, hh, ha, b))
    scored.sort(key=lambda x: x[0])
    chosen_block = scored[-1][3]
    chosen_has_heading = scored[-1][1]
    chosen_has_anchor = scored[-1][2]
    
    block_pain_and_suffering = []
    block_loss_of_income = []
    block_medical_expenses = []
    block_special_diet = []
    block_transportation = []
    block_future_medical_expenses = []
    block_attender_charges = []
    
    block_sources = {}
    needs_manual_review = []
    explicit_zeros = set()
    rejected_fields = set()
    
    for item in chosen_block:
        if item.get("is_totals"):
            continue
        desc = item["desc"]
        amt_str = item["amount_str"]
        line_text = item["line_text"]
        amt_val = parse_isolated_amount(amt_str)
        
        is_nil = any(kw in amt_str.lower() for kw in ["निरंक", "शून्य", "nil"])
        
        classification = classify_hindi_line(desc)
        if not classification:
            needs_manual_review.append(line_text)
            continue
            
        if isinstance(classification, tuple) and classification[0] == "AMBIGUOUS":
            logger.warning(f"[HINDI PARSER] Ambiguous structural line: '{line_text}' matches {classification[1]}")
            needs_manual_review.append(line_text)
            continue
            
        class_name, subtype = classification
        
        # Plausibility Bounds Check
        field_name = None
        if class_name == "BUNDLE_D":
            field_name = BUNDLED_TRIPLE_TARGET_FIELD or "attender_charges"
        elif class_name == "BUNDLE_B":
            field_name = BUNDLED_FUTURE_TARGET_FIELD or "future_medical_expenses"
        elif class_name == "BUNDLE_C":
            field_name = BUNDLED_TRANSPORT_ATTENDER_TARGET_FIELD or "attender_charges"
        elif class_name == "BUNDLE_A":
            field_name = BUNDLED_DIET_TRANSPORT_TARGET_FIELD or "special_diet"
        elif class_name == "PAIN_AND_SUFFERING":
            field_name = "pain_and_suffering"
        elif class_name == "LOSS_OF_INCOME":
            field_name = "loss_of_income"
        elif class_name == "STANDALONE_FUTURE_MEDICAL":
            field_name = "future_medical_expenses"
        elif class_name == "STANDALONE_MEDICAL":
            field_name = "medical_expenses"
        elif class_name == "STANDALONE_DIET":
            field_name = "special_diet"
        elif class_name == "STANDALONE_TRANSPORT":
            field_name = "transportation"
        elif class_name == "STANDALONE_ATTENDER":
            field_name = "attender_charges"
            
        if field_name and not check_amount_plausibility(amt_val, field_name, line_text):
            rejected_fields.add(field_name)
            amt_val = 0.0
        
        if class_name == "BUNDLE_D":
            target = BUNDLED_TRIPLE_TARGET_FIELD
            if target == "attender_charges":
                block_attender_charges.append(amt_val)
                block_special_diet.append(0.0)
                block_transportation.append(0.0)
                if is_nil:
                    explicit_zeros.update(["attender_charges", "special_diet", "transportation"])
            elif target == "special_diet":
                block_special_diet.append(amt_val)
                block_attender_charges.append(0.0)
                block_transportation.append(0.0)
                if is_nil:
                    explicit_zeros.update(["attender_charges", "special_diet", "transportation"])
            else:
                block_transportation.append(amt_val)
                block_attender_charges.append(0.0)
                block_special_diet.append(0.0)
                if is_nil:
                    explicit_zeros.update(["attender_charges", "special_diet", "transportation"])
            block_sources["attender_charges"] = block_sources["special_diet"] = block_sources["transportation"] = f"Bundle D: '{line_text}'"
            
        elif class_name == "BUNDLE_B":
            target = BUNDLED_FUTURE_TARGET_FIELD
            if target == "future_medical_expenses":
                block_future_medical_expenses.append(amt_val)
                block_loss_of_income.append(0.0)
                if is_nil:
                    explicit_zeros.update(["future_medical_expenses", "loss_of_income"])
            else:
                block_loss_of_income.append(amt_val)
                block_future_medical_expenses.append(0.0)
                if is_nil:
                    explicit_zeros.update(["future_medical_expenses", "loss_of_income"])
            block_sources["future_medical_expenses"] = block_sources["loss_of_income"] = f"Bundle B: '{line_text}'"
            
        elif class_name == "BUNDLE_C":
            target = BUNDLED_TRANSPORT_ATTENDER_TARGET_FIELD
            if target == "attender_charges":
                block_attender_charges.append(amt_val)
                block_transportation.append(0.0)
                if is_nil:
                    explicit_zeros.update(["attender_charges", "transportation"])
            else:
                block_transportation.append(amt_val)
                block_attender_charges.append(0.0)
                if is_nil:
                    explicit_zeros.update(["attender_charges", "transportation"])
            block_sources["attender_charges"] = block_sources["transportation"] = f"Bundle C: '{line_text}'"
            
        elif class_name == "BUNDLE_A":
            target = BUNDLED_DIET_TRANSPORT_TARGET_FIELD
            if target == "special_diet":
                block_special_diet.append(amt_val)
                block_transportation.append(0.0)
                if is_nil:
                    explicit_zeros.update(["special_diet", "transportation"])
            else:
                block_transportation.append(amt_val)
                block_special_diet.append(0.0)
                if is_nil:
                    explicit_zeros.update(["special_diet", "transportation"])
            block_sources["special_diet"] = block_sources["transportation"] = f"Bundle A: '{line_text}'"
            
        elif class_name == "PAIN_AND_SUFFERING":
            block_pain_and_suffering.append(amt_val)
            if is_nil:
                explicit_zeros.add("pain_and_suffering")
            block_sources["pain_and_suffering"] = f"Rule 1{subtype or ''}: '{line_text}'"
            
        elif class_name == "LOSS_OF_INCOME":
            block_loss_of_income.append(amt_val)
            if is_nil:
                explicit_zeros.add("loss_of_income")
            block_sources["loss_of_income"] = f"Rule 2{subtype or ''}: '{line_text}'"
            
        elif class_name == "STANDALONE_FUTURE_MEDICAL":
            block_future_medical_expenses.append(amt_val)
            if is_nil:
                explicit_zeros.add("future_medical_expenses")
            block_sources["future_medical_expenses"] = f"Standalone future medical: '{line_text}'"
            
        elif class_name == "STANDALONE_MEDICAL":
            block_medical_expenses.append(amt_val)
            if is_nil:
                explicit_zeros.add("medical_expenses")
            block_sources["medical_expenses"] = f"Standalone medical: '{line_text}'"
            
        elif class_name == "STANDALONE_DIET":
            block_special_diet.append(amt_val)
            if is_nil:
                explicit_zeros.add("special_diet")
            block_sources["special_diet"] = f"Standalone diet: '{line_text}'"
            
        elif class_name == "STANDALONE_TRANSPORT":
            block_transportation.append(amt_val)
            if is_nil:
                explicit_zeros.add("transportation")
            block_sources["transportation"] = f"Standalone transport: '{line_text}'"
            
        elif class_name == "STANDALONE_ATTENDER":
            block_attender_charges.append(amt_val)
            if is_nil:
                explicit_zeros.add("attender_charges")
            block_sources["attender_charges"] = f"Standalone attendant: '{line_text}'"

    res = {}
    for f, lst in [
        ("pain_and_suffering", block_pain_and_suffering),
        ("loss_of_income", block_loss_of_income),
        ("medical_expenses", block_medical_expenses),
        ("special_diet", block_special_diet),
        ("transportation", block_transportation),
        ("future_medical_expenses", block_future_medical_expenses),
        ("attender_charges", block_attender_charges)
    ]:
        if f in explicit_zeros:
            res[f] = 0.0
        elif lst:
            res[f] = sum(lst)
        else:
            res[f] = 0.0
            
    return {
        "success": True,
        "fields": res,
        "sources": block_sources,
        "needs_manual_review": needs_manual_review,
        "explicit_zeros": explicit_zeros,
        "rejected_fields": rejected_fields,
        "has_heading": chosen_has_heading,
        "has_anchor": chosen_has_anchor
    }


def parse_hindi_extracted_text(text_lines: list, case_type: str = None) -> dict:
    """
    Highly advanced table-aware and heading-aware regex field extractor for Hindi Lower Court MACT judgments.
    Tolerates spelling variations and OCR errors, parses structured tables (both PP-Structure and markdown),
    and scores candidates based on visual structure and proximity to key award headings.
    
    Updated with generalized block detection, B, C, D bundles, and explicit nil handling.
    """
    logger.info("Starting advanced Hindi Lower Court MACT extraction pipeline...")
    
    out, conf = {}, {}
    rejected_fields = set()
    
    # 1. Clean and normalize lines
    lines_norm = []
    for l in text_lines:
        line_clean = re.sub(r'[ \t]+', ' ', l).strip()
        lines_norm.append(line_clean)
        
    total_lines = len(lines_norm)
    full_text = "\n".join(l for l in text_lines if not l.strip().startswith("--- PAGE"))
    flat = "\n".join(lines_norm)
    
    # 2. Trace award sections/headings
    AWARD_HEADINGS_REGEX = re.compile(
        r'(?:न्यायालय *श्रीमान *सदस्य *मोटर *दुर्घटना *दावा *अधिकरण|'
        r'मोटर *दुर्घटना *दावा *अधिकरण|'
        r'अधिनिर्णय|'
        r'दावा *आवेदन|'
        r'प्रतिकर *निर्धारण|'
        r'क्षतिपूर्ति|'
        r'प्रतिकर|'
        r'award|'
        r'compensation)',
        re.IGNORECASE
    )
    
    award_headings_found = []
    for idx, line in enumerate(lines_norm):
        if AWARD_HEADINGS_REGEX.search(line):
            award_headings_found.append((idx, line))
            logger.info(f"[HINDI PARSER] Found award heading at line {idx}: '{line}'")
            
    def get_award_heading_score(line_idx):
        for h_idx, _ in reversed(award_headings_found):
            if line_idx >= h_idx:
                return 50
        return 0

    # 4. Helper to extract numbers tolerating commas, dots, and trailing /-.
    def _extract_number_from_string(s, field):
        s_clean = re.sub(r'^\s*(?:\[|\()?\s*(?:\d+|[१२३४५६७८९०]+)\s*(?:\]|\)|[\.\-\)])\s*', '', s.strip())
        if not s_clean:
            return None
            
        if field == "disability":
            m = re.search(r'(\d{1,3})\s*[/:\-–]*\s*(?:%|प्रतिशत|percent)', s_clean, re.IGNORECASE)
            if m:
                val = int(m.group(1))
                if 1 <= val <= 100:
                    return val
            return None
        else:
            s_trans = translate_deva_digits(s_clean)
            pattern = r'\b(\d+(?:,\d+)*(?:\.\d+)?)\b'
            for m in re.finditer(pattern, s_trans):
                num_str = m.group(1).replace(',', '')
                try:
                    val = float(num_str)
                    if 1900 <= val <= 2030:
                        if val == 2000:
                            pass
                        else:
                            start, end = m.span()
                            if not _is_currency_adjacent(s_trans, start, end):
                                continue
                    if val in (2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026):
                        continue
                    if val >= 100:
                        return val
                except ValueError:
                    continue
            return None

    # 5. Core Candidate Search Logic
    def find_field_candidates(field, pattern_regex):
        candidates = []
        current_page = 1
        
        for idx, line in enumerate(lines_norm):
            if "--- PAGE" in line:
                m_pg = re.search(r'PAGE\s+(\d+)', line, re.IGNORECASE)
                if m_pg:
                    current_page = int(m_pg.group(1))
                continue
                
            # Exclude overlaps
            if field == "medical_expenses":
                if any(x in line.lower() for x in ["भविष्य", "भावी", "future"]):
                    continue
            if field == "monthly_income":
                if any(x in line.lower() for x in ["हानि", "नुकसान", "loss", "damage"]):
                    continue
                    
            if not re.search(pattern_regex, line, re.IGNORECASE):
                continue
                
            val = None
            is_table = "|" in line
            matched_text = line
            
            if is_table:
                cells = [c.strip() for c in line.split('|')]
                matched_cell_idx = -1
                for cell_idx, cell in enumerate(cells):
                    if re.search(pattern_regex, cell, re.IGNORECASE):
                        matched_cell_idx = cell_idx
                        break
                        
                if matched_cell_idx != -1:
                    for cell_idx in range(matched_cell_idx + 1, len(cells)):
                        num = _extract_number_from_string(cells[cell_idx], field)
                        if num is not None:
                            val = num
                            matched_text = f"Table Row Cell: '{cells[cell_idx]}' in line '{line}'"
                            break
                    if val is None and len(cells) > matched_cell_idx + 1:
                        num = _extract_number_from_string(cells[-1], field)
                        if num is not None:
                            val = num
                            matched_text = f"Table Row Last Cell: '{cells[-1]}' in line '{line}'"
                            
            if val is None:
                num = _extract_number_from_string(line, field)
                if num is not None:
                    val = num
                    matched_text = f"Same line paragraph: '{line}'"
                    
            if val is None:
                for offset in (1, 2):
                    if idx + offset < total_lines:
                        next_line = lines_norm[idx + offset]
                        if "--- PAGE" in next_line:
                            break
                        if "|" in next_line:
                            cells = [c.strip() for c in next_line.split('|') if c.strip()]
                            for cell_val in cells:
                                num = _extract_number_from_string(cell_val, field)
                                if num is not None:
                                    val = num
                                    matched_text = f"Next line table cell (offset {offset}): '{cell_val}' in line '{next_line}'"
                                    break
                        else:
                            num = _extract_number_from_string(next_line, field)
                            if num is not None:
                                val = num
                                matched_text = f"Next line paragraph (offset {offset}): '{next_line}'"
                                break
                    if val is not None:
                        break
                        
            if val is not None:
                table_bonus = 100 if is_table else 0
                heading_bonus = get_award_heading_score(idx)
                ratio_bonus = (idx / total_lines) * 20 if total_lines > 0 else 0
                total_score = table_bonus + heading_bonus + ratio_bonus
                
                candidates.append({
                    "value": val,
                    "score": total_score,
                    "page": current_page,
                    "is_table": is_table,
                    "matched_text": matched_text,
                    "line_idx": idx
                })
                
        return candidates

    COMPENSATION_FIELDS = {
        "monthly_income": (
            r'(?:मासिक *आय|प्रति *माह *आय|प्रतिमाह *आय|वेतन|मासिक *वेतन|मजदूरी|कमाई|आजीविका|आय *प्रमाण|salary|income|monthly *income|monthly *salary)',
            "Monthly Income"
        ),
        "disability": (
            r'(?:स्था[यीीइ]+.*(?:विकलांगता|अपंगता|अक्षमता|दिव्यांगता)|विक[लाांंगगंतताा]+|दिव्यांगता|अक्षमता|permanent *disability|functional *disability|disability)',
            "Permanent Disability (%)"
        ),
        "medical_expenses": (
            r'(?:(?:चिकित्स[ाा]?|उपचार|इलाज|मेडिकल|दवा|औषधि|अस्पताल|डॉ\.?|डॉक्टर).*(?:व्यय|खर्च|बर्बाद|राशि|फीस)|चिकित्स[ाा]? *व्यय|उपचार *व्यय|इलाज *खर्च|चिकित्स[ाा]? *खर्च|मेडिकल *खर्च|दवा *खर्च|औषधि *व्यय|अस्पताल *व्यय|medical *expenses|treatment *expenses|hospital *expenses)',
            "Medical Expenses"
        ),
        "future_medical_expenses": (
            r'(?:(?:भविष्य|भावी).*(?:चिकित्स[ाा]?|उपचार|इलाज|व्यय|खर्च|उपचार होने वाले व्यय)|भविष्य *चिकित्स[ाा]? *व्यय|भविष्य *उपचार *खर्च|भविष्य *इलाज *खर्च|भावी *चिकित्स[ाा]? *व्यय|भावी *उपचार *व्यय|future *medical *expenses|future *treatment *expenses)',
            "Future Medical Expenses"
        ),
        "pain_and_suffering": (
            r'(?:(?:मानसिक|शारीरिक|शारीरीक|वेदना|दुःख|कष्ट).*(?:पीड़ा|वेदना|कष्ट|दुःख)|पीड़ा|वेदना|दुःख *एवं *कष्ट|पीड़ा *एवं *वेदना|pain *and *suffering|pain *\& *suffering)',
            "Pain & Suffering"
        ),
        "transportation": (
            r'(?:(?:परिवहन|यातायात|यात्रा|आवागमन|आने *- *जाने|कन्वेयन्स).*(?:व्यय|खर्च|होने वाला|राशि)|परिवहन *व्यय|परिवहन *खर्च|यातायात *व्यय|यात्रा *व्यय|आने *- *जाने|आवागमन *व्यय|conveyance|transportation|transport)',
            "Transportation"
        ),
        "special_diet": (
            r'(?:(?:विशेष|पौष्टिक).*(?:आहार|भोजन|खुराक|व्यय|खर्च|खुराक व्यय|आहार व्यय)|विशेष *आहार|पौष्टिक *आहार|विशेष *भोजन|विशेष *खुराक|पोषण *व्यय|nutrition|special *diet)',
            "Special Diet"
        ),
        "attender_charges": (
            r'(?:(?:परिचारक|परिचर|अटेंडेंट|देखभाल|सेवक|सहायक).*(?:व्यय|खर्च|होने वाला|राशि)|परिचारक *व्यय|परिचर *व्यय|अटेंडेंट *खर्च|देखभाल *व्यय|सेवक *व्यय|सहायक *व्यय|nursing|attendant|attender)',
            "Attender Charges"
        ),
        "loss_of_income": (
            r'(?:(?:आय|वेतन|मजदूरी|कमाई|रोजगार|उपार्जन).*(?:हानि|नुकसान|अवधि)|आय *की *हानि|आय *में *हानि|आय *का *नुकसान|वेतन *हानि|मजदूरी *की *हानि|कमाई *का *नुकसान|रोजगार *हानि|उपार्जन *क्षमता|उपचार *अवधि|loss *of *income|loss *of *earnings|loss *of *wages)',
            "Loss of Income"
        ),
        "loss_of_future_prospects": (
            r'(?:भविष्य *में *(?:प्रगति|उन्नति|आय|विकास)|भविष्य *की *प्रगति|भविष्य *में *(?:आय|प्रगति|उन्नति).*वंचित|आय *प्राप्त *करने *से *वंचित|loss *of *future *prospects|loss *of *prospects|future *prospects)',
            "Loss of Future Prospects"
        ),
        "loss_of_amenities": (
            r'(?:आनंदपूर्ण *जीवन|सुखमय *जीवन|सुखी *जीवन|जीवन *के *सुखों|जीवन *के *आनंद|आनंद *से *वंचित|सुख *से *वंचित|भोग *की *हानि|आनंदपूर्ण.*वंचित|loss *of *amenities|loss *of *enjoyment|enjoyment *of *life)',
            "Loss of Amenities"
        ),
        "award_amount": (
            r'(?:कुल *प्रतिकर|कुल *क्षतिपूर्ति|प्रतिकर *राशि|कुल *अवार्ड|कुल *राशि|योग|कुल *क्षतिपूर्ति *राशि|कुल *प्रतिकर *राशि|award|total *compensation)',
            "Award Amount / Total Compensation"
        )
    }

    extraction_audit_logs = []

    # Extract all candidates for all fields first
    field_candidates = {}
    for field, (pattern, label) in COMPENSATION_FIELDS.items():
        field_candidates[field] = find_field_candidates(field, pattern)

    # Detect combined multi-head clauses sharing the same line and amount
    lines_to_candidates = {}
    for field, candidates in field_candidates.items():
        if field in ("award_amount", "monthly_income", "disability"):
            continue
        for c in candidates:
            lines_to_candidates.setdefault(c["line_idx"], []).append((field, c))

    combined_details = []
    combined_unallocated_amount = 0.0

    for line_idx, matched in lines_to_candidates.items():
        if len(matched) > 1:
            values = [c["value"] for field, c in matched]
            if len(set(values)) == 1:
                val = values[0]
                matched_fields = [field for field, c in matched]
                combined_unallocated_amount += val
                combined_details.append({
                    "line_idx": line_idx,
                    "line_text": lines_norm[line_idx],
                    "matched_fields": matched_fields,
                    "amount": val
                })
                for field, c in matched:
                    c["is_combined"] = True

    if combined_details:
        out["combined_unallocated_amount"] = combined_unallocated_amount
        out["combined_unallocated_details"] = combined_details
        conf["combined_unallocated_amount"] = 0.85
        log_msg = f"Combined Fields -> matched combined val={combined_unallocated_amount} across {len(combined_details)} clauses."
        logger.info(log_msg)
        extraction_audit_logs.append(log_msg)

    # Now select the best candidate for each field from the remaining non-combined candidates
    for field, (pattern, label) in COMPENSATION_FIELDS.items():
        candidates = field_candidates.get(field, [])
        valid_candidates = [c for c in candidates if not c.get("is_combined")]
        
        if valid_candidates:
            valid_candidates.sort(key=lambda x: x["score"], reverse=True)
            best = valid_candidates[0]
            out[field] = best["value"]
            conf[field] = 0.85 if best["score"] >= 100 else 0.70
            
            log_msg = (
                f"Field '{label}' -> matched candidate val={best['value']} "
                f"(score={best['score']:.1f}) on Page {best['page']}. "
                f"Source: {'Table' if best['is_table'] else 'Paragraph'} -> '{best['matched_text']}'"
            )
            logger.info(log_msg)
            extraction_audit_logs.append(log_msg)
        else:
            log_msg = f"Field '{label}' -> NOT found in document."
            logger.info(log_msg)
            extraction_audit_logs.append(log_msg)

    # 3. Ambient search check to determine if a line matches any rule
    def get_matched_rules(line_text: str):
        classification = classify_hindi_line(line_text)
        if not classification:
            return []
        if isinstance(classification, tuple) and classification[0] == "AMBIGUOUS":
            return [("AMBIGUOUS", classification[1])]
        
        class_name, subtype = classification
        mapping = {
            "PAIN_AND_SUFFERING": 1,
            "LOSS_OF_INCOME": 2,
            "STANDALONE_MEDICAL": 3,
            "BUNDLE_A": 4,
            "STANDALONE_ATTENDER": 5,
            "BUNDLE_B": 6,
            "BUNDLE_C": 7,
            "BUNDLE_D": 8,
            "STANDALONE_DIET": 9,
            "STANDALONE_TRANSPORT": 10,
            "STANDALONE_FUTURE_MEDICAL": 11
        }
        rule_num = mapping.get(class_name)
        if rule_num is not None:
            return [(rule_num, subtype)]
        return []

    def is_valid_disability_percentage(matched_num_str: str, match_start: int, full_text: str) -> bool:
        try:
            val = float(matched_num_str)
            if not (1.0 <= val <= 100.0):
                return False
        except ValueError:
            return False

        pre_text = full_text[:match_start]
        post_text = full_text[match_start + len(matched_num_str):]
        
        is_line_start = (len(pre_text.strip()) == 0) or (pre_text.endswith('\n') or re.search(r'\n\s*$', pre_text))
        is_followed_by_dot = post_text.startswith('.')
        
        if is_line_start and is_followed_by_dot:
            near_span = full_text[max(0, match_start - 15) : match_start + len(matched_num_str) + 15]
            if not ('%' in near_span or 'प्रतिशत' in near_span or 'percent' in near_span.lower()):
                logger.warning(f"[DISABILITY-REJECT] Rejected potential percentage value '{matched_num_str}' as list marker: context '{near_span.strip()}'")
                return False

        adjacent_span = full_text[max(0, match_start - 12) : match_start + len(matched_num_str) + 12]
        if not ('%' in adjacent_span or 'प्रतिशत' in adjacent_span or 'percent' in adjacent_span.lower()):
            logger.warning(f"[DISABILITY-REJECT] Rejected percentage value '{matched_num_str}': not adjacent to '%' or 'प्रतिशत' (adjacent span: '{adjacent_span.strip()}')")
            return False

        return True

    def get_number_from_text(text: str) -> float:
        text_trans = translate_deva_digits(text)
        cleaned = text_trans.replace(',', '')
        cleaned = re.sub(r'/(?:-)?', '', cleaned)
        cleaned = re.sub(r'[^\d.]', ' ', cleaned)
        nums = re.findall(r'\b\d+(?:\.\d+)?\b', cleaned)
        for num_str in reversed(nums):
            try:
                val = float(num_str)
                if 1900 <= val <= 2030:
                    if val != 2000:
                        start_idx = text_trans.find(num_str)
                        end_idx = start_idx + len(num_str)
                        if not _is_currency_adjacent(text_trans, start_idx, end_idx):
                            continue
                if val in (2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026):
                    continue
                if val >= 100:
                    return val
            except ValueError:
                continue
        return None

    def extract_amount_for_line(idx: int) -> float:
        line = lines_norm[idx]
        s_clean = re.sub(r'^\s*(?:\[|\()?\s*(?:\d+|[१२३४५६८९०]+)\s*(?:\]|\)|[\.\-\)])\s*', '', line.strip())
        
        if "|" in line:
            cells = [c.strip() for c in line.split('|') if c.strip()]
            for cell in reversed(cells):
                num = get_number_from_text(cell)
                if num is not None:
                    return num
                    
        num = get_number_from_text(s_clean)
        if num is not None:
            return num
            
        for offset in (1, 2):
            if idx + offset < total_lines:
                next_line = lines_norm[idx + offset]
                if "--- PAGE" in next_line:
                    break
                if get_matched_rules(next_line):
                    break
                if "|" in next_line:
                    cells = [c.strip() for c in next_line.split('|') if c.strip()]
                    for cell in reversed(cells):
                        num = get_number_from_text(cell)
                        if num is not None:
                            return num
                else:
                    num = get_number_from_text(next_line)
                    if num is not None:
                        return num
        return None

    # Narrative Disability Percentage
    narrative_disability = None
    flat_norm = flat.replace("स्थाई", "स्थायी").replace("निर्योग्यता", "अपंगता").replace("विकलांगता", "अपंगता")
    
    for m in re.finditer(r'स्थायी\s+अपंगता.{0,100}?(\d{1,3})\s*[/:\-–]*\s*(?:प्रतिशत|%)', flat_norm, re.DOTALL):
        num_str = m.group(1)
        if is_valid_disability_percentage(num_str, m.start(1), flat_norm):
            narrative_disability = float(num_str)
            break
            
    if narrative_disability is None:
        for m2 in re.finditer(r'(\d{1,3})\s*[/:\-–]*\s*(?:प्रतिशत|%).{0,100}?स्थायी\s+अपंगता', flat_norm, re.DOTALL):
            num_str = m2.group(1)
            if is_valid_disability_percentage(num_str, m2.start(1), flat_norm):
                narrative_disability = float(num_str)
                break

    # Apply structural block detection first
    struct_res = extract_hindi_structural_block(text_lines)
    if struct_res:
        logger.info("[HINDI PARSER] Structural table block detected! Applying priority overrides.")
        fields_map = struct_res["fields"]
        sources_map = struct_res["sources"]
        explicit_zeros = struct_res["explicit_zeros"]
        if "rejected_fields" in struct_res:
            rejected_fields.update(struct_res["rejected_fields"])
        
        has_heading = struct_res.get("has_heading", False)
        has_anchor = struct_res.get("has_anchor", False)
        
        if has_heading and has_anchor:
            block_conf = 0.96
        else:
            block_conf = 0.70
            if "needs_manual_review" not in out:
                out["needs_manual_review"] = []
            msg = "Low anchor matching confidence for structural table block: "
            if not has_heading:
                msg += "missing heading lookback. "
            if not has_anchor:
                msg += "missing end-anchor lookahead. "
            out["needs_manual_review"].append(msg.strip())
            
        # Override the 7 fields
        for field in [
            "pain_and_suffering", "loss_of_income", "medical_expenses",
            "special_diet", "transportation", "future_medical_expenses", "attender_charges"
        ]:
            val = fields_map.get(field, 0.0)
            if field in explicit_zeros:
                out[field] = 0.0
                conf[field] = block_conf
            else:
                out[field] = val
                conf[field] = block_conf
                
            log_msg = f"[FIELD] {field} = {out[field]}, matched_by=Hindi Structural Table Override, source_line='{sources_map.get(field, '')}'"
            logger.info(log_msg)
            extraction_audit_logs.append(log_msg)
            
        if struct_res.get("needs_manual_review"):
            if "needs_manual_review" not in out:
                out["needs_manual_review"] = []
            raw_review = struct_res["needs_manual_review"]
            if isinstance(raw_review, list):
                out["needs_manual_review"].extend(raw_review)
            else:
                out["needs_manual_review"].append(str(raw_review))
            
        out["loss_of_future_prospects"] = 0.0
        out["loss_of_amenities"] = 0.0
        out["explicit_zeros"] = explicit_zeros

        # Clear combined unallocated candidate search outputs
        out.pop("combined_unallocated_amount", None)
        out.pop("combined_unallocated_details", None)
    else:
        # Fallback to candidate search logic
        pain_and_suffering_parts = {"1A": [], "1B": []}
        loss_of_income_parts = {"2A": [], "2B": [], "2C": []}
        medical_expenses_vals = []
        bundled_vals = []
        attender_charges_vals = []
        
        bundle_b_vals = []
        bundle_c_vals = []
        bundle_d_vals = []
        standalone_diet_vals = []
        standalone_transport_vals = []
        standalone_future_medical_vals = []
        
        needs_manual_review_lines = []
        explicit_zeros = set()

        pain_and_suffering_sources = []
        loss_of_income_sources = []
        medical_expenses_sources = []
        bundled_sources = []
        attender_charges_sources = []

        # Define lists to hold line-specific match confidences
        ps_confs = []
        loi_confs = []
        med_confs = []
        diet_confs = []
        trans_confs = []
        att_confs = []
        fut_med_confs = []

        for idx in range(total_lines):
            line = lines_norm[idx]
            is_nil = any(kw in line.lower() for kw in ["निरंक", "शून्य", "nil"])
            
            _CURRENT_MATCH_SCORES.clear()
            matches = get_matched_rules(line)
            if len(matches) > 1:
                logger.warning(f"[HINDI PARSER] Ambiguous line: '{line}' matched multiple rules: {matches}")
                needs_manual_review_lines.append(line)
                continue
            elif len(matches) == 1:
                match_val = matches[0]
                if isinstance(match_val, tuple) and match_val[0] == "AMBIGUOUS":
                    logger.warning(f"[HINDI PARSER] Ambiguous line: '{line}' matched multiple bundles: {match_val[1]}")
                    needs_manual_review_lines.append(line)
                    continue
                    
                rule_num, sub_type = match_val
                amount = 0.0 if is_nil else extract_amount_for_line(idx)
                
                if amount is not None or is_nil:
                    amt = 0.0 if is_nil else amount
                    
                    # Calculate candidate confidence based on fuzzed ratios
                    line_score = sum(_CURRENT_MATCH_SCORES) / len(_CURRENT_MATCH_SCORES) if _CURRENT_MATCH_SCORES else 100.0
                    line_conf = round(line_score / 100.0, 3)
                    
                    field_name = None
                    if rule_num == 1:
                        field_name = "pain_and_suffering"
                    elif rule_num == 2:
                        field_name = "loss_of_income"
                    elif rule_num == 3:
                        field_name = "medical_expenses"
                    elif rule_num == 4:
                        field_name = BUNDLED_DIET_TRANSPORT_TARGET_FIELD or "special_diet"
                    elif rule_num == 5:
                        field_name = "attender_charges"
                    elif rule_num == 6:
                        field_name = BUNDLED_FUTURE_TARGET_FIELD or "future_medical_expenses"
                    elif rule_num == 7:
                        field_name = BUNDLED_TRANSPORT_ATTENDER_TARGET_FIELD or "attender_charges"
                    elif rule_num == 8:
                        field_name = BUNDLED_TRIPLE_TARGET_FIELD or "attender_charges"
                    elif rule_num == 9:
                        field_name = "special_diet"
                    elif rule_num == 10:
                        field_name = "transportation"
                    elif rule_num == 11:
                        field_name = "future_medical_expenses"

                    if field_name and not check_amount_plausibility(amt, field_name, line):
                        rejected_fields.add(field_name)
                        amt = 0.0
                    if rule_num == 1:
                        pain_and_suffering_parts[sub_type].append(amt)
                        pain_and_suffering_sources.append(f"Rule 1{sub_type}: '{line}' -> {amt}")
                        ps_confs.append(line_conf)
                        if is_nil:
                            explicit_zeros.add("pain_and_suffering")
                    elif rule_num == 2:
                        loss_of_income_parts[sub_type].append(amt)
                        loss_of_income_sources.append(f"Rule 2{sub_type}: '{line}' -> {amt}")
                        loi_confs.append(line_conf)
                        if is_nil:
                            explicit_zeros.add("loss_of_income")
                    elif rule_num == 3:
                        medical_expenses_vals.append(amt)
                        medical_expenses_sources.append(f"Rule 3: '{line}' -> {amt}")
                        med_confs.append(line_conf)
                        if is_nil:
                            explicit_zeros.add("medical_expenses")
                    elif rule_num == 4:
                        bundled_vals.append(amt)
                        bundled_sources.append(f"Rule 4 (Bundled A): '{line}' -> {amt}")
                        diet_confs.append(line_conf)
                        trans_confs.append(line_conf)
                        if is_nil:
                            explicit_zeros.update(["special_diet", "transportation"])
                    elif rule_num == 5:
                        attender_charges_vals.append(amt)
                        attender_charges_sources.append(f"Rule 5: '{line}' -> {amt}")
                        att_confs.append(line_conf)
                        if is_nil:
                            explicit_zeros.add("attender_charges")
                    elif rule_num == 6:
                        bundle_b_vals.append(amt)
                        fut_med_confs.append(line_conf)
                        loi_confs.append(line_conf)
                        if is_nil:
                            explicit_zeros.update(["future_medical_expenses", "loss_of_income"])
                    elif rule_num == 7:
                        bundle_c_vals.append(amt)
                        trans_confs.append(line_conf)
                        att_confs.append(line_conf)
                        if is_nil:
                            explicit_zeros.update(["attender_charges", "transportation"])
                    elif rule_num == 8:
                        bundle_d_vals.append(amt)
                        att_confs.append(line_conf)
                        diet_confs.append(line_conf)
                        trans_confs.append(line_conf)
                        if is_nil:
                            explicit_zeros.update(["attender_charges", "special_diet", "transportation"])
                    elif rule_num == 9:
                        standalone_diet_vals.append(amt)
                        diet_confs.append(line_conf)
                        if is_nil:
                            explicit_zeros.add("special_diet")
                    elif rule_num == 10:
                        standalone_transport_vals.append(amt)
                        trans_confs.append(line_conf)
                        if is_nil:
                            explicit_zeros.add("transportation")
                    elif rule_num == 11:
                        standalone_future_medical_vals.append(amt)
                        fut_med_confs.append(line_conf)
                        if is_nil:
                            explicit_zeros.add("future_medical_expenses")

        # Determine bundle targets
        has_bundle = False
        
        # Bundle A (Diet/Transport)
        diet_from_bundle_a = 0.0
        trans_from_bundle_a = 0.0
        if bundled_vals:
            has_bundle = True
            bundled_amount_a = sum(bundled_vals)
            if BUNDLED_DIET_TRANSPORT_TARGET_FIELD == "special_diet":
                diet_from_bundle_a = bundled_amount_a
                out["transportation"] = 0.0
                conf["transportation"] = 0.90
            else:
                trans_from_bundle_a = bundled_amount_a
                out["special_diet"] = 0.0
                conf["special_diet"] = 0.90
                
        # Bundle B (Future Income + Future Medical)
        future_med_from_bundle_b = 0.0
        income_from_bundle_b = 0.0
        if bundle_b_vals:
            has_bundle = True
            bundled_amount_b = sum(bundle_b_vals)
            if BUNDLED_FUTURE_TARGET_FIELD == "future_medical_expenses":
                future_med_from_bundle_b = bundled_amount_b
                out["loss_of_income"] = 0.0
                conf["loss_of_income"] = 0.90
            else:
                income_from_bundle_b = bundled_amount_b
                out["future_medical_expenses"] = 0.0
                conf["future_medical_expenses"] = 0.90
                
        # Bundle C (Transport + Attender)
        trans_from_bundle_c = 0.0
        attender_from_bundle_c = 0.0
        if bundle_c_vals:
            has_bundle = True
            bundled_amount_c = sum(bundle_c_vals)
            if BUNDLED_TRANSPORT_ATTENDER_TARGET_FIELD == "attender_charges":
                attender_from_bundle_c = bundled_amount_c
                out["transportation"] = 0.0
                conf["transportation"] = 0.90
            else:
                trans_from_bundle_c = bundled_amount_c
                out["attender_charges"] = 0.0
                conf["attender_charges"] = 0.90
                
        # Bundle D (Attender + Diet + Transport)
        attender_from_bundle_d = 0.0
        diet_from_bundle_d = 0.0
        trans_from_bundle_d = 0.0
        if bundle_d_vals:
            has_bundle = True
            bundled_amount_d = sum(bundle_d_vals)
            target = BUNDLED_TRIPLE_TARGET_FIELD
            if target == "attender_charges":
                attender_from_bundle_d = bundled_amount_d
                out["special_diet"] = 0.0
                conf["special_diet"] = 0.90
                out["transportation"] = 0.0
                conf["transportation"] = 0.90
            elif target == "special_diet":
                diet_from_bundle_d = bundled_amount_d
                out["attender_charges"] = 0.0
                conf["attender_charges"] = 0.90
                out["transportation"] = 0.0
                conf["transportation"] = 0.90
            else:
                trans_from_bundle_d = bundled_amount_d
                out["attender_charges"] = 0.0
                conf["attender_charges"] = 0.90
                out["special_diet"] = 0.0
                conf["special_diet"] = 0.90

        if has_bundle:
            out["bundled_source"] = True

        # Aggregate pain and suffering (always overwrite)
        pain_and_suffering_sum = sum(pain_and_suffering_parts["1A"]) + sum(pain_and_suffering_parts["1B"])
        if "pain_and_suffering" in explicit_zeros:
            out["pain_and_suffering"] = 0.0
            conf["pain_and_suffering"] = 0.99
        else:
            out["pain_and_suffering"] = pain_and_suffering_sum
            conf["pain_and_suffering"] = sum(ps_confs) / len(ps_confs) if ps_confs else 0.0
            if pain_and_suffering_sum > 0:
                log_msg = f"[FIELD] pain_and_suffering = {out['pain_and_suffering']}, matched_by=parse_hindi_extracted_text (candidate fallback), source_line='{'; '.join(pain_and_suffering_sources)}'"
                logger.info(log_msg)
                extraction_audit_logs.append(log_msg)

        # Aggregate loss of income (always overwrite)
        loss_of_income_sum = sum(loss_of_income_parts["2A"]) + sum(loss_of_income_parts["2B"]) + sum(loss_of_income_parts["2C"]) + income_from_bundle_b
        if "loss_of_income" in explicit_zeros:
            out["loss_of_income"] = 0.0
            conf["loss_of_income"] = 0.99
            out["loss_of_future_prospects"] = 0.0
            conf["loss_of_future_prospects"] = 0.99
            out["loss_of_amenities"] = 0.0
            conf["loss_of_amenities"] = 0.99
        else:
            out["loss_of_income"] = loss_of_income_sum
            conf["loss_of_income"] = sum(loi_confs) / len(loi_confs) if loi_confs else 0.0
            if loss_of_income_sum > 0:
                log_msg = f"[FIELD] loss_of_income = {out['loss_of_income']}, matched_by=parse_hindi_extracted_text (candidate fallback), source_line='{'; '.join(loss_of_income_sources)}'"
                logger.info(log_msg)
                extraction_audit_logs.append(log_msg)
            
            if loss_of_income_parts["2A"]:
                out["loss_of_future_prospects"] = sum(loss_of_income_parts["2A"])
                conf["loss_of_future_prospects"] = sum(loi_confs) / len(loi_confs) if loi_confs else 0.0
            else:
                out["loss_of_future_prospects"] = 0.0
                conf["loss_of_future_prospects"] = 0.0
                
            if loss_of_income_parts["2B"]:
                out["loss_of_amenities"] = sum(loss_of_income_parts["2B"])
                conf["loss_of_amenities"] = sum(loi_confs) / len(loi_confs) if loi_confs else 0.0
            else:
                out["loss_of_amenities"] = 0.0
                conf["loss_of_amenities"] = 0.0

        # Aggregate medical expenses (always overwrite)
        med_sum = sum(medical_expenses_vals)
        if "medical_expenses" in explicit_zeros:
            out["medical_expenses"] = 0.0
            conf["medical_expenses"] = 0.99
        else:
            out["medical_expenses"] = med_sum
            conf["medical_expenses"] = sum(med_confs) / len(med_confs) if med_confs else 0.0
            if med_sum > 0:
                log_msg = f"[FIELD] medical_expenses = {out['medical_expenses']}, matched_by=parse_hindi_extracted_text (candidate fallback), source_line='{'; '.join(medical_expenses_sources)}'"
                logger.info(log_msg)
                extraction_audit_logs.append(log_msg)

        # Special Diet
        diet_sum = sum(standalone_diet_vals) + diet_from_bundle_a + diet_from_bundle_d
        if "special_diet" in explicit_zeros:
            out["special_diet"] = 0.0
            conf["special_diet"] = 0.99
        elif diet_sum > 0:
            out["special_diet"] = diet_sum
            conf["special_diet"] = sum(diet_confs) / len(diet_confs) if diet_confs else 0.0
        else:
            if "special_diet" not in out:
                out["special_diet"] = 0.0
                conf["special_diet"] = 0.0

        # Transportation
        trans_sum = sum(standalone_transport_vals) + trans_from_bundle_a + trans_from_bundle_c + trans_from_bundle_d
        if "transportation" in explicit_zeros:
            out["transportation"] = 0.0
            conf["transportation"] = 0.99
        elif trans_sum > 0:
            out["transportation"] = trans_sum
            conf["transportation"] = sum(trans_confs) / len(trans_confs) if trans_confs else 0.0
        else:
            if "transportation" not in out:
                out["transportation"] = 0.0
                conf["transportation"] = 0.0

        # Attender charges
        att_sum = sum(attender_charges_vals) + attender_from_bundle_c + attender_from_bundle_d
        if "attender_charges" in explicit_zeros:
            out["attender_charges"] = 0.0
            conf["attender_charges"] = 0.99
        elif att_sum > 0:
            out["attender_charges"] = att_sum
            conf["attender_charges"] = sum(att_confs) / len(att_confs) if att_confs else 0.0
        else:
            if "attender_charges" not in out:
                out["attender_charges"] = 0.0
                conf["attender_charges"] = 0.0

        # Future medical expenses
        future_med_sum = sum(standalone_future_medical_vals) + future_med_from_bundle_b
        if "future_medical_expenses" in explicit_zeros:
            out["future_medical_expenses"] = 0.0
            conf["future_medical_expenses"] = 0.99
        elif future_med_sum > 0:
            out["future_medical_expenses"] = future_med_sum
            conf["future_medical_expenses"] = sum(fut_med_confs) / len(fut_med_confs) if fut_med_confs else 0.0
        else:
            if "future_medical_expenses" not in out:
                out["future_medical_expenses"] = 0.0
                conf["future_medical_expenses"] = 0.0

        if "needs_manual_review" not in out:
            out["needs_manual_review"] = []
        out["needs_manual_review"].append("Felled back to candidate search logic: no structural table block detected.")
        if needs_manual_review_lines:
            out["needs_manual_review"].extend(needs_manual_review_lines)
            
        out["explicit_zeros"] = explicit_zeros

    # Narrative Disability Percentage (Always overrides, regardless of structural or fallback path)
    if narrative_disability is not None:
        out["disability"] = narrative_disability
        conf["disability"] = 0.95
        out["permanent_disability_percentage"] = narrative_disability
    else:
        if "disability" not in out:
            out["disability"] = ""
            conf["disability"] = 0.0
# ---- safety net verification ------------------------------------------------
    rupee_heads = [
        "medical_expenses",
        "future_medical_expenses",
        "pain_and_suffering",
        "transportation",
        "special_diet",
        "attender_charges",
        "loss_of_income",
        "loss_of_future_prospects",
        "loss_of_amenities"
    ]
    heads_sum = sum(out.get(f, 0.0) for f in rupee_heads)
    if "combined_unallocated_amount" in out:
        heads_sum += out["combined_unallocated_amount"]

    award_total = out.get("award_amount", 0.0)
    if award_total > 0.0:
        difference = abs(heads_sum - award_total)
        if difference > 10.0:
            out["mismatch_warning"] = True
            out["mismatch_details"] = f"Sum of extracted heads ({heads_sum:,.2f}) does not match total award ({award_total:,.2f})"
            logger.warning(f"[HINDI PARSER] Safety Net Warning: {out['mismatch_details']}")
        else:
            out["mismatch_warning"] = False

    # ---- name + father's name -------------------------------------------------
    m = re.search(rf'(?:नाम(?: और| एवं|/)? पिता का नाम|Name\s*(?:&|and|/)?\s*Father\'s\s*Name) *(?:[:\-]+)? *({_HI_NAME_SPAN_WIDE})', flat, re.IGNORECASE)
    if m:
        val = m.group(1).strip()
        m2 = re.match(rf'^({_HI_NAME_SPAN_WIDE}?) *(?:पुत्र|पुत्री|son of|daughter of|s/o|d/o|w/o|पत्नी|husband of) +(?:श्री|shri|late|स्व\.)? *({_HI_NAME_SPAN_WIDE})$', val, re.IGNORECASE)
        if m2:
            out["injured_name"] = _hi_trim_stopwords(m2.group(1))
            out["father_name"] = _hi_trim_stopwords(m2.group(2))
            conf["injured_name"] = conf["father_name"] = 0.90

    if "injured_name" not in out:
        m = re.search(rf'({_HI_NAME_SPAN}) +(?:पुत्र|पुत्री|son of|daughter of|s/o|d/o|w/o|पत्नी) +(?:श्री +|shri +|late +|स्व\. +)?({_HI_NAME_SPAN})', flat, re.IGNORECASE)
        if m:
            out["injured_name"] = _hi_trim_stopwords(m.group(1))
            out["father_name"] = _hi_trim_stopwords(m.group(2))
            conf["injured_name"] = conf["father_name"] = 0.65

    # ---- age --------------------------------------------------------------
    m = re.search(r'(?:आयु|उम्र|age) *(?:लगभग)?[ \-:]*?(\d{1,3}) *(?:वर्ष|years|yrs)', flat, re.IGNORECASE)
    if m:
        out["age"] = int(m.group(1))
        conf["age"] = 0.85

    # ---- date of accident ---------------------------------------------------
    m = re.search(r'(?:दिनांक|date of accident|accident date) *(?:[:\-]+)? *(\d{1,2}[./-]\d{1,2}[./-]\d{4})', flat, re.IGNORECASE)
    if m:
        out["date_of_accident"] = m.group(1).replace("/", ".")
        conf["date_of_accident"] = 0.55

    # ---- vehicle number -------------------------------------------------------
    m = re.search(
        r'(?:मो\.? *सा\.?|वाहन|क\.-|क)? *(?:क्रं|क्रमांक|नं|क\.-|क)?\.? *([A-Z]{2}[ \-]?\d{1,2}[ \-]?[A-Z]{1,3}[ \-]?\d{3,4})',
        flat, re.IGNORECASE
    )
    if m:
        val = m.group(1).strip()
        val = re.sub(r'^(?:क\.-|क\-)', '', val, flags=re.IGNORECASE).strip()
        out["vehicle_number"] = val
        conf["vehicle_number"] = 0.75

    # ---- policy number ---------------------------------------------------------
    m = re.search(r'(?:पॉलिसी|पालिसी) *(?:कवर *नोट)? *(?:नंबर|नं|no|num)?\.? *([A-Za-z0-9\-/]{5,20})', flat, re.IGNORECASE)
    if m:
        out["policy_number"] = m.group(1).strip()
        conf["policy_number"] = 0.75

    # ---- insurance company -------------------------------------------------------
    ins_self_pat = re.compile(
        r'(?:बीमा *कंपनी|बीमाकर्ता|बीमा *कम्पनी|बीमा *पालिसी|बीमा *पॉलिसी|insurer|insurance *company|ins. *co.) *[:\-]+ *(स्वयं|स्व\.|स्वयं *का)',
        re.IGNORECASE
    )
    m_self = ins_self_pat.search(flat)
    if m_self:
        out["insurance_company"] = m_self.group(1).strip()
        conf["insurance_company"] = 0.90
    else:
        m = re.search(
            rf'({_HI_NAME_SPAN} +(?:इन्शोरेंस|इंश्योरेंस|इंश्योरेन्स|इन्श्योरेंस) +{_HI_NAME_TOK}(?: +{_HI_NAME_TOK}){{0,2}})',
            flat
        )
        if m:
            out["insurance_company"] = m.group(1).strip()
            conf["insurance_company"] = 0.70

    # ---- biographical list override ----
    bio_res = extract_hindi_biographical_list(text_lines)
    if bio_res:
        logger.info("[HINDI PARSER] Biographical list format detected! Applying updates to biographical fields.")
        bio_confs = bio_res.pop("field_confidences", {})
        bio_review = bio_res.pop("needs_manual_review", [])
        if bio_review:
            if "needs_manual_review" not in out:
                out["needs_manual_review"] = []
            out["needs_manual_review"].extend(bio_review)
            
        for k, val in bio_res.items():
            if val is not None and val != "":
                if k == "police_station":
                    logger.info(f"Follow-up field addition: police_station field does not exist, logged for future addition. Value: {val}")
                    if not out.get("fir_number"):
                        out["fir_number"] = val
                        conf["fir_number"] = bio_confs.get(k, 0.70)
                out[k] = val
                conf[k] = bio_confs.get(k, 0.95)

    # ---- case type: death vs injury ----------------------------------------------
    if case_type is not None:
        out["case_type"] = case_type
    else:
        from backend.llm_client import classify_case_type_by_ocr_text
        detected = classify_case_type_by_ocr_text(flat)
        if detected is not None:
            out["case_type"] = detected
        else:
            death_kws = ["मृत्यु", "मृतक", "स्वर्गीय", "दिवंगत"]
            injury_kws = ["उपहति", "क्षतिग्रस्त", "घायल", "चोट", "अपंगता", "निर्योग्यता", "विकलांगता"]
            death_hits = sum(flat.count(k) for k in death_kws)
            injury_hits = sum(flat.count(k) for k in injury_kws)
            out["case_type"] = "death" if death_hits > injury_hits else "injury"

    if out["case_type"] == "death":
        out["disability"] = ""
        if "disability" in conf:
            conf["disability"] = 0.0
        for f in ["pain_and_suffering", "loss_of_income", "medical_expenses", "special_diet", "transportation", "future_medical_expenses", "attender_charges", "loss_of_future_prospects", "loss_of_amenities"]:
            out[f] = 0.0
            if f in conf:
                conf[f] = 0.0

    # ---- case number (metadata, not a calculator field, kept for traceability) --
    m = re.search(
        r'(?:एम\.?ए\.?सी\.?सी\.?|MACC)[.\s]*(?:क्\.?|No\.?|नं\.?)? *[-–:]? *(\d{1,6} */ *\d{4})',
        flat, re.IGNORECASE
    )
    if m:
        out["case_number"] = m.group(1).replace(" ", "")

    for field in rejected_fields:
        out[field] = None
        conf[field] = 0.0

    out["confidence_scores"] = {k: {"confidence": v} for k, v in conf.items()}
    out["ai_recovery_triggered"] = False
    out["extraction_audit_logs"] = extraction_audit_logs

    # ---- AI Data Recovery Fallback (Hindi lower court) -----------------------
    critical_missing = (
        (out.get("case_type") == "injury" and (not out.get("disability") or not out.get("monthly_income") or not out.get("medical_expenses"))) or
        (out.get("case_type") == "death" and (not out.get("monthly_income") or not out.get("award_amount")))
    )
    if critical_missing:
        try:
            from backend.llm_client import ai_data_recovery
            recovered = ai_data_recovery(full_text, track="lower_court", case_type=out.get("case_type"))
            if recovered and not recovered.get("ai_recovery_error"):
                out["ai_recovery_triggered"] = True
                for key, val in recovered.items():
                    if val is not None and val != "":
                        target_key = "disability" if key == "disability_percentage" else key
                        current_val = out.get(target_key)
                        current_conf = conf.get(target_key, 0.0)
                        if not current_val or current_conf < 0.70:
                            out[target_key] = val
                            out["confidence_scores"][target_key] = {"confidence": 0.90}
        except Exception as e:
            logger.error(f"AI data recovery failed during Hindi parsing: {e}")

    return out


def extract_age_from_text(raw_text: str, claimant_name: str = None, deceased_name: str = None, case_type: str = None) -> tuple:
    """
    Scans raw text to extract age based on proximity to claimant/deceased name,
    falling back to global regex scans.
    Returns: (age: int | None, context_snippet: str | None)
    """
    if not raw_text:
        return None, None
        
    # Lightweight English age regexes
    patterns = [
        r'\baged?\s+(?:about\s+)?(\d{1,3})\s*years?\b',
        r'\b(\d{1,3})\s*years?\s+old\b',
        r'\b(?:age|aged)\s*(?:about|is|was)?\s*[:\-;]?\s*(\d{1,3})\b',
        r'\b(\d{1,3})\s*(?:years|yrs)\b'
    ]
    
    # 1. Proximity scan based on target name
    target_names = []
    if case_type == "death":
        if deceased_name:
            target_names.append((deceased_name, "deceased"))
        if claimant_name:
            target_names.append((claimant_name, "claimant"))
    else:
        # injury or default
        if claimant_name:
            target_names.append((claimant_name, "claimant/injured"))
        if deceased_name:
            target_names.append((deceased_name, "deceased"))
            
    for name_val, role_label in target_names:
        # Tokenize name and take first long token to scan
        tokens = [t for t in name_val.split() if len(t) > 2]
        if not tokens:
            continue
        search_term = tokens[0]
        
        pos = 0
        while True:
            idx = raw_text.lower().find(search_term.lower(), pos)
            if idx == -1:
                break
            
            # Extract proximity window
            w_start = max(0, idx - 150)
            w_end = min(len(raw_text), idx + len(search_term) + 150)
            window = raw_text[w_start:w_end]
            
            best_val = None
            min_distance = 999999
            term_idx_in_window = idx - w_start
            
            for pat in patterns:
                for m in re.finditer(pat, window, re.IGNORECASE):
                    val = int(m.group(1))
                    if 1 <= val <= 100:
                        match_center = (m.start() + m.end()) / 2
                        dist = abs(match_center - term_idx_in_window)
                        if dist < min_distance:
                            min_distance = dist
                            best_val = val
                            
            if best_val is not None:
                snippet = window.replace("\n", " ").strip()
                logger.info(f"[AGE-EXTRACTOR] Extracted age {best_val} near {role_label} name '{name_val}' (dist={min_distance:.1f}) in window: '{snippet}'")
                return best_val, snippet
            pos = idx + len(search_term)

    # 2. General role-anchored regex fallbacks
    role_anchored_patterns = [
        r'\b(?:deceased|injured|claimant)\s*(?:person)?\s+(?:was\s+)?aged?\s*(?:about\s+)?(\d{1,3})\b',
        r'\b(?:age|aged)\s+of\s+the?\s*(?:deceased|injured|claimant)\s*(?:is|was|[:\-;])?\s*(\d{1,3})\b',
    ]
    for pat in role_anchored_patterns:
        m = re.search(pat, raw_text, re.IGNORECASE)
        if m:
            val = int(m.group(1))
            if 1 <= val <= 100:
                logger.info(f"[AGE-EXTRACTOR] Extracted age {val} globally using role-anchored pattern '{pat}'")
                return val, f"Global match: {m.group(0)}"
                
    # 3. Global scan fallback
    for pat in patterns[:3]: # limit to slightly more specific patterns globally
        for m in re.finditer(pat, raw_text, re.IGNORECASE):
            val = int(m.group(1))
            if 5 <= val <= 100: # tighter guard for general scan
                logger.info(f"[AGE-EXTRACTOR] Extracted age {val} globally using fallback pattern '{pat}'")
                return val, f"Global match: {m.group(0)}"
                
    return None, None


