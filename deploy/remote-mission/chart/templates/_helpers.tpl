{{- define "myskills.name" -}}{{ .Release.Name | trunc 40 | trimSuffix "-" }}{{- end }}

{{- define "myskills.labels" -}}
app.kubernetes.io/part-of: myskills-remote
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{- define "myskills.image" -}}{{ .Values.image.repository }}:{{ .Values.image.tag }}{{- end }}
{{- define "myskills.serviceImage" -}}{{ .Values.serviceImage.repository }}:{{ .Values.serviceImage.tag }}{{- end }}

{{/* Fournisseur des modèles : litellm (LiteLLM d'un autre cluster) ou foundry (Azure AI Foundry, sans LiteLLM). */}}
{{- define "myskills.foundry" -}}{{ if eq (.Values.llm.provider | default "litellm") "foundry" }}true{{ end }}{{- end }}
{{- define "myskills.foundryHost" -}}{{ required "foundry.resource : nom de la ressource Azure AI Foundry" .Values.foundry.resource }}.services.ai.azure.com{{- end }}
{{/* Hôte des modèles (allowed_hosts). */}}
{{- define "myskills.llmHost" -}}
{{- if include "myskills.foundry" . }}{{ include "myskills.foundryHost" . }}{{ else }}{{ include "myskills.host" .Values.litellm.url }}{{ end -}}
{{- end }}

{{/* Nom d'hôte d'une URL, sans port. */}}
{{- define "myskills.host" -}}{{ (urlParse .).host | splitList ":" | first }}{{- end }}

{{/* Configuration du service (remote.json), validée par remote_server.py check. */}}
{{- define "myskills.remoteJson" -}}
{{- $v := .Values -}}
{{- $gitlab := trimSuffix "/" $v.gitlab.url -}}
{{- $discovery := dict "topic" $v.gitlab.discovery.topic "title" $v.gitlab.discovery.title -}}
{{- if $v.gitlab.discovery.group }}{{ $_ := set $discovery "group" $v.gitlab.discovery.group }}{{ end -}}
{{- $agent := dict "timeout" $v.agent.timeout "continue_args" (list "--continue") -}}
{{- $foundry := include "myskills.foundry" . -}}
{{- $m := ternary $v.foundry.models $v.litellm.models (not (empty $foundry)) -}}
{{- if eq $v.agent.kind "claude" -}}
{{- $_ := set $agent "command" (list "claude" "-p" "{prompt}" "--output-format" "text" "--permission-mode" "acceptEdits" "--allowedTools" "Bash(uv run:*)" "Bash(python:*)" "Read" "Write" "Edit" "Glob" "Grep" "Skill" "Agent") -}}
{{- $env := dict "ANTHROPIC_DEFAULT_HAIKU_MODEL" $m.simple "ANTHROPIC_DEFAULT_SONNET_MODEL" $m.moyen "ANTHROPIC_DEFAULT_OPUS_MODEL" $m.complexe "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC" "1" "DISABLE_AUTOUPDATER" "1" -}}
{{- if $foundry }}{{ $_ := set $env "CLAUDE_CODE_USE_FOUNDRY" "1" }}{{ $_ := set $env "ANTHROPIC_FOUNDRY_RESOURCE" $v.foundry.resource }}
{{- else }}{{ $_ := set $env "ANTHROPIC_BASE_URL" (trimSuffix "/v1" (trimSuffix "/" $v.litellm.url)) }}{{ end -}}
{{- $_ := set $agent "env" $env -}}
{{- else -}}
{{- $_ := set $agent "command" (list "opencode" "run" "{prompt}") -}}
{{- $_ := set $agent "skip_lines" (list "^> \\S+ · ") -}}
{{- $env := dict "OPENCODE_CONFIG" "/etc/myskills/opencode.json" "OPENCODE_DISABLE_AUTOUPDATE" "true" "OPENCODE_DISABLE_MODELS_FETCH" "true" "OPENCODE_DISABLE_LSP_DOWNLOAD" "true" -}}
{{- if not $foundry }}{{ $_ := set $env "LITELLM_BASE_URL" $v.litellm.url }}{{ end -}}
{{- $_ := set $agent "env" $env -}}
{{- end -}}
{{- $runner := dict "kind" "kubernetes" "image" (include "myskills.image" .) "namespace" .Release.Namespace
      "secret" $v.secrets.session "git_secret" $v.secrets.git "config_map" (printf "%s-config" (include "myskills.name" .))
      "idle_minutes" $v.sessions.idleMinutes "retention_days" $v.sessions.retentionDays "session_size" $v.sessions.size
      "resources" $v.sessions.resources "tools" $v.agent.kind "models" "/etc/myskills/models.json" -}}
{{- if $v.sessions.storageClass }}{{ $_ := set $runner "storage_class" $v.sessions.storageClass }}{{ end -}}
{{- if $v.caSecret }}{{ $_ := set $runner "ca_secret" $v.caSecret }}{{ end -}}
{{- $config := dict
      "missions" (dict)
      "discovery" $discovery
      "workdir" "/work/clones"
      "branch_prefix" $v.gitlab.branchPrefix
      "allowed_hosts" (list (include "myskills.host" $v.gitlab.url) (include "myskills.llmHost" .) | uniq)
      "access" (dict "provider" "gitlab" "api" (printf "%s/api/v4" $gitlab) "token_env" "GITLAB_ACCESS_TOKEN" "read_level" $v.gitlab.readLevel "write_level" $v.gitlab.writeLevel)
      "agent" $agent
      "git" (dict "name" $v.gitlab.commitAuthor.name "email" $v.gitlab.commitAuthor.email)
      "server" (dict "host" "0.0.0.0" "port" $v.service.port "token_env" "MYSKILLS_REMOTE_TOKEN" "max_jobs" $v.service.maxJobs)
      "runner" $runner -}}
{{- if $v.mergeRequests.enabled -}}
{{- $merge := dict "on" $v.mergeRequests.triggers "draft" $v.mergeRequests.draft "token_env" "GITLAB_MR_TOKEN" -}}
{{- if $v.mergeRequests.target }}{{ $_ := set $merge "target" $v.mergeRequests.target }}{{ end -}}
{{- if $v.mergeRequests.labels }}{{ $_ := set $merge "labels" $v.mergeRequests.labels }}{{ end -}}
{{- $_ := set $config "merge_requests" $merge -}}
{{- end -}}
{{- toPrettyJson $config }}
{{- end }}

