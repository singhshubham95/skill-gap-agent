"""Alternative-skill groups (requirements semantics, milestone 5 addendum).

JDs rarely name one strict brand for capability categories — "cloud AI
platforms (Azure OpenAI, AWS Bedrock, GCP Vertex AI)" is an any-of requirement.
Without group semantics, each brand mention becomes an independent strict
requirement, producing false "foundational learning" verdicts (e.g. Azure
ranked #1 despite the user's production GCP depth).

Design (agreed after user review — NOT naive group-matching):

- Groups NEVER erase a specific skill gap. Every target skill keeps its own
  gap status; a missing brand like LangChain remains a real gap with full
  urgency when JDs name it specifically.
- Groups only add a verdict modifier: if the target skill belongs to an
  any-of group AND the user holds another member of that group, the
  group-capability requirement is "satisfied by alternative" — the target is
  demoted to a bridge (low urgency), because the JD's intent (a cloud
  platform / a DL framework / a BI tool) is already met.

Per-group mention policies (hand-set, auditable — NOT auto-parsed):
- "any-of": JDs nearly always list these brands as interchangeable
  alternatives ("Azure/AWS/GCP") → alternative satisfaction applies.
- "specific": JDs typically name the brand as a specific requirement
  ("such as LangChain, LlamaIndex, ..." reads as exemplars but each brand is
  a distinct skill employers differentiate on) → alternative satisfaction
  does NOT apply; the skill gap keeps full urgency.

Honest limitation (recorded in specs/7-open-items.md): v1 cannot classify each
JD mention's modality ("such as" vs "must have X") automatically — the
per-group policy is a hand-set approximation. A future LLM pass could
classify modality per mention per JD; that is the proper fix.
"""

from __future__ import annotations

from dataclasses import dataclass

from .graph import SkillGraph


@dataclass(frozen=True)
class AlternativeGroup:
    name: str
    members: frozenset[str]
    mention: str  # "any-of" | "specific"


# Hand-curated equivalence groups for capability categories JDs list as
# interchangeable brands. Policies are debatable one-liners — edit freely.
ALTERNATIVE_GROUPS: list[AlternativeGroup] = [
    AlternativeGroup(
        "cloud_platform",
        frozenset({"AWS", "Azure", "Google Cloud Platform"}),
        "any-of",
    ),
    AlternativeGroup(
        "managed_llm_platform",
        frozenset({"AWS Bedrock", "Azure OpenAI", "Vertex AI"}),
        "any-of",
    ),
    AlternativeGroup(
        "agent_framework",
        frozenset({"LangChain", "LangGraph", "LlamaIndex", "AutoGen", "CrewAI"}),
        "specific",
    ),
    AlternativeGroup(
        "dl_framework",
        frozenset({"PyTorch", "TensorFlow"}),
        "any-of",
    ),
    AlternativeGroup(
        "bi_tool",
        frozenset({"Tableau", "Power BI"}),
        "any-of",
    ),
]

# skill name (lower) -> group
_SKILL_TO_GROUP: dict[str, AlternativeGroup] = {
    m.lower(): g for g in ALTERNATIVE_GROUPS for m in g.members
}


def group_for(skill: str) -> AlternativeGroup | None:
    return _SKILL_TO_GROUP.get(skill.strip().lower())


def alternative_satisfied(sg: SkillGraph, target: str) -> tuple[bool, str]:
    """Is this target's requirement satisfied by an alternative group member?

    Returns (satisfied, group_name). True only when:
    - the target belongs to an "any-of" group, AND
    - the user holds a DIFFERENT member of that group (via match ladder).
    """
    g = group_for(target)
    if g is None or g.mention != "any-of":
        return False, ""
    for member in sorted(g.members):
        if member.lower() == target.strip().lower():
            continue
        if sg.match_current(member) is not None:
            return True, g.name
    return False, ""