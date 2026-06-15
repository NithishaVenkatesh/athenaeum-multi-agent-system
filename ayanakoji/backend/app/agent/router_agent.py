"""Route node — decides where a (clean) turn goes: Foundry IQ, Work IQ, or general.

Tool scope: **none.** The router classifies intent only. It uses the course
grounding index as a *signal* (does the catalog have content for this?), but does
not answer. The deterministic classifier is the offline path and the fallback
whenever the model is unparseable or unreachable — routing must never hard-fail.
"""

from __future__ import annotations

import json
import re
from datetime import date

from app.agent.contracts import (
    PhaseName,
    PhaseStatus,
    PhaseTelemetry,
    Route,
    RouteDecision,
    TraceStep,
)
from app.agent.grounding import CourseGrounding, get_grounding
from app.agent.llm import AllProvidersDown, Capability, ModelRouter
from app.agent.recommend import vertical_from_text
from app.agent.schedule_edit import parse_adjustment, parse_pace
from app.config import Settings, get_settings

# A bare affirmation ("yes", "sure", "go ahead") only means something in context:
# it inherits the action the assistant just proposed (e.g. a pending pace question).
_AFFIRM_RE = re.compile(
    r"^\s*(yes|yep|yeah|yup|sure|ok(ay)?|please\s+do|go\s+ahead|do\s+it|sounds?\s+good|"
    r"that\s+works|let'?s\s+do\s+it|absolutely|definitely|please)\b[\s.!]*$",
    re.IGNORECASE,
)

# Accepting a just-offered course suggestion is looser than a bare affirmation: it
# allows a trailing object ("yes, start that one", "let's begin", "sign me up"), so a
# natural multi-turn accept enrolls the course instead of dead-ending (R2).
_ACCEPT_RE = re.compile(
    r"^\s*(yes|yep|yeah|yup|sure|ok(ay)?|absolutely|definitely|please|sounds?\s+good|"
    r"that\s+works|go\s+ahead|do\s+it|let'?s\s+(do|go|start|begin)|start|begin|enroll|"
    r"sign\s+me\s+up|i'?ll\s+take|i\s+want\s+(to\s+start|that|this))\b",
    re.IGNORECASE,
)


# A negation anywhere flips an apparent acceptance into a refusal: "absolutely not",
# "please don't start", "yeah no", "ok but no" must NOT enroll (red-team: the worst bug
# was silently enrolling a learner who explicitly declined). "start over"/"start again"
# is a restart, not an accept, so it is excluded too.
#
# The generic contraction tail REQUIRES a real apostrophe (``n['’]t``): the apostrophe is
# what separates a contraction (can't, isn't, won't, doesn't) from an ordinary word that
# merely ends in "nt" (want, important, assessment, current, consent, student). Without it
# the tail matched the "…nt" of acceptances and silently declined an enrolling learner.
_NEGATION_RE = re.compile(
    r"\b(not|never|nope|nah|cancel|decline|refuse|don'?t|do\s+not|won'?t|"
    r"no\s+thanks?|no\b|nvm|nevermind|never\s*mind|stop)\b|n['’]t\b",
    re.IGNORECASE,
)
_RESTART_RE = re.compile(r"\bstart\s+(over|again|from\s+scratch|fresh)\b", re.IGNORECASE)


def is_acceptance(text: str) -> bool:
    """True iff the message accepts a just-offered course suggestion — affirmation with
    no negation and not a 'start over' restart (so a refusal never enrolls)."""
    if _NEGATION_RE.search(text) or _RESTART_RE.search(text):
        return False
    return bool(_ACCEPT_RE.search(text))


# Ordinal / positional references to a specific offered option ("the second one",
# "number 3", "the first") so a multi-option suggestion is resolvable by chat (R2+).
_ORDINAL_RE = re.compile(
    r"\b(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|last|former|latter"
    r"|(?:number|option|the)\s+\d+|\d+(?:st|nd|rd|th)|that\s+(?:one|course))\b",
    re.IGNORECASE,
)
# A comparison / info question ABOUT the options ("what's the difference between the
# first and the second?") names ordinals but is NOT a selection — picking option 1 from
# it would silently enroll a course (a persisted side-effect). Such a turn must fall
# through to the model, which can answer the comparison instead.
_COMPARE_QUESTION_RE = re.compile(
    r"\bdifference\b|\bcompare\b|\bversus\b|\bvs\.?\b|\bbetween\b"
    r"|\bwhat'?s\b|\bwhat\s+(is|are)\b|\bwhich\s+(is|one\s+is|of|should|would)\b"
    r"|\bhow\s+(do|does|is|are|much|long)\b|\bwhy\b|\btell\s+me\b|\bexplain\b|\bmore\s+about\b",
    re.IGNORECASE,
)


def is_refusal(text: str) -> bool:
    """True if the message declines (so a suggestion is rejected, never enrolled)."""
    return bool(_NEGATION_RE.search(text))


def is_options_question(text: str) -> bool:
    """True if the message is a comparison / info question ABOUT the offered options
    ("what's the difference between the first and the second?") rather than a selection of
    one. Such a turn must NOT trigger an enroll side-effect — it falls through to the model
    so the comparison gets answered."""
    return bool(_COMPARE_QUESTION_RE.search(text))


def is_suggestion_response(text: str) -> bool:
    """True if the message responds to an offered suggestion — accept or pick one.

    A negated message ("not the second one", "no") is never a selection, and neither is a
    comparison/info question that merely names ordinals ("what's the difference between the
    first and the second?") — enrolling on that would be a silent, persisted side-effect, so
    it falls through to the model to answer instead.
    """
    if is_acceptance(text):
        return True
    if is_refusal(text) or is_options_question(text):
        return False
    return bool(_ORDINAL_RE.search(text))


# "Help me choose / explore courses" signals → Recommend (profile- or topic-scoped).
_RECOMMEND_RE = re.compile(
    r"\b(suggest|recommend|which)\b.{0,40}\bcourse"
    r"|\bcourse\b.{0,20}\b(for me|suggestion|recommendation)"
    r"|\b(explore|show|find|browse|see|list|view)\b.{0,25}\bcourses?"
    r"|\bcourses?\s+(in|on|about|for|related)\b"
    r"|what\s+(should|do|can)\s+i\s+(learn|take|study|do|start)"
    r"|what\s+(courses|verticals|tracks|topics|paths?)\b"
    r"|what(?:'s| is)\s+next|where\s+(do|should)\s+i\s+start"
    r"|help\s+me\s+(choose|pick|decide|get\s+started|start)"
    r"|(based\s+on|fits?)\s+my\s+(role|profile|schedule|work)"
    r"|i('?d| would)\s+like\s+to\s+(explore|learn|study|take)"
    r"|recommend\s+(me\s+)?(a|some|something)",
    re.IGNORECASE,
)
# "Build / adjust my study plan / schedule" → Study Plan. Schedule edits (start
# later, skip a day, skip a week) and pace changes are detected separately by
# ``parse_adjustment`` / ``parse_pace`` so this only matches explicit plan asks
# (it must NOT fire on "where do I begin in Azure").
_PLAN_RE = re.compile(
    r"\b(study\s+plan|study\s+schedule|learning\s+plan|prep\s+plan|prepare\s+plan)"
    r"|\b(build|make|create|give|generate|draft|rebuild|redo|adjust|reschedule)\b.{0,20}\b(plan|schedule)"
    r"|\b(plan|schedule)\b.{0,20}\b(my|the)\s+(study|learning|prep|week)"
    r"|how\s+should\s+i\s+(study|prepare|schedule)|when\s+do\s+i\s+study",
    re.IGNORECASE,
)
# Warm onboarding / small talk → Greeting.
_GREETING_INTENT_RE = re.compile(
    r"^\s*(hi|hey|hello|yo|sup|hiya|good\s+(morning|afternoon|evening)|"
    r"thanks?|thank\s+you|who\s+are\s+you|what\s+can\s+you\s+do|"
    r"what\s+do\s+you\s+do|help\b|get\s+started)\b",
    re.IGNORECASE,
)
# Strong "about my own work" signals → Work IQ even when a course is named.
_WORK_STRONG_RE = re.compile(
    r"\bmy\s+(schedule|calendar|week|day|meetings?|workload|capacity|hours|availability)"
    r"|\b(on[\s-]?call|too\s+busy|overloaded|swamped|collaboration\s+load)\b"
    r"|\bfree\s+(time|slot|window|hours?)\b|\bfocus\s+time\b|\bmeeting\s+load\b"
    r"|\bnext\s+free\b|\bspare\s+time\b|\bwhen\s+(?:am\s+i|i'?m)\s+(?:next\s+)?free\b",
    re.IGNORECASE,
)
# "When is my next free slot/window" → a concrete next-free-slot answer from the calendar.
_FREE_SLOT_RE = re.compile(
    r"\bnext\s+free\b|\bfree\s+(slot|window)\b|\bwhen\s+(?:am\s+i|i'?m)\s+(?:next\s+)?free\b"
    r"|\bwhen\s+(?:is|'?s)\s+my\s+next\s+free\b",
    re.IGNORECASE,
)


def wants_next_free_slot(text: str) -> bool:
    """True if the learner is asking when their next free slot/window is."""
    return bool(_FREE_SLOT_RE.search(text))


# A turn that asks about ANOTHER person (by employee id, role, or third-party
# reference). The personal-data answers (work_iq, progress) decline outright on a
# match. Conservative: high-signal markers only, so a learner's own "my schedule /
# my progress / my other courses" never trips it.
# Deterministic floor ONLY (offline path + fallback when the model is unreachable). The
# online path relies on the LLM router's ``third_party`` signal — far better at catching a
# proper name ("Sarah's schedule") or role ("my manager's progress") than a regex NER. This
# stays a conservative high-signal net so a learner's own "my schedule / my progress" never
# trips it.
_OTHER_PERSON_RE = re.compile(
    r"\bEMP-\d"
    r"|\bcolleagues?\b|\bteammates?\b|\bco-?workers?\b"
    r"|\b(everyone|everybody)\b"
    r"|\bsomeone\s+else\b|\banother\s+(employee|person|learner|colleague|user)\b"
    r"|\bother\s+(employees?|people|persons?|learners?|users?|teammates?|staff)\b"
    r"|\bthis\s+person'?s?\b|\bthat\s+person'?s?\b"
    r"|\b(manager|boss|supervisor|director|mentor)('s|s')\s+"
    r"(schedule|calendar|workload|hours|meetings?|progress|courses?|data|load|signals?)\b"
    r"|\b(his|her|their)\s+"
    r"(schedule|calendar|workload|hours|meetings?|progress|courses|data|load|manager|signals?)\b",
    re.IGNORECASE,
)


def mentions_other_person(text: str) -> bool:
    """True if the message asks about a person other than the current learner.

    Deterministic floor (offline + fallback); the online guard also trusts the LLM router's
    ``third_party`` signal, which catches proper names the regex cannot."""
    return bool(_OTHER_PERSON_RE.search(text))


# Weaker timing signals → Work IQ only if the turn isn't really about course content.
_WORK_TIMING_RE = re.compile(
    r"when\s+should\s+i\s+study|how\s+much\s+time|fit\s+(this|it|study)\s+(in|around)"
    r"|this\s+week\b",
    re.IGNORECASE,
)
# "Practise / quiz me on this module" → the assessor practice round.
_PRACTISE_RE = re.compile(
    r"\b(practi[sc]e|quiz|drill|warm\s*up|test\s+me|test\s+myself|check\s+my\s+understanding)\b"
    r"|\bgive\s+me\s+(some\s+)?(practice|quiz)\b"
    r"|\b(practice|quiz)\s+(questions?|me)\b",
    re.IGNORECASE,
)
# "I'm ready to take the test / evaluation" → CTA to the module evaluation.
_TAKE_EVAL_RE = re.compile(
    r"\b(ready|prepared)\s+(for|to\s+take)\s+(the\s+)?(test|exam|evaluation|assessment|quiz)\b"
    r"|\b(take|start|do|begin|attempt)\s+(the\s+)?(test|exam|evaluation|assessment)\b"
    # Scoped to the ready-sentence so it can't span into a later informational question
    # ("I'm ready for a break. What's on the exam?"); branch 1 covers "ready for the test".
    r"|\bi'?m\s+ready\s+(?:to\s+take\s+)?(?:the\s+)?(test|exam|evaluation|assessment)\b"
    r"|\bevaluate\s+me\b",
    re.IGNORECASE,
)
# "Open / go to / study the module" → CTA to the module page.
_GO_MODULE_RE = re.compile(
    r"\b(go\s+to|open|take\s+me\s+to|show\s+me|back\s+to|study)\s+(the\s+)?(module|lesson|content|material)\b"
    r"|\bstudy\s+(the\s+)?module\b|\bopen\s+(the\s+)?module\b",
    re.IGNORECASE,
)
# "Give me feedback on my failed test / why did I fail / what did I get wrong" →
# the in-chat feedback route (grounded review of a test in THIS course). Kept
# disjoint from _TAKE_EVAL_RE ("take the test") and _PRACTISE_RE ("quiz me") so a
# request to review past results never reads as a request to start a new attempt.
_FEEDBACK_RE = re.compile(
    r"\bfeedback\b"
    r"|why\s+did\s+i\s+(fail|not\s+pass|do\s+(so\s+)?(badly|poorly))"
    r"|why\s+(was|were|is|are)\s+[^?.!]{0,40}\bwrong\b"
    r"|what\s+did\s+i\s+(get\s+wrong|miss)"
    r"|where\s+did\s+i\s+go\s+wrong"
    r"|(go|walk)\s+(me\s+)?(over|through)\s+(my|the)\s+(results?|answers?|mistakes?|quiz|exam|test)"
    r"|review\s+(my|the)\s+(results?|answers?|mistakes?)"
    r"|how\s+did\s+i\s+do\s+(on|in)\s+(my|the)\s+(test|quiz|exam|assessment|oral)",
    re.IGNORECASE,
)


