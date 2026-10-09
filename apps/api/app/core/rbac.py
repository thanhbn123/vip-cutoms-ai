"""Role-based access control. Server-side source of truth for every critical action."""

from enum import StrEnum


class Role(StrEnum):
    OPERATOR = "OPERATOR"
    REVIEWER = "REVIEWER"
    SENIOR_REVIEWER = "SENIOR_REVIEWER"
    ADMIN = "ADMIN"


class Perm(StrEnum):
    CASE_CREATE = "case.create"
    CASE_READ = "case.read"
    CASE_UPDATE = "case.update"
    DOC_UPLOAD = "document.upload"
    PARSE_RUN = "parse.run"
    FIELD_EDIT = "field.edit"  # non-critical fields only; critical edits become proposals
    PROPOSE_CHANGE = "proposal.create"
    COPILOT_ASK = "copilot.ask"
    DRAFT_PREVIEW = "draft.preview"
    AUDIT_READ = "audit.read"
    MASTERDATA_MANAGE = "masterdata.manage"
    PROPOSAL_DECIDE = "proposal.decide"
    HS_DECIDE = "hs.decide"
    ISSUE_RESOLVE = "issue.resolve"
    ISSUE_WAIVE_WARNING = "issue.waive_warning"
    ISSUE_WAIVE_CRITICAL = "issue.waive_critical"
    HS_OVERRIDE = "hs.override"  # approve a code outside the AI candidate headings
    CASE_MARK_READY = "case.mark_ready"
    DRAFT_EXPORT_RELEASE = "draft.export_release"
    MEMORY_OUTCOME = "memory.outcome"
    KNOWLEDGE_MANAGE = "knowledge.manage"
    KNOWLEDGE_VERIFY = "knowledge.verify"  # G18B: mark a dataset authoritative (ADMIN, SENIOR_REVIEWER)
    USER_MANAGE = "user.manage"


_OPERATOR = {
    Perm.CASE_CREATE, Perm.CASE_READ, Perm.CASE_UPDATE, Perm.DOC_UPLOAD, Perm.PARSE_RUN, Perm.FIELD_EDIT,
    Perm.PROPOSE_CHANGE, Perm.COPILOT_ASK, Perm.DRAFT_PREVIEW, Perm.AUDIT_READ, Perm.MASTERDATA_MANAGE,
}
_REVIEWER = _OPERATOR | {
    Perm.PROPOSAL_DECIDE, Perm.HS_DECIDE, Perm.ISSUE_RESOLVE, Perm.ISSUE_WAIVE_WARNING,
    Perm.CASE_MARK_READY, Perm.DRAFT_EXPORT_RELEASE,
}
_SENIOR = _REVIEWER | {Perm.ISSUE_WAIVE_CRITICAL, Perm.HS_OVERRIDE, Perm.MEMORY_OUTCOME, Perm.KNOWLEDGE_VERIFY}
# Separation of duties (D-011): Admin configures the system but takes no customs decisions.
_ADMIN = {Perm.CASE_READ, Perm.AUDIT_READ, Perm.KNOWLEDGE_MANAGE, Perm.KNOWLEDGE_VERIFY, Perm.USER_MANAGE, Perm.MASTERDATA_MANAGE,
          Perm.DRAFT_PREVIEW}

ROLE_PERMISSIONS: dict[Role, frozenset[Perm]] = {
    Role.OPERATOR: frozenset(_OPERATOR),
    Role.REVIEWER: frozenset(_REVIEWER),
    Role.SENIOR_REVIEWER: frozenset(_SENIOR),
    Role.ADMIN: frozenset(_ADMIN),
}


def has_perm(role: str, perm: Perm) -> bool:
    try:
        return perm in ROLE_PERMISSIONS[Role(role)]
    except ValueError:
        return False