{{/* Configuration d'OpenCode : un seul fournisseur (LiteLLM ou Azure AI Foundry), rien ne se télécharge, shell limité. */}}
{{- define "myskills.opencodeJson" -}}
{{- $foundry := include "myskills.foundry" . -}}
{{- $id := ternary "foundry" "litellm" (not (empty $foundry)) -}}
{{- $m := ternary .Values.foundry.models .Values.litellm.models (not (empty $foundry)) -}}
{{- $models := dict -}}
{{- range $level, $alias := $m }}{{ $_ := set $models $alias (dict "name" (printf "%s (%s)" $alias (ternary "Azure AI Foundry" "LiteLLM" (not (empty $foundry))))) }}{{ end -}}
{{- $provider := dict -}}
{{- if $foundry -}}
{{- /* API Anthropic de Foundry : clé en x-api-key (fournisseur Anthropic d'OpenCode) et en api-key (Azure). */ -}}
{{- $provider = dict "npm" "@ai-sdk/anthropic" "name" "Azure AI Foundry"
      "options" (dict "baseURL" (printf "https://%s/anthropic/v1" (include "myskills.foundryHost" .)) "apiKey" "{env:ANTHROPIC_FOUNDRY_API_KEY}"
                      "headers" (dict "api-key" "{env:ANTHROPIC_FOUNDRY_API_KEY}")) "models" $models -}}
{{- else -}}
{{- $provider = dict "npm" "@ai-sdk/openai-compatible" "name" "LiteLLM"
      "options" (dict "baseURL" "{env:LITELLM_BASE_URL}" "apiKey" "{env:LITELLM_API_KEY}") "models" $models -}}
{{- end -}}
{{- $bash := dict "*" "deny" "uv run *" "allow" "python *" "allow" "git status*" "allow" "git diff*" "allow" "git log*" "allow" -}}
{{- toPrettyJson (dict
      "$schema" "https://opencode.ai/config.json"
      "provider" (dict $id $provider)
      "enabled_providers" (list $id)
      "model" (printf "%s/%s" $id $m.moyen)
      "small_model" (printf "%s/%s" $id $m.simple)
      "share" "disabled"
      "autoupdate" false
      "permission" (dict "edit" "allow" "webfetch" "deny" "bash" $bash)) }}
{{- end }}

{{/* Modèle de chaque niveau des agents de myskills (install.py sync --models). */}}
{{- define "myskills.modelsJson" -}}
{{- $foundry := include "myskills.foundry" . -}}
{{- $id := ternary "foundry" "litellm" (not (empty $foundry)) -}}
{{- $m := ternary .Values.foundry.models .Values.litellm.models (not (empty $foundry)) -}}
{{- toPrettyJson (dict
      "opencode" (dict "simple" (printf "%s/%s" $id $m.simple) "moyen" (printf "%s/%s" $id $m.moyen) "complexe" (printf "%s/%s" $id $m.complexe))
      "claude" (dict "simple" "haiku" "moyen" "sonnet" "complexe" "opus")) }}
{{- end }}

{{/* Montage de l'autorité interne et fichier des autorités (image + interne), construit au démarrage. */}}
{{- define "myskills.caInit" -}}
- name: ca-bundle
  image: {{ include "myskills.serviceImage" . }}
  command: ["sh", "-c", "cat /etc/ssl/certs/ca-certificates.crt /etc/myskills-ca/*.crt > /ca/ca-bundle.crt"]
  securityContext: {allowPrivilegeEscalation: false, capabilities: {drop: [ALL]}}
  resources: {requests: {cpu: 10m, memory: 16Mi}, limits: {memory: 64Mi}}
  volumeMounts:
    - {name: ca, mountPath: /etc/myskills-ca, readOnly: true}
    - {name: ca-bundle, mountPath: /ca}
{{- end }}

{{- define "myskills.dnsEgress" -}}
- to:
    - namespaceSelector: {}
      podSelector:
        matchLabels: {k8s-app: kube-dns}
  ports: [{port: 53, protocol: UDP}, {port: 53, protocol: TCP}]
{{- end }}

{{- define "myskills.gitlabEgress" -}}
- to:
    {{- range .Values.gitlab.cidrs }}
    - ipBlock: {cidr: {{ . }}}
    {{- end }}
  ports: [{port: 443}, {port: 22}]
{{- end }}
