"""ORM model registration entry point.

Importing this module ensures all ORM models are registered with
``Base.metadata`` so Alembic autogenerate detects every table.

The actual ORM classes have moved to entity-specific subpackages:
- ``tianshu.persistence.thread_meta``
- ``tianshu.persistence.run``
- ``tianshu.persistence.feedback``
- ``tianshu.persistence.user``

``RunEventRow`` remains in ``tianshu.persistence.models.run_event`` because
its storage implementation lives in ``tianshu.runtime.events.store.db`` and
there is no matching entity directory.
"""

from tianshu.persistence.agents.model import AgentRow
from tianshu.persistence.channel_connections.model import (
    ChannelConnectionRow,
    ChannelConversationRow,
    ChannelCredentialRow,
    ChannelOAuthStateRow,
)
from tianshu.persistence.feedback.model import FeedbackRow
from tianshu.persistence.models.run_event import RunEventRow
from tianshu.persistence.run.model import RunRow
from tianshu.persistence.scheduled_task_runs.model import ScheduledTaskRunRow
from tianshu.persistence.scheduled_tasks.model import ScheduledTaskRow
from tianshu.persistence.thread_meta.model import ThreadMetaRow
from tianshu.persistence.user.model import UserRow
from tianshu.persistence.user_mcp.model import UserMCPServerRow
from tianshu.persistence.webhook_delivery.model import WebhookDeliveryRow
from tianshu.persistence.workflows.model import (
    WorkflowExecutionRow,
    WorkflowExecutionStepRow,
    WorkflowEdgeRow,
    WorkflowNodeRow,
    WorkflowRow,
)

__all__ = [
    "AgentRow",
    "ChannelConnectionRow",
    "ChannelConversationRow",
    "ChannelCredentialRow",
    "ChannelOAuthStateRow",
    "FeedbackRow",
    "RunEventRow",
    "RunRow",
    "ScheduledTaskRow",
    "ScheduledTaskRunRow",
    "ThreadMetaRow",
    "UserRow",
    "UserMCPServerRow",
    "WebhookDeliveryRow",
    "WorkflowRow",
    "WorkflowNodeRow",
    "WorkflowEdgeRow",
    "WorkflowExecutionRow",
    "WorkflowExecutionStepRow",
]