def is_feedback_intent(text: str) -> bool:
    """True if the learner is asking for feedback / a review of a test they took."""
    return bool(_FEEDBACK_RE.search(text))


# Clearly-not-our-domain topics → general with a stronger nudge.
_OFF_DOMAIN_RE = re.compile(
    r"\b(weather|football|cricket|soccer|world\s+cup|movie|film|recipe|cook|sport|"
    r"politics|election|celebrity|stock|crypto|joke|game\s+of\s+thrones|horoscope)\b",
    re.IGNORECASE,
)
_GREETING_RE = re.compile(
    r"^\s*(hi|hey|hello|yo|sup|good\s+(morning|afternoon|evening)|thanks?|thank\s+you|"
    r"how\s+are\s+you|what\s+can\s+you\s+do|who\s+are\s+you)\b",
    re.IGNORECASE,
)
# "What's my next module / session / upcoming" → Upcoming route.
_UPCOMING_RE = re.compile(
    r"\b(what(?:'?s?|\s+is)\s+(?:my\s+)?(?:next|upcoming)|what\s+(?:am\s+i|should\s+i)\s+(?:studying|doing)\s+next"
    r"|next\s+(?:module|session|thing|topic)\s+(?:i\s+(?:should|need\s+to)\s+)?(?:study|do|cover|learn|work\s+on)?"
    r"|(what|which)\s+module\s+(?:is\s+)?(?:next|coming\s+up|am\s+i\s+on)"
    r"|where\s+(?:am\s+i|should\s+i\s+(?:be|start))\s+(?:in\s+my\s+plan|in\s+my\s+schedule)?"
    r"|upcoming\s+(?:module|session|study|class|deadline)s?)\b",
    re.IGNORECASE,
)
# "How much have I completed / how many courses left / my progress" → Progress route.
# Requires a completion/progress word so catalog-breadth asks ("how many courses are
# there") and timing asks ("how much time") never match. This is the learner asking
# about their OWN completion status — answered directly, never via the work_iq gate.
_COMPLETION = r"(complete|completed|completing|done|finish|finished|passed|left|remaining|pending)"
_PROGRESS_RE = re.compile(
    r"\bmy\s+progress\b"
    r"|\bprogress\s+(so\s+far|report|summary|update|check|overview)\b"
    r"|how\s+(am\s+i\s+doing|far\s+along|far\s+am\s+i)\b"
    rf"|how\s+(many|much)\b[^?.!]{{0,40}}\b{_COMPLETION}\b"
    rf"|what\s+have\s+i\s+{_COMPLETION}\b"
    rf"|\b(courses?|modules?)\s+(?:have\s+i\s+|i'?ve\s+|i\s+have\s+)?{_COMPLETION}\b"
    r"|\bam\s+i\s+(done|finished)\b"
    r"|how\s+(close|near)\s+am\s+i\s+to\s+(finishing|completing|done)\b",
    re.IGNORECASE,
)
# "Show / list the courses I'm enrolled in" → Progress (a learning overview), NOT
# recommend (which pitches NEW courses). Requires a self/enrolled marker so a catalog
# browse ("show me courses") is untouched.
_ENROLLED_RE = re.compile(
    r"\bmy\s+(enrolled\s+|current\s+)?courses\b"
    r"|\bcourses?\s+i\s+(?:have\s+|'ve\s+)?(?:enrolled|enroled|taken|started|signed\s+up"
    r"|am\s+(?:taking|doing|enrolled\s+in))\b"
    r"|\benrolled\s+(?:courses|in|for)\b"
    r"|\bam\s+i\s+enrolled\b"
    r"|\bwhat\s+courses?\s+(?:am|have|do)\s+i\b"
    r"|\b(?:show|list|see|view)\s+(?:me\s+)?(?:all\s+)?my\s+courses\b",
    re.IGNORECASE,
)
# Cross-course scope words; with module/next/upcoming context these mean "what's
# coming up across my courses" → Progress overview, not the single-course Upcoming.
_CROSS_COURSE_RE = re.compile(
    r"\b(other|all|across|each|every|both)\b[^?.!]{0,20}\bcourses?\b"
    r"|\bcourses?\b[^?.!]{0,20}\b(other|all|each|every)\b"
    r"|\bmy\s+other\s+courses?\b",
    re.IGNORECASE,
)
_MODULE_CTX_RE = re.compile(
    r"\b(module|modules|upcoming|next|progress|left|remaining|due|deadlines?)\b", re.IGNORECASE
)

