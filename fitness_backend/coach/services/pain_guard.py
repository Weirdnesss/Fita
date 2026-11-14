"""
Rule-based pain/injury guard for the coach chat.

Pain and medical topics are where a wrong or over-confident answer does the
most harm, and a long rule list in the prompt is not followed reliably. So
this is decided by plain code, not by the model: if the latest message (or
the one before a bare "continue") mentions pain, stiffness or a possible
injury, the coach answers in a short, fixed shape and ignores the Detailed
setting for that message.

It errs on the side of caution: a false positive only means a short, safe
reply; a false negative would mean the normal prompt rules apply.
"""

import re

PAIN_WORDS = re.compile(
    r"\b(pain|painful|hurt|hurts|hurting|ache|aches|aching|sprain\w*|strain\w*|pulled|torn|"
    r"injur\w*|swollen|swelling|numb\w*|tingling|dizzy|dizziness|faint\w*|cramp\w*|clicking|stiff\w*)\b",
    re.IGNORECASE,
)
BODY_PARTS = re.compile(
    r"\b(knees?|shoulders?|elbows?|wrists?|ankles?|hips?|neck|lower back|joints?|spine|back|legs?)\b",
    re.IGNORECASE,
)
FEELING_WORDS = re.compile(
    r"\b(feel|feels|felt|feeling|weird|funny|tight|locked|unstable|weak|clicks|catches|giving way|"
    r"harder to move|hard to move|can't bend|cannot bend|won't bend)\b",
    re.IGNORECASE,
)
CONTINUE_ONLY = re.compile(
    r"^\W*(please\s+)?(continue|go on|keep going|more|tell me more|next|and)\W*$",
    re.IGNORECASE,
)

PAIN_MAX_TOKENS = 500

PAIN_SYSTEM_BLOCK = (
    "## PAIN OR INJURY MODE\n"
    "The user has mentioned pain, stiffness, or a possible injury. This replaces any Detailed-mode "
    "length and style instruction. Reply in at most 70 words, in plain sentences with no headings, "
    "lists, or tables. Say only: (1) avoid movements that hurt and go lighter or rest, (2) the warning "
    "signs that need care (sharp pain, swelling, a feeling of instability, or pain that persists or gets "
    "worse), and (3) that a doctor or physical therapist should check it. Do not give exercises, stretches, "
    "ice or compression routines, numbers, or possible causes. Do not say that any exercise or activity is "
    "safe for their medical condition; if you mention their condition, say a doctor needs to clear it. "
    "If they say they will not see a doctor, respect that without lecturing, and repeat once that pain "
    "that persists should be checked."
)

PAIN_REMINDER = (
    "[Reply under 70 words with no lists or headings: avoid painful movements, rest, warning signs, "
    "see a professional. No exercises, stretches, numbers, or causes. Do not say anything is safe for "
    "their medical condition.]"
)


def is_pain_message(text):
    """True if one message mentions pain, stiffness or a possible injury."""
    if not text:
        return False
    return bool(PAIN_WORDS.search(text) or (BODY_PARTS.search(text) and FEELING_WORDS.search(text)))


def is_pain_conversation(user_texts):
    """
    user_texts: the user's recent messages, newest first.
    True if the newest one is about pain, or is just "continue" after one that was.
    """
    if not user_texts:
        return False
    latest = user_texts[0]
    if is_pain_message(latest):
        return True
    if CONTINUE_ONLY.match(latest.strip()) and len(user_texts) > 1:
        return is_pain_message(user_texts[1])
    return False
