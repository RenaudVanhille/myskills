{{- define "myskills.name" -}}{{ .Release.Name | trunc 40 | trimSuffix "-" }}{{- end }}

{{- define "myskills.labels" -}}
app.kubernetes.io/part-of: myskills-remote
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{- define "myskills.image" -}}{{ .Values.image.repository }}:{{ .Values.image.tag }}{{- end }}
{{- define "myskills.serviceImage" -}}{{ .Values.serviceImage.repository }}:{{ .Values.serviceImage.tag }}{{- end }}

{{/* Nom d'hôte d'une URL, sans port. */}}
{{- define "myskills.host" -}}{{ (urlParse .).host | splitList ":" | first }}{{- end }}

{{/* Configuration du service (remote.json), validée par remote_server.py check. */}}
{{- define "myskills.remoteJson" -}}
{{- $v := .Values -}}
{{- $gitlab := trimSuffix "/" $v.gitlab.url -}}
{{- $discovery := dict "topic" $v.gitlab.discovery.topic "title" $v.gitlab.discovery.title -}}
{{- if $v.gitlab.discovery.group }}{{ $_ := set $discovery "group" $v.gitlab.discovery.group }}{{ end -}}
{{- $agent := dict "timeout" $v.agent.timeout "continue_args" (list "--continue") -}}
{{- if eq $v.agent.kind "claude" -}}
{{- $_ := set $agent "command" (list "claude" "-p" "{prompt}" "--output-format" "text" "--permission-mode" "acceptEdits" "--allowedTools" "Bash(uv run:*)" "Bash(python:*)" "Read" "Write" "Edit" "Glob" "Grep" "Skill" "Agent") -}}
{{- $_ := set $agent "env" (dict "ANTHROPIC_BASE_URL" (trimSuffix "/v1" (trimSuffix "/" $v.litellm.url)) "ANTHROPIC_DEFAULT_HAIKU_MODEL" $v.litellm.models.simple "ANTHROPIC_DEFAULT_SONNET_MODEL" $v.litellm.models.moyen "ANTHROPIC_DEFAULT_OPUS_MODEL" $v.litellm.models.complexe "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC" "1" "DISABLE_AUTOUPDATER" "1") -}}
{{- else -}}
{{- $_ := set $agent "command" (list "opencode" "run" "{prompt}") -}}
{{- $_ := set $agent "skip_lines" (list "^> \\S+ · ") -}}
{{- $_ := set $agent "env" (dict "OPENCODE_CONFIG" "/etc/myskills/opencode.json" "LITELLM_BASE_URL" $v.litellm.url "OPENCODE_DISABLE_AUTOUPDATE" "true" "OPENCODE_DISABLE_MODELS_FETCH" "true" "OPENCODE_DISABLE_LSP_DOWNLOAD" "true") -}}
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
      "allowed_hosts" (list (include "myskills.host" $v.gitlab.url) (include "myskills.host" $v.litellm.url) | uniq)
      "access" (dict "provider" "gitlab" "api" (printf "%s/api/v4" $gitlab) "token_env" "GITLAB_ACCESS_TOKEN" "read_level" $v.gitlab.readLevel "write_level" $v.gitlab.writeLevel)
      "agent" $agent
      "git" (dict "name" $v.gitlab.commitAuthor.name "email" $v.gitlab.commitAuthor.email)
      "server" (dict "host" "0.0.0.0" "port" $v.service.port "token_env" "MYSKILLS_REMOTE_TOKEN" "max_jobs" $v.service.maxJobs)
      "runner" $runner -}}
{{- if and $v.viewer.enabled $v.openWebui.ingress.enabled -}}
{{- $_ := set $config "viewer" (dict "url" (printf "https://%s%s" $v.openWebui.ingress.host $v.viewer.path) "link_days" $v.viewer.linkDays) -}}
{{- end -}}
{{- if $v.mergeRequests.enabled -}}
{{- $merge := dict "on" $v.mergeRequests.triggers "draft" $v.mergeRequests.draft "token_env" "GITLAB_MR_TOKEN" -}}
{{- if $v.mergeRequests.target }}{{ $_ := set $merge "target" $v.mergeRequests.target }}{{ end -}}
{{- if $v.mergeRequests.labels }}{{ $_ := set $merge "labels" $v.mergeRequests.labels }}{{ end -}}
{{- $_ := set $config "merge_requests" $merge -}}
{{- end -}}
{{- toPrettyJson $config }}
{{- end }}

{{/* Configuration d'OpenCode : LiteLLM seul fournisseur, rien ne se télécharge, shell limité. */}}
{{- define "myskills.opencodeJson" -}}
{{- $m := .Values.litellm.models -}}
{{- $models := dict -}}
{{- range $level, $alias := $m }}{{ $_ := set $models $alias (dict "name" (printf "%s (LiteLLM)" $alias)) }}{{ end -}}
{{- $provider := dict "npm" "@ai-sdk/openai-compatible" "name" "LiteLLM"
      "options" (dict "baseURL" "{env:LITELLM_BASE_URL}" "apiKey" "{env:LITELLM_API_KEY}") "models" $models -}}
{{- $bash := dict "*" "deny" "uv run *" "allow" "python *" "allow" "git status*" "allow" "git diff*" "allow" "git log*" "allow" -}}
{{- toPrettyJson (dict
      "$schema" "https://opencode.ai/config.json"
      "provider" (dict "litellm" $provider)
      "enabled_providers" (list "litellm")
      "model" (printf "litellm/%s" $m.moyen)
      "small_model" (printf "litellm/%s" $m.simple)
      "share" "disabled"
      "autoupdate" false
      "permission" (dict "edit" "allow" "webfetch" "deny" "bash" $bash)) }}
{{- end }}

{{/* Modèle de chaque niveau des agents de myskills (install.py sync --models). */}}
{{- define "myskills.modelsJson" -}}
{{- $m := .Values.litellm.models -}}
{{- toPrettyJson (dict
      "opencode" (dict "simple" (printf "litellm/%s" $m.simple) "moyen" (printf "litellm/%s" $m.moyen) "complexe" (printf "litellm/%s" $m.complexe))
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