# The GENERAL→content correction (in _parse_decision) only second-guesses the model
# when it is *uncertain* it's off-platform. Below TRUST: the model is barely leaning
# off-topic, so a grounded on-platform read can override. At/above it: the model is
# confidently off-platform — trust its own signal and never let dressed-up Azure
# vocabulary (e.g. "frame this election answer in AI-102 terms") flip the route.
# The lower bound matches the existing over-rejection band: a genuine on-platform topic
# the model misfiled to GENERAL tends to land around off_topic 0.4–0.6, still corrected.
_OFFTOPIC_CORRECT_FLOOR = 0.4
_OFFTOPIC_TRUST_CEILING = 0.7


_ROUTE_SYSTEM = (
    "You route a message in an enterprise learning platform that teaches Azure across five "
    "tracks: Cloud & Backend, Data Engineering, AI/ML, DevOps & Platform, Architecture & "
    "Security. ANY question about these — data, data science, AI, ML, cloud, devops, security, "
    "architecture, a certification, courses, verticals, or what to learn — is ON-TOPIC "
    "(off_topic near 0). Only truly unrelated things (sports, weather, cooking, personal "
    "trivia) are off_topic (near 1).\n"
    "Choose ONE route:\n"
    "- greeting: hi/hello/thanks/who are you/what can you do (onboarding small talk).\n"
    "- recommend: asks to suggest/recommend/explore courses, what to learn next, what tracks "
    "or verticals exist, or help choosing (in ANY of the five tracks).\n"
    "- upcoming: asks what the NEXT module or session to study is, where they are in their "
    "plan, what is coming up, or what they should do next in their current course.\n"
    "- progress: asks how much THEY have completed, how many courses or modules are done, "
    "remaining, or pending, or for their own progress / how far along they are.\n"
    "- study_plan: asks to build/make a study plan or schedule, or how/when to study.\n"
    "- foundry_iq: asks about the CONTENT of a specific course/cert/Azure topic.\n"
    "- work_iq: asks about THEIR OWN schedule, workload, meetings, capacity, or study timing.\n"
    "- practise_module: asks to practise / quiz / drill / test themselves on the CURRENT module.\n"
    "- take_evaluation: says they are ready to take, or want to start, the module "
    "test / evaluation.\n"
    "- go_to_module: asks to open / go to / study the current module.\n"
    "- general: only genuinely off-platform topics.\n"
    "Set third_party=true when the message asks about a person OTHER than the learner "
    "themselves — a named person ('what's Sarah's schedule'), a colleague, their manager, a "
    "teammate, 'someone else', or building/quizzing 'for my colleague'. It is false when the "
    "turn is about the learner's own data or is general course content.\n"
    "intents: if the turn asks for SEVERAL things, list the route of EVERY intent in the order "
    "asked, e.g. 'explain triggers, then quiz me, and build a plan' → "
    '["foundry_iq","practise_module","study_plan"]. Put the SAME value as route first. For an '
    "ordinary single-request turn use an empty list []. Do NOT split one request into many.\n"
    'Reply ONLY with JSON: {"route":'
    '"greeting|recommend|upcoming|progress|study_plan|foundry_iq|work_iq|practise_module|'
    'take_evaluation|go_to_module|general",'
    '"reasoning":"<short>","off_topic":0..1,"confidence":0..1,"third_party":true|false,'
    '"intents":["<route>",...]}.'
)


def is_plan_intent(text: str) -> bool:
    """True for any study-plan ask: a build request, a schedule edit, or a pace change.

    Schedule edits ("start after June 30", "skip Mondays", "remove week 2") and
    pace changes ("revert to a slower pace") are high-signal re-plan requests; the
    LLM tends to misroute them to work_iq, so we detect them deterministically.
    """
    return bool(
        _PLAN_RE.search(text)
        or parse_adjustment(text, today=date.today()) is not None
        or parse_pace(text) is not None
    )


def _study_plan_decision() -> RouteDecision:
    return RouteDecision(
        route=Route.STUDY_PLAN,
        reasoning="Study-plan request (build, schedule edit, or pace change) for the course.",
        off_topic=0.0,
        confidence=0.85,
    )


def is_progress_intent(text: str) -> bool:
    """True for a question about the learner's OWN learning status: how much is
    completed/remaining, which courses they're enrolled in, or what's coming up
    across their courses.

    High-signal and deterministic so it wins over the LLM, which tends to misfile
    completion asks as work_iq (data-less deflection) and enrollment/cross-course
    asks as recommend/upcoming (wrong answer).
    """
    if _PROGRESS_RE.search(text) or _ENROLLED_RE.search(text):
        return True
    # "upcoming / next modules across my OTHER courses" — cross-course overview.
    return bool(_CROSS_COURSE_RE.search(text) and _MODULE_CTX_RE.search(text))


