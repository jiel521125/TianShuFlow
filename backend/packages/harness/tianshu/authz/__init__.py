"""Pluggable fine-grained authorization (resource-level RBAC and beyond)."""

from tianshu.authz.adapter import GuardrailAuthorizationAdapter
from tianshu.authz.enforcement import filter_tools_by_authorization
from tianshu.authz.principal import build_principal_from_context, normalize_authz_attributes
from tianshu.authz.provider import AuthorizationProvider, AuthzDecision, AuthzReason, AuthzRequest, Principal
from tianshu.authz.rbac import RbacAuthorizationProvider
from tianshu.authz.runtime import resolve_authorization_provider
from tianshu.authz.tool_filter import apply_tool_authorization

__all__ = [
    "AuthzDecision",
    "AuthzReason",
    "AuthzRequest",
    "AuthorizationProvider",
    "GuardrailAuthorizationAdapter",
    "Principal",
    "RbacAuthorizationProvider",
    "apply_tool_authorization",
    "build_principal_from_context",
    "filter_tools_by_authorization",
    "normalize_authz_attributes",
    "resolve_authorization_provider",
]
