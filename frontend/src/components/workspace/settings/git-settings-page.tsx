"use client";

import {
  ChevronDownIcon,
  GithubIcon,
  GitlabIcon,
  HelpCircleIcon,
  Loader2Icon,
  SaveIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { useI18n } from "@/core/i18n/hooks";
import { useGitConfig, useSaveGitConfig } from "@/core/git/hooks";
import { cn } from "@/lib/utils";

import { SettingsSection } from "./settings-section";

export function GitSettingsPage() {
  const { t } = useI18n();
  const { data: config, isLoading, error } = useGitConfig();
  const saveConfig = useSaveGitConfig();

  const [githubToken, setGithubToken] = useState("");
  const [giteeToken, setGiteeToken] = useState("");
  // Track which fields the user actually edited so we only send those.
  const [githubDirty, setGithubDirty] = useState(false);
  const [giteeDirty, setGiteeDirty] = useState(false);

  // Seed the inputs only on first load so a background refetch never
  // clobbers what the user is typing.
  useEffect(() => {
    if (config && !githubDirty && !giteeDirty) {
      setGithubToken("");
      setGiteeToken("");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config?.github.configured, config?.gitee.configured]);

  const save = () => {
    const body: { github_token?: string | null; gitee_token?: string | null } =
      {};
    if (githubDirty) body.github_token = githubToken.trim() || null;
    if (giteeDirty) body.gitee_token = giteeToken.trim() || null;
    if (Object.keys(body).length === 0) {
      toast.info(t.settings.git.noChanges);
      return;
    }
    saveConfig.mutate(body, {
      onSuccess: () => {
        setGithubDirty(false);
        setGiteeDirty(false);
        setGithubToken("");
        setGiteeToken("");
        toast.success(t.settings.git.saveSuccess);
      },
      onError: (err) =>
        toast.error(err instanceof Error ? err.message : String(err)),
    });
  };

  return (
    <SettingsSection
      title={t.settings.git.title}
      description={t.settings.git.description}
    >
      {isLoading ? (
        <div className="text-muted-foreground flex items-center gap-2 text-sm">
          <Loader2Icon className="size-4 animate-spin" />
          {t.common.loading}
        </div>
      ) : error ? (
        <div className="text-destructive text-sm">
          {error instanceof Error ? error.message : String(error)}
        </div>
      ) : (
        <div className="space-y-4">
          <GitTokenCard
            icon={<GithubIcon className="size-5" />}
            title={t.settings.git.github.title}
            description={t.settings.git.github.description}
            configured={config?.github.configured ?? false}
            placeholder={t.settings.git.github.placeholder}
            token={githubToken}
            help={t.settings.git.github.help}
            onTokenChange={(value) => {
              setGithubToken(value);
              setGithubDirty(true);
            }}
          />
          <GitTokenCard
            icon={<GitlabIcon className="size-5" />}
            title={t.settings.git.gitee.title}
            description={t.settings.git.gitee.description}
            configured={config?.gitee.configured ?? false}
            placeholder={t.settings.git.gitee.placeholder}
            token={giteeToken}
            help={t.settings.git.gitee.help}
            onTokenChange={(value) => {
              setGiteeToken(value);
              setGiteeDirty(true);
            }}
          />
          <div className="flex items-center gap-3">
            <Button onClick={save} disabled={saveConfig.isPending}>
              {saveConfig.isPending ? (
                <Loader2Icon className="size-4 animate-spin" />
              ) : (
                <SaveIcon className="size-4" />
              )}
              {t.settings.git.save}
            </Button>
            <p className="text-muted-foreground text-xs">
              {t.settings.git.securityNote}
            </p>
          </div>
        </div>
      )}
    </SettingsSection>
  );
}

function GitTokenCard({
  icon,
  title,
  description,
  configured,
  placeholder,
  token,
  help,
  onTokenChange,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  configured: boolean;
  placeholder: string;
  token: string;
  help: string[];
  onTokenChange: (value: string) => void;
}) {
  const { t } = useI18n();
  const [helpOpen, setHelpOpen] = useState(false);
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          <div className="bg-primary/10 text-primary rounded-lg p-2">{icon}</div>
          <div>
            <CardTitle>{title}</CardTitle>
            <CardDescription>{description}</CardDescription>
          </div>
          <div className="ml-auto">
            <Badge variant={configured ? "secondary" : "outline"}>
              {configured ? t.settings.git.configured : t.settings.git.notConfigured}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        <label className="text-sm font-medium" htmlFor={`git-token-${title}`}>
          {t.settings.git.tokenLabel}
        </label>
        <Input
          id={`git-token-${title}`}
          type="password"
          autoComplete="off"
          placeholder={placeholder}
          value={token}
          onChange={(event) => onTokenChange(event.currentTarget.value)}
        />
        <Collapsible open={helpOpen} onOpenChange={setHelpOpen}>
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="text-muted-foreground hover:text-foreground inline-flex cursor-pointer items-center gap-1 rounded text-xs"
              aria-expanded={helpOpen}
            >
              <HelpCircleIcon className="size-3.5" />
              {t.settings.git.helpLabel}
              <ChevronDownIcon
                className={cn(
                  "size-3.5 transition-transform duration-200",
                  helpOpen && "rotate-180",
                )}
              />
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="bg-muted/50 border-border mt-2 rounded-lg border p-3">
              <ol className="text-muted-foreground list-decimal space-y-1.5 pl-4 text-xs leading-5">
                {help.map((step, index) => (
                  <li key={index}>{step}</li>
                ))}
              </ol>
            </div>
          </CollapsibleContent>
        </Collapsible>
      </CardContent>
    </Card>
  );
}