def _progress_decision() -> RouteDecision:
    return RouteDecision(
        route=Route.PROGRESS,
        reasoning="Asks about their own progress / how much is completed or remaining.",
        off_topic=0.0,
        confidence=0.85,
    )


def _practise_decision() -> RouteDecision:
    return RouteDecision(
        route=Route.PRACTISE_MODULE,
        reasoning="Wants to practise the current module with questions.",
        off_topic=0.0,
        confidence=0.85,
    )


def _take_eval_decision() -> RouteDecision:
    return RouteDecision(
        route=Route.TAKE_EVALUATION,
        reasoning="Wants to take the module evaluation.",
        off_topic=0.0,
        confidence=0.85,
    )


def _go_module_decision() -> RouteDecision:
    return RouteDecision(
        route=Route.GO_TO_MODULE,
        reasoning="Wants to open the current module to study.",
        off_topic=0.0,
        confidence=0.85,
    )


def _feedback_decision(*, followup: bool = False) -> RouteDecision:
    reasoning = (
        "Continuing feedback on the test just discussed (pinned context)."
        if followup
        else "Wants feedback on a test they took in this course."
    )
    return RouteDecision(route=Route.FEEDBACK, reasoning=reasoning, off_topic=0.0, confidence=0.85)


def classify(
    text: str,
    *,
    grounding: CourseGrounding | None = None,
    pending: str | None = None,
    feedback_active: bool = False,
) -> RouteDecision:
    """Deterministic intent classifier (offline path + fallback for the online path).

    Priority: affirmation→pending → feedback → plan/edit/pace → recommend → greeting
    → strong-work → course-content → weak-work-timing → off-topic → [feedback pin] →
    general. Course content outranks weak timing words so a question that merely says
    "how much time" about a real topic still gets a grounded content answer.

    ``feedback_active`` pins a just-given feedback turn: a follow-up the chain would
    otherwise dump to GENERAL stays in FEEDBACK so it keeps grounding on that test,
    until a competing intent above (plan, navigation, off-domain) breaks the pin.
    """
    # A bare "yes" only resolves against what the assistant just proposed.
    if pending == "pace" and _AFFIRM_RE.search(text):
        return RouteDecision(
            route=Route.STUDY_PLAN,
            reasoning="Affirmation after a pace question — proceed to build the plan.",
            off_topic=0.0,
            confidence=0.8,
        )
    # Responding to a course suggestion ("yes, start that one", "the second one")
    # begins setup; the courses layer links the chosen course, then this routes to
    # the first setup step.
    if pending == "suggestion" and is_suggestion_response(text):
        return RouteDecision(
            route=Route.STUDY_PLAN,
            reasoning="Responded to a course suggestion — start the course and begin setup.",
            off_topic=0.0,
            confidence=0.8,
        )
    # An explicit feedback ask ("why did I fail my quiz") wins over the content/plan
    # intents below: those words alone would otherwise read as ungrounded → general.
    if is_feedback_intent(text):
        return _feedback_decision()
    if is_plan_intent(text):
        return _study_plan_decision()
    if is_progress_intent(text):
        return _progress_decision()
    if _UPCOMING_RE.search(text):
        return RouteDecision(
            route=Route.UPCOMING,
            reasoning="Asks about the next module or upcoming session in their plan.",
            off_topic=0.0,
            confidence=0.8,
        )
    if _PRACTISE_RE.search(text):
        return _practise_decision()
    if _TAKE_EVAL_RE.search(text):
        return _take_eval_decision()
    if _GO_MODULE_RE.search(text):
        return _go_module_decision()
    if _RECOMMEND_RE.search(text):
        return RouteDecision(
            route=Route.RECOMMEND,
            reasoning="Asks for a course recommendation — match to their profile.",
            off_topic=0.0,
            confidence=0.75,
        )
    if _GREETING_INTENT_RE.search(text) and len(text.split()) <= 6:
        return RouteDecision(
            route=Route.GREETING,
            reasoning="Greeting / onboarding — welcome and invite a course choice.",
            off_topic=0.0,
            confidence=0.7,
        )
    if _WORK_STRONG_RE.search(text):
        return RouteDecision(
            route=Route.WORK_IQ,
            reasoning="Mentions the learner's own schedule / workload.",
            off_topic=0.0,
            confidence=0.7,
        )
    grounding = grounding or get_grounding()
    if grounding.search(text, k=1):
        return RouteDecision(
            route=Route.FOUNDRY_IQ,
            reasoning="Names a course or topic in the catalog — answer + offer to start it.",
            off_topic=0.0,
            confidence=0.7,
        )
    if _WORK_TIMING_RE.search(text):
        return RouteDecision(
            route=Route.WORK_IQ,
            reasoning="Asks about study timing / capacity in their week.",
            off_topic=0.0,
            confidence=0.65,
        )
    if _OFF_DOMAIN_RE.search(text):
        return RouteDecision(
            route=Route.GENERAL,
            reasoning="Off-platform topic — answer briefly, then steer back to learning.",
            off_topic=0.85,
            confidence=0.6,
        )
    # Feedback pin (last resort): a follow-up that nothing above claimed, while a
    # feedback turn is active, stays in FEEDBACK so "answer my questions from there
    # on" keeps grounding on the same test instead of being refused as off-topic.
    if feedback_active:
        return _feedback_decision(followup=True)
    off = 0.1 if _GREETING_RE.search(text) else 0.5
    return RouteDecision(
        route=Route.GENERAL,
        reasoning="No course or work-context match — general assistance.",
        off_topic=off,
        confidence=0.5,
    )


def _telemetry(decision: RouteDecision, *, model: str | None, tier: int | None) -> PhaseTelemetry:
    is_heuristic = model is None or "heuristic" in (model or "")
    label = "Heuristic classifier" if is_heuristic else "LLM router"
    step = TraceStep(
        label=label,
        passed=True,
        detail=(
            f"Route: {decision.route.value} · confidence {decision.confidence:.0%}"
            f" · off-topic score {decision.off_topic:.0%}"
        ),
        model=model,
    )
    return PhaseTelemetry(
        phase=PhaseName.ROUTE,
        status=PhaseStatus.PASSED,
        summary=f"Routed to {decision.route.value}",
        reasoning=decision.reasoning,
        route=decision.route,
        model=model,
        tier=tier,
        steps=[step],
        confidence=decision.confidence,
        off_topic=decision.off_topic,
    )


def _history_messages(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    """The last few turns as chat messages so the router can resolve follow-ups."""
    if not history:
        return []
    recent = history[-4:]
    return [
        {"role": "assistant" if m.get("role") == "assistant" else "user", "content": m["content"]}
        for m in recent
        if m.get("content")
    ]


def route(
    text: str,
    *,
    router: ModelRouter | None = None,
    grounding: CourseGrounding | None = None,
    history: list[dict[str, str]] | None = None,
    pending: str | None = None,
    feedback_active: bool = False,
    settings: Settings | None = None,
) -> tuple[RouteDecision, PhaseTelemetry]:
    """Decide the route for a clean turn, with telemetry for the trace.

    ``history`` (recent turns) and ``pending`` (an action the last assistant turn
    proposed, e.g. "pace") let the router resolve context-dependent follow-ups
    like a bare "yes" instead of treating each message in isolation. ``feedback_active``
    pins a just-given feedback turn so follow-ups keep grounding on the same test.
    """
    settings = settings or get_settings()
    if settings.llm_offline:
        decision = classify(
            text, grounding=grounding, pending=pending, feedback_active=feedback_active
        )
        return decision, _telemetry(decision, model="heuristic", tier=None)

    router = router or ModelRouter(settings)
    try:
        messages = [
            {"role": "system", "content": _ROUTE_SYSTEM},
            *_history_messages(history),
            {"role": "user", "content": text},
        ]
        result = router.complete(Capability.FAST, messages, json_mode=True, max_tokens=120)
        decision = _parse_decision(
            result.text, text, grounding, pending=pending, feedback_active=feedback_active
        )
        return decision, _telemetry(decision, model=result.model, tier=result.tier)
    except AllProvidersDown:
        decision = classify(
            text, grounding=grounding, pending=pending, feedback_active=feedback_active
        )
        return decision, _telemetry(decision, model="heuristic (providers down)", tier=None)


def _json_third_party(raw: str) -> bool:
    """Best-effort extract the model's third_party flag from the router JSON."""
    try:
        return bool(json.loads(raw).get("third_party", False))
    except (json.JSONDecodeError, AttributeError, TypeError):
        return False


# A compound turn serves at most this many intents (primary + extras) — a runaway-loop and
# cost bound; a real multi-intent message rarely names more.
_MAX_INTENTS = 4


def _json_intents(raw: str) -> list[Route]:
    """The ordered, deduped, valid-route intents the model detected in a compound turn."""
    try:
        items = json.loads(raw).get("intents")
    except (json.JSONDecodeError, AttributeError, TypeError):
        return []
    if not isinstance(items, list):
        return []
    out: list[Route] = []
    for item in items:
        try:
            route = Route(str(item))
        except ValueError:
            continue
        if route not in out:
            out.append(route)
    return out[:_MAX_INTENTS]


def _parse_decision(
    raw: str,
    text: str,
    grounding: CourseGrounding | None,
    *,
    pending: str | None = None,
    feedback_active: bool = False,
) -> RouteDecision:
    """Parse the model's route, then carry the third-party signal onto the final decision.

    The route can be deterministically overridden (a schedule edit, a feedback ask), but the
    cross-user question — 'is this about someone other than the learner?' — is the model's to
    judge ('build a study plan for Sarah'), so we read its ``third_party`` flag from the raw
    JSON regardless of which route wins, OR'd with the deterministic marker floor.
    """
    decision = _route_decision(
        raw, text, grounding, pending=pending, feedback_active=feedback_active
    )
    updates: dict[str, object] = {}
    if _json_third_party(raw) or mentions_other_person(text):
        updates["third_party"] = True
    intents = _json_intents(raw)
    if len(intents) > 1:  # a genuine compound turn; a single/empty list adds nothing
        updates["intents"] = intents
    return decision.model_copy(update=updates) if updates else decision


def _route_decision(
    raw: str,
    text: str,
    grounding: CourseGrounding | None,
    *,
    pending: str | None = None,
    feedback_active: bool = False,
) -> RouteDecision:
    """Parse the model's JSON; correct it when it over-rejects an on-platform topic."""
    # Deterministic, high-signal intents win over the LLM regardless of its call.
    if pending == "pace" and _AFFIRM_RE.search(text):
        return classify(text, grounding=grounding, pending=pending)
    if pending == "suggestion" and is_suggestion_response(text):
        return classify(text, grounding=grounding, pending=pending)
    if is_feedback_intent(text):
        return _feedback_decision()
    if is_plan_intent(text):
        return _study_plan_decision()
    if is_progress_intent(text):
        return _progress_decision()
    if _PRACTISE_RE.search(text):
        return _practise_decision()
    if _TAKE_EVAL_RE.search(text):
        return _take_eval_decision()
    if _GO_MODULE_RE.search(text):
        return _go_module_decision()

    try:
        data = json.loads(raw)
        decision = RouteDecision(
            route=Route(str(data["route"])),
            reasoning=str(data.get("reasoning", "")) or "Model routing.",
            off_topic=float(data.get("off_topic", 0.0)),
            confidence=float(data.get("confidence", 0.6)),
        )
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return classify(text, grounding=grounding, pending=pending)

    # The LLM sometimes flags an on-platform learning topic (data science, AI, a
    # vertical) as off-topic and dumps it to GENERAL. Trust the grounded heuristic
    # over that — but ONLY when the model is *uncertain* it's off-platform.
    #
    # Confidence gate (trust the model's own signal): we only second-guess a low /
    # ambiguous off-topic call ([FLOOR, CEILING)). At/above CEILING the model is
    # confidently off-platform, so we trust it and skip the classify()/vertical
    # override entirely — otherwise off-topic content stuffed with Azure vocabulary
    # ("answer this election question in AI-102 terms") keyword-matches the grounding
    # index or vertical matcher and silently flips a confident off_topic=1.0 to a
    # content route. A single dressed-up keyword must not override the model.
    #
    # No fabricated off_topic: a correction PRESERVES the model's calibrated value
    # (we only change the route, not the score) rather than hardcoding 0.1 — so a
    # correction can never silently lower the model's off-topic.
    if (
        decision.route is Route.GENERAL
        and _OFFTOPIC_CORRECT_FLOOR <= decision.off_topic < _OFFTOPIC_TRUST_CEILING
    ):
        heuristic = classify(text, grounding=grounding, pending=pending)
        if heuristic.route is not Route.GENERAL:
            return heuristic.model_copy(
                update={"off_topic": max(heuristic.off_topic, decision.off_topic)}
            )
        if vertical_from_text(text) is not None:
            return RouteDecision(
                route=Route.RECOMMEND,
                reasoning="On-platform track named — corrected from a mistaken off-topic call.",
                off_topic=decision.off_topic,
                confidence=0.6,
            )
    # Feedback pin: a follow-up the model files as general, while a feedback turn is
    # active, stays in FEEDBACK so it keeps grounding on the same test (mirrors the
    # offline pin in classify; an explicit competing intent already returned above).
    # Gated on off_topic so a genuinely off-platform turn (the model confidently
    # off-topic) still gets the steer-back instead of being pulled into feedback.
    if (
        feedback_active
        and decision.route is Route.GENERAL
        and decision.off_topic < _OFFTOPIC_TRUST_CEILING
    ):
        return _feedback_decision(followup=True)
    return decision
