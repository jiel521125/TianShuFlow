"use client";

import { useEffect } from "react";

import {
  WorkspaceBody,
  WorkspaceContainer,
  WorkspaceHeader,
} from "@/components/workspace/workspace-container";
import { WorkspaceManager } from "@/components/workspace/workspace-manager";
import { useI18n } from "@/core/i18n/hooks";

export default function WorkspacePage() {
  const { t } = useI18n();

  useEffect(() => {
    document.title = `${t.userWorkspace.title} - ${t.pages.appName}`;
  }, [t.pages.appName, t.userWorkspace.title]);

  return (
    <WorkspaceContainer>
      <WorkspaceHeader />
      <WorkspaceBody>
        <div className="mx-auto flex w-full max-w-(--container-width-lg) flex-col p-6">
          <WorkspaceManager />
        </div>
      </WorkspaceBody>
    </WorkspaceContainer>
  );
}
