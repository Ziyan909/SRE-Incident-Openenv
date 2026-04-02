const state = {
  tasks: [],
  activeTier: "easy",
  selectedTaskId: null,
  queuedActions: [],
  sessionId: null,
  currentObservation: null,
  currentResult: null,
  timeline: [],
  currentView: "tasks",
  aiHistory: [],
};

const AI_RUNTIME_STORAGE_KEY = "sre-ai-runtime-settings-v1";

const els = {
  taskCount:        document.getElementById("task-count"),
  activeTierCount:  document.getElementById("active-tier-count"),
  activeTierTitle:  document.getElementById("active-tier-title"),
  activeTierList:   document.getElementById("active-tier-list"),
  sessionState:     document.getElementById("session-state"),
  selectedTaskName: document.getElementById("selected-task-name"),
  scenarioDesc:     document.getElementById("scenario-description"),
  modeGuidance:     document.getElementById("mode-guidance"),
  selectedTier:     document.getElementById("selected-tier"),
  selectedMaxSteps: document.getElementById("selected-max-steps"),
  selectedTaskId:   document.getElementById("selected-task-id"),
  sessionSeed:      document.getElementById("session-seed"),
  serviceFocus:     document.getElementById("service-focus"),
  actionSpace:      document.getElementById("action-space"),
  statusBadge:      document.getElementById("status-badge"),
  alerts:           document.getElementById("alerts"),
  incidentTicket:   document.getElementById("incident-ticket"),
  lifecycleStage:   document.getElementById("lifecycle-stage"),
  businessImpact:   document.getElementById("business-impact"),
  trafficStatus:    document.getElementById("traffic-status"),
  queueStatus:      document.getElementById("queue-status"),
  featureFlags:     document.getElementById("feature-flags"),
  regionalStatus:   document.getElementById("regional-status"),
  telemetryWarnings:document.getElementById("telemetry-warnings"),
  serviceOwners:    document.getElementById("service-owners"),
  runbookHints:     document.getElementById("runbook-hints"),
  deployHistory:    document.getElementById("deploy-history"),
  configFindings:   document.getElementById("config-findings"),
  validationStatus: document.getElementById("validation-status"),
  changeEvents:     document.getElementById("change-events"),
  rolloutStatus:    document.getElementById("rollout-status"),
  traceOutput:      document.getElementById("trace-output"),
  servicesGrid:     document.getElementById("services-grid"),
  queuedActions:    document.getElementById("queued-actions"),
  baselineOutput:   document.getElementById("baseline-output"),
  baselineProvider: document.getElementById("baseline-provider"),
  baselineModel:    document.getElementById("baseline-model"),
  benchmarkSeeds:   document.getElementById("benchmark-seeds"),
  benchmarkProvider:document.getElementById("benchmark-provider"),
  benchmarkModel:   document.getElementById("benchmark-model"),
  benchmarkOutput:  document.getElementById("benchmark-output"),
  benchmarkHistoryOutput: document.getElementById("benchmark-history-output"),
  replayOutput:     document.getElementById("replay-output"),
  judgeOutput:      document.getElementById("judge-output"),
  replaySteps:      document.getElementById("replay-steps"),
  sessionHistory:   document.getElementById("session-history"),
  comparisonOutput: document.getElementById("comparison-output"),
  graderOutput:     document.getElementById("grader-output"),
  evidenceOutput:   document.getElementById("evidence-output"),
  unknownsOutput:   document.getElementById("unknowns-output"),
  timeline:         document.getElementById("timeline"),
  actionType:       document.getElementById("action-type"),
  service:          document.getElementById("service"),
  lines:            document.getElementById("lines"),
  windowSeconds:    document.getElementById("window-seconds"),
  targetVersion:    document.getElementById("target-version"),
  replicas:         document.getElementById("replicas"),
  rootCauseService: document.getElementById("root-cause-service"),
  rootCauseCategory:document.getElementById("root-cause-category"),
  fixDescription:   document.getElementById("fix-description"),
  viewTabs:         Array.from(document.querySelectorAll(".view-tab")),
  tasksView:        document.getElementById("tasks-view"),
  sessionView:      document.getElementById("session-view"),
  runtimeView:      document.getElementById("runtime-view"),
  aiControlView:    document.getElementById("ai-control-view"),
  aiProvider:       document.getElementById("ai-provider"),
  aiCustomProviderField: document.getElementById("ai-custom-provider-field"),
  aiCustomProvider: document.getElementById("ai-custom-provider"),
  aiModel:          document.getElementById("ai-model"),
  aiApiKey:         document.getElementById("ai-api-key"),
  aiBaseUrl:        document.getElementById("ai-base-url"),
  aiSelectedTask:   document.getElementById("ai-selected-task"),
  aiSelectedTier:   document.getElementById("ai-selected-tier"),
  aiSelectedSeed:   document.getElementById("ai-selected-seed"),
  aiCurrentSession: document.getElementById("ai-current-session"),
  aiSettingsStatus: document.getElementById("ai-settings-status"),
  aiValidationOutput: document.getElementById("ai-validation-output"),
  aiRunSeed:        document.getElementById("ai-run-seed"),
  aiBenchmarkSeeds: document.getElementById("ai-benchmark-seeds"),
  aiPersistMode:    document.getElementById("ai-persist-mode"),
  aiCredentialMode: document.getElementById("ai-credential-mode"),
  aiBaselineOutput: document.getElementById("ai-baseline-output"),
  aiBenchmarkOutput:document.getElementById("ai-benchmark-output"),
  aiCompareOutput:  document.getElementById("ai-compare-output"),
  aiRunHistory:     document.getElementById("ai-run-history"),
};

const actionTypes = [
  "read_logs", "check_metrics", "ping_service", "inspect_deploy", "query_traces",
  "check_runbook", "diff_config", "drain_traffic", "failover_region",
  "restart_service", "rollback_deploy", "scale_up", "check_dependencies", "submit_diagnosis",
];

function setStatus(text, mode = "idle") {
  const badge = els.statusBadge;
  badge.textContent = "● " + text;
  badge.className = "status-pill " + (mode === "working" ? "status-working" : mode === "error" ? "status-error" : "status-ready");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function reportError(context, error) {
  console.error(context, error);
  const message = error && error.message ? error.message : String(error);
  setStatus(`${context}: ${message}`, "error");
}

function populateActionTypes() {
  els.actionType.innerHTML = actionTypes.map(t => `<option value="${t}">${t}</option>`).join("");
}

function selectedTask() {
  return state.tasks.find(t => t.task_id === state.selectedTaskId) || null;
}

function currentSeedValue() {
  return Number(els.sessionSeed.value || 0);
}

function tasksForTier(tier) {
  return state.tasks.filter((task) => task.tier === tier);
}

function randomTaskForActiveTier() {
  const tierTasks = tasksForTier(state.activeTier);
  if (!tierTasks.length) return null;
  return tierTasks[Math.floor(Math.random() * tierTasks.length)];
}

function ensureTaskSelection({ randomize = false } = {}) {
  let task = selectedTask();
  if (task) return task;
  const tierTasks = tasksForTier(state.activeTier);
  if (!tierTasks.length) return null;
  task = randomize ? randomTaskForActiveTier() : tierTasks[0];
  if (!task) return null;
  state.selectedTaskId = task.task_id;
  renderTasks();
  renderSelectedTask();
  return task;
}

function clearSessionForTaskChange() {
  state.sessionId = null;
  state.currentObservation = null;
  state.currentResult = null;
  state.timeline = [];
  renderSessionState();
  renderObservation();
  renderSummary();
  renderTimeline();
}

async function requestJson(url, options) {
  const res = await fetch(url, options);
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = payload && typeof payload.detail === "string" ? payload.detail : `Request failed (${res.status})`;
    throw new Error(detail);
  }
  return payload;
}

function renderTasks() {
  els.taskCount.textContent = state.tasks.length;
  const tierTasks = tasksForTier(state.activeTier);
  els.activeTierCount.textContent = `${tierTasks.length} scenarios`;
  els.activeTierTitle.textContent = state.activeTier.charAt(0).toUpperCase() + state.activeTier.slice(1);

  const renderTier = (tasks) => tasks.map(task => `
    <article class="task-card ${task.task_id === state.selectedTaskId ? "is-active" : ""}" data-task-id="${task.task_id}">
      <div class="task-title-row">
        <h3>${task.name}</h3>
        <span class="tier-pill">${task.tier}</span>
      </div>
      <p class="body-copy">${task.description}</p>
      <p class="task-meta">max_steps=${task.max_steps} · investigation scope intentionally hidden</p>
    </article>
  `).join("");

  els.activeTierList.innerHTML = renderTier(tierTasks) || `<div class="is-empty">No scenarios available for this tier.</div>`;

  document.querySelectorAll(".tier-mode-button").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.tier === state.activeTier);
  });

  document.querySelectorAll(".task-card").forEach(card => {
    card.addEventListener("click", () => {
      const nextTaskId = card.dataset.taskId;
      if (state.selectedTaskId !== nextTaskId) {
        clearSessionForTaskChange();
      }
      state.selectedTaskId = nextTaskId;
      renderTasks();
      renderSelectedTask();
    });
  });
}

function renderSelectedTask() {
  const task = selectedTask();
  if (!task) {
    els.selectedTaskName.textContent = `${state.activeTier.charAt(0).toUpperCase() + state.activeTier.slice(1)} mode ready`;
    els.scenarioDesc.textContent = `Choose a scenario from the ${state.activeTier} list, or press Start Session to launch a random ${state.activeTier} scenario.`;
    els.modeGuidance.textContent = guidanceForTier(state.activeTier);
    els.selectedTier.textContent = state.activeTier;
    els.selectedMaxSteps.textContent = "—";
    els.selectedTaskId.textContent = "random-on-start";
    els.serviceFocus.innerHTML = "";
    els.actionSpace.innerHTML = "";
    renderAiTaskContext();
    return;
  }
  els.selectedTaskName.textContent = task.name;
  els.scenarioDesc.textContent = task.description;
  els.modeGuidance.textContent = guidanceForTier(task.tier);
  els.selectedTier.textContent = task.tier;
  els.selectedMaxSteps.textContent = String(task.max_steps);
  els.selectedTaskId.textContent = task.task_id;
  els.serviceFocus.innerHTML = `<span class="chip">Service focus hidden until investigated</span>`;
  els.actionSpace.innerHTML = task.action_space.map(s => `<span class="chip">${s}</span>`).join("");
  renderAiTaskContext();
}

function guidanceForTier(tier) {
  if (tier === "hard") {
    return "Hard mode is partially observable: versions start hidden, dependencies must be discovered, and you must validate recovery with an explicit ping before final diagnosis.";
  }
  if (tier === "medium") {
    return "Medium mode rewards targeted investigation: inspect symptoms, discover dependencies, and confirm the fix before submitting diagnosis.";
  }
  return "Easy mode still hides some details up front: inspect metrics or logs before fixing so you do not waste steps.";
}

function renderObservation() {
  const obs = state.currentObservation;
  if (!obs) {
    els.alerts.className = "alert-list is-empty";
    els.alerts.textContent = "Start a session to see active alerts.";
    els.incidentTicket.className = "alert-list is-empty";
    els.incidentTicket.textContent = "Incident ticket and operator notes appear here.";
    els.lifecycleStage.className = "alert-list is-empty";
    els.lifecycleStage.textContent = "Lifecycle stage appears here.";
    els.businessImpact.className = "alert-list is-empty";
    els.businessImpact.textContent = "Business impact appears here.";
    els.trafficStatus.className = "alert-list is-empty";
    els.trafficStatus.textContent = "Traffic control status appears here.";
    els.queueStatus.className = "alert-list is-empty";
    els.queueStatus.textContent = "Queue depth appears here.";
    els.featureFlags.className = "alert-list is-empty";
    els.featureFlags.textContent = "Feature flag state appears here.";
    els.regionalStatus.className = "alert-list is-empty";
    els.regionalStatus.textContent = "Regional status appears here.";
    els.telemetryWarnings.className = "alert-list is-empty";
    els.telemetryWarnings.textContent = "Telemetry warnings appear here.";
    els.serviceOwners.className = "alert-list is-empty";
    els.serviceOwners.textContent = "Service ownership contacts appear here.";
    els.runbookHints.className = "alert-list is-empty";
    els.runbookHints.textContent = "Relevant runbook hints appear here.";
    els.deployHistory.className = "alert-list is-empty";
    els.deployHistory.textContent = "Deploy and change history appears here.";
    els.configFindings.className = "alert-list is-empty";
    els.configFindings.textContent = "Config findings appear here.";
    els.validationStatus.className = "alert-list is-empty";
    els.validationStatus.textContent = "Validation status appears here after investigation or remediation.";
    els.changeEvents.className = "alert-list is-empty";
    els.changeEvents.textContent = "Recent change and deployment events appear here.";
    els.rolloutStatus.className = "alert-list is-empty";
    els.rolloutStatus.textContent = "Rollout and canary state appears here.";
    els.traceOutput.className = "alert-list is-empty";
    els.traceOutput.textContent = "Trace clues appear here after investigation.";
    els.servicesGrid.className = "svc-grid is-empty";
    els.servicesGrid.textContent = "No services loaded.";
    els.evidenceOutput.className = "is-empty";
    els.evidenceOutput.textContent = "Inspections and discovered evidence will appear here.";
    els.unknownsOutput.className = "is-empty";
    els.unknownsOutput.textContent = "Hidden versions, dependencies, and unexplored services will appear here.";
    return;
  }

  const alerts = obs.active_alerts || [];
  if (!alerts.length) {
    els.alerts.className = "alert-list is-empty";
    els.alerts.textContent = "No active alerts.";
  } else {
    els.alerts.className = "alert-list";
    els.alerts.innerHTML = alerts.map(a => `<article class="alert-item">${a}</article>`).join("");
  }

  const ticketLines = [obs.incident_ticket, ...(obs.operator_notes || [])].filter(Boolean);
  if (ticketLines.length) {
    els.incidentTicket.className = "alert-list";
    els.incidentTicket.innerHTML = ticketLines.map((line) => `<article class="alert-item">${line}</article>`).join("");
  } else {
    els.incidentTicket.className = "alert-list is-empty";
    els.incidentTicket.textContent = "No incident ticket context surfaced.";
  }

  els.lifecycleStage.className = "alert-list";
  els.lifecycleStage.innerHTML = `<article class="alert-item">Lifecycle stage: ${obs.lifecycle_stage || "unknown"}</article>`;

  const impactLines = obs.business_impact || [];
  if (impactLines.length) {
    els.businessImpact.className = "alert-list";
    els.businessImpact.innerHTML = impactLines.map((line) => `<article class="alert-item">${line}</article>`).join("");
  } else {
    els.businessImpact.className = "alert-list is-empty";
    els.businessImpact.textContent = "No business impact surfaced.";
  }

  const trafficLines = obs.traffic_status || [];
  if (trafficLines.length) {
    els.trafficStatus.className = "alert-list";
    els.trafficStatus.innerHTML = trafficLines.map((line) => `<article class="alert-item">${line}</article>`).join("");
  } else {
    els.trafficStatus.className = "alert-list is-empty";
    els.trafficStatus.textContent = "No traffic control status surfaced.";
  }

  const queueLines = obs.queue_status || [];
  if (queueLines.length) {
    els.queueStatus.className = "alert-list";
    els.queueStatus.innerHTML = queueLines.map((line) => `<article class="alert-item">${line}</article>`).join("");
  } else {
    els.queueStatus.className = "alert-list is-empty";
    els.queueStatus.textContent = "No queue pressure surfaced.";
  }

  const flagLines = obs.feature_flags || [];
  if (flagLines.length) {
    els.featureFlags.className = "alert-list";
    els.featureFlags.innerHTML = flagLines.map((line) => `<article class="alert-item">${line}</article>`).join("");
  } else {
    els.featureFlags.className = "alert-list is-empty";
    els.featureFlags.textContent = "No feature flag drift surfaced.";
  }

  const regionLines = obs.regional_status || [];
  if (regionLines.length) {
    els.regionalStatus.className = "alert-list";
    els.regionalStatus.innerHTML = regionLines.map((line) => `<article class="alert-item">${line}</article>`).join("");
  } else {
    els.regionalStatus.className = "alert-list is-empty";
    els.regionalStatus.textContent = "No regional state surfaced.";
  }

  const telemetryLines = obs.telemetry_warnings || [];
  if (telemetryLines.length) {
    els.telemetryWarnings.className = "alert-list";
    els.telemetryWarnings.innerHTML = telemetryLines.map((line) => `<article class="alert-item">${line}</article>`).join("");
  } else {
    els.telemetryWarnings.className = "alert-list is-empty";
    els.telemetryWarnings.textContent = "No telemetry warnings surfaced.";
  }

  const ownerLines = obs.service_owners || [];
  if (ownerLines.length) {
    els.serviceOwners.className = "alert-list";
    els.serviceOwners.innerHTML = ownerLines.map((line) => `<article class="alert-item">${line}</article>`).join("");
  } else {
    els.serviceOwners.className = "alert-list is-empty";
    els.serviceOwners.textContent = "No ownership contacts surfaced.";
  }

  const runbookLines = obs.runbook_hints || [];
  if (runbookLines.length) {
    els.runbookHints.className = "alert-list";
    els.runbookHints.innerHTML = runbookLines.map((line) => `<article class="alert-item">${line}</article>`).join("");
  } else {
    els.runbookHints.className = "alert-list is-empty";
    els.runbookHints.textContent = "No runbook hints surfaced.";
  }

  const deployLines = obs.deploy_history || [];
  if (deployLines.length) {
    els.deployHistory.className = "alert-list";
    els.deployHistory.innerHTML = deployLines.map((line) => `<article class="alert-item">${line}</article>`).join("");
  } else {
    els.deployHistory.className = "alert-list is-empty";
    els.deployHistory.textContent = "No deploy history surfaced.";
  }

  const configLines = obs.config_findings || [];
  if (configLines.length) {
    els.configFindings.className = "alert-list";
    els.configFindings.innerHTML = configLines.map((line) => `<article class="alert-item">${line}</article>`).join("");
  } else {
    els.configFindings.className = "alert-list is-empty";
    els.configFindings.textContent = "No config findings surfaced.";
  }

  els.validationStatus.className = "alert-list";
  els.validationStatus.innerHTML = `<article class="alert-item">${obs.validation_status || "No validation state available."}</article>`;

  const changeEvents = obs.change_events || [];
  if (changeEvents.length) {
    els.changeEvents.className = "alert-list";
    els.changeEvents.innerHTML = changeEvents.map((line) => `<article class="alert-item">${line}</article>`).join("");
  } else {
    els.changeEvents.className = "alert-list is-empty";
    els.changeEvents.textContent = "No recent change events surfaced.";
  }

  const rolloutStatus = obs.rollout_status || [];
  if (rolloutStatus.length) {
    els.rolloutStatus.className = "alert-list";
    els.rolloutStatus.innerHTML = rolloutStatus.map((line) => `<article class="alert-item">${line}</article>`).join("");
  } else {
    els.rolloutStatus.className = "alert-list is-empty";
    els.rolloutStatus.textContent = "No rollout state surfaced.";
  }

  const traceSpans = obs.trace_spans || [];
  if (traceSpans.length) {
    els.traceOutput.className = "alert-list";
    els.traceOutput.innerHTML = traceSpans.map((line) => `<article class="alert-item">${line}</article>`).join("");
  } else {
    els.traceOutput.className = "alert-list is-empty";
    els.traceOutput.textContent = "No trace clues surfaced.";
  }

  if (obs.evidence_summary?.length) {
    els.evidenceOutput.className = "";
    els.evidenceOutput.innerHTML = obs.evidence_summary.map((line) => `<p class="tiny">${line}</p>`).join("");
  } else {
    els.evidenceOutput.className = "is-empty";
    els.evidenceOutput.textContent = "Inspections and discovered evidence will appear here.";
  }

  if (obs.unknowns?.length) {
    els.unknownsOutput.className = "";
    els.unknownsOutput.innerHTML = obs.unknowns.map((line) => `<p class="tiny">${line}</p>`).join("");
  } else {
    els.unknownsOutput.className = "is-empty";
    els.unknownsOutput.textContent = "No major unknowns remain.";
  }

  const services = Object.values(obs.services || {});
  els.servicesGrid.className = "svc-grid";
  els.servicesGrid.innerHTML = services.map(svc => `
    <article class="svc-card status-${svc.status}">
      <header>
        <h3>${svc.name}</h3>
        <span class="status-tag status-${svc.status}">${svc.status}</span>
      </header>
      <p class="svc-meta">ver=${svc.version} · deps=${svc.dependencies.join(", ") || "none"}</p>
      <div class="metrics-row">
        <div class="metric-chip"><span>Error Rate</span><strong>${svc.metrics.error_rate}</strong></div>
        <div class="metric-chip"><span>Latency</span><strong>${svc.metrics.latency_ms}ms</strong></div>
        <div class="metric-chip"><span>CPU</span><strong>${svc.metrics.cpu_percent}%</strong></div>
        <div class="metric-chip"><span>Replicas</span><strong>${svc.metrics.replicas}</strong></div>
      </div>
    </article>
  `).join("");
}

function renderQueue() {
  if (!state.queuedActions.length) {
    els.queuedActions.className = "q-list is-empty";
    els.queuedActions.textContent = "No actions queued.";
    return;
  }
  els.queuedActions.className = "q-list";
  els.queuedActions.innerHTML = state.queuedActions.map((action, i) => `
    <article class="queue-item">
      <h4>#${i + 1} ${action.action_type}</h4>
      <p>${Object.entries(action).filter(([k]) => k !== "action_type").map(([k,v]) => `${k}=${v}`).join(" · ") || "no extra fields"}</p>
    </article>
  `).join("");
}

function renderBaseline(result) {
  els.baselineOutput.className = "";
  els.baselineOutput.innerHTML = baselineMarkup(result);
}

function baselineMarkup(result) {
  return `
    <div class="result-grid">
      <div class="result-stat"><span>Task</span><strong>${escapeHtml(result.task_id)}</strong></div>
      <div class="result-stat"><span>Mode</span><strong>${escapeHtml(result.mode)}</strong></div>
      <div class="result-stat"><span>Score</span><strong>${escapeHtml(result.score)}</strong></div>
      <div class="result-stat"><span>Steps</span><strong>${escapeHtml(result.steps_taken)}</strong></div>
    </div>
    <p class="tiny">solved=${escapeHtml(result.solved)} · seed=${escapeHtml(result.seed)}${result.model ? ` · model=${escapeHtml(result.model)}` : ""}</p>
    ${result.error ? `<p class="tiny">error=${escapeHtml(result.error)}</p>` : ""}
    ${renderAnalyticsTiny(result.analytics)}
  `;
}

function renderBenchmark(report) {
  els.benchmarkOutput.className = "";
  els.benchmarkOutput.innerHTML = benchmarkMarkup(report);
}

function benchmarkMarkup(report) {
  return `
    <div class="result-grid">
      <div class="result-stat"><span>Scenarios</span><strong>${escapeHtml(report.scenario_count)}</strong></div>
      <div class="result-stat"><span>Templates</span><strong>${escapeHtml(report.template_count)}</strong></div>
      <div class="result-stat"><span>Avg Score</span><strong>${report.overall_average_score.toFixed(2)}</strong></div>
      <div class="result-stat"><span>Solve Rate</span><strong>${(report.overall_solve_rate * 100).toFixed(0)}%</strong></div>
      <div class="result-stat"><span>Mode</span><strong>${escapeHtml(report.mode)}</strong></div>
    </div>
    <p class="tiny">public=${escapeHtml(report.public_scenario_count)} holdout=${escapeHtml(report.holdout_scenario_count)} generated_at=${escapeHtml(report.generated_at)}</p>
    ${report.tier_summaries.map((item) => `<p class="tiny">${escapeHtml(item.tier)}: avg=${item.average_score.toFixed(2)} solve_rate=${(item.solve_rate * 100).toFixed(0)}% steps=${item.average_steps.toFixed(1)}</p>`).join("")}
    ${renderAnalyticsTiny(report.analytics_summary)}
    <p class="tiny">families: ${Object.entries(report.family_breakdown).map(([name, count]) => `${escapeHtml(name)}=${escapeHtml(count)}`).join(" · ")}</p>
    ${report.hardest_scenarios.map((item) => `<p class="tiny">hard case: ${escapeHtml(item.task_id)} score=${item.score.toFixed(2)} solved=${escapeHtml(item.solved)}</p>`).join("")}
  `;
}

function renderReplay(record) {
  els.replayOutput.className = "";
  els.replayOutput.innerHTML = `
    <p class="tiny">session=${record.session_id} scenario=${record.scenario_id} seed=${record.seed}</p>
    <p class="tiny">steps=${record.replay_steps.length} solved=${record.result.solved}</p>
    <p class="tiny">score=${record.result.final_score} final_diagnosis=${record.result.final_diagnosis ? record.result.final_diagnosis.root_cause_service || "submitted" : "none"}</p>
    ${record.replay_steps.slice(-4).map((step) => `<p class="tiny">step ${step.step_number}: ${step.action ? step.action.action_type : "reset"}</p>`).join("")}
  `;
  if (record.judge_summary?.length) {
    els.judgeOutput.className = "";
    els.judgeOutput.innerHTML = record.judge_summary.map((line) => `<p class="tiny">${line}</p>`).join("");
  } else {
    els.judgeOutput.className = "is-empty";
    els.judgeOutput.textContent = "Replay grading notes appear here.";
  }
  els.replaySteps.className = "obs-timeline";
  els.replaySteps.innerHTML = record.replay_steps.map((step) => `
    <article class="timeline-item">
      <h4>Replay Step ${step.step_number}</h4>
      <p>${step.action ? step.action.action_type : "reset"}</p>
      <p class="tiny">${step.observation.action_result || "initial observation"}</p>
      ${step.reward ? `<p class="tiny">reward=${step.reward.total} · breakdown=${Object.entries(step.reward.breakdown).filter(([, value]) => value !== 0).map(([key, value]) => `${key}=${value}`).join(" · ") || "none"}</p>` : ""}
    </article>
  `).join("");
}

function renderSessions(items) {
  if (!items.length) {
    els.sessionHistory.className = "is-empty";
    els.sessionHistory.textContent = "No saved sessions found.";
    return;
  }
  els.sessionHistory.className = "";
  els.sessionHistory.innerHTML = items.slice(0, 8).map((item) => `
    <p class="tiny">session=${item.session_id} scenario=${item.scenario_id} seed=${item.seed} score=${item.score} solved=${item.solved}</p>
  `).join("");
}

function renderBenchmarkHistory(items) {
  if (!items.length) {
    els.benchmarkHistoryOutput.className = "is-empty";
    els.benchmarkHistoryOutput.textContent = "No saved benchmark runs found.";
    return;
  }
  els.benchmarkHistoryOutput.className = "";
  els.benchmarkHistoryOutput.innerHTML = items.slice(0, 8).map((item) => `
    <p class="tiny">benchmark=${item.benchmark_id} provider=${item.provider} avg=${item.overall_average_score.toFixed(2)} solve_rate=${(item.overall_solve_rate * 100).toFixed(0)}% public=${item.public_scenario_count} holdout=${item.holdout_scenario_count}</p>
  `).join("");
}

function renderComparison(payload) {
  els.comparisonOutput.className = "";
  els.comparisonOutput.innerHTML = comparisonMarkup(payload);
}

function comparisonMarkup(payload) {
  const human = payload.human?.result || {};
  const scripted = payload.scripted?.summary || {};
  const selected = payload.selected?.summary || null;
  return `
    <p class="tiny">scenario=${escapeHtml(payload.scenario_id)} seed=${escapeHtml(payload.seed)}</p>
    <p class="tiny">human score=${escapeHtml(human.final_score ?? "n/a")} solved=${escapeHtml(human.solved ?? false)}</p>
    <p class="tiny">scripted score=${escapeHtml(scripted.score ?? "n/a")} solved=${escapeHtml(scripted.solved ?? false)}</p>
    ${selected ? `<p class="tiny">${escapeHtml(selected.mode)} score=${escapeHtml(selected.score ?? "n/a")} solved=${escapeHtml(selected.solved ?? false)}${selected.error ? ` error=${escapeHtml(selected.error)}` : ""}</p>` : `<p class="tiny">selected baseline not requested.</p>`}
    ${human.analytics ? `<p class="tiny">human ${analyticsLine(human.analytics)}</p>` : ""}
    ${scripted.analytics ? `<p class="tiny">scripted ${analyticsLine(scripted.analytics)}</p>` : ""}
    ${selected?.analytics ? `<p class="tiny">${selected.mode} ${analyticsLine(selected.analytics)}</p>` : ""}
  `;
}

function analyticsLine(analytics = {}) {
  return Object.entries(analytics).map(([key, value]) => `${key}=${Number(value).toFixed(2)}`).join(" · ");
}

function renderAnalyticsTiny(analytics = {}) {
  const line = analyticsLine(analytics);
  return line ? `<p class="tiny">${line}</p>` : "";
}

function renderSummary() {
  if (!state.currentResult) {
    els.graderOutput.className = "is-empty";
    els.graderOutput.textContent = "No session activity yet.";
    return;
  }
  const r = state.currentResult;
  els.graderOutput.className = "";
  els.graderOutput.innerHTML = `
    <div class="result-grid">
      <div class="result-stat"><span>Scenario</span><strong>${r.scenario_id}</strong></div>
      <div class="result-stat"><span>Score</span><strong>${r.final_score}</strong></div>
      <div class="result-stat"><span>Steps</span><strong>${r.steps_taken}</strong></div>
      <div class="result-stat"><span>Solved</span><strong>${r.solved ? "Yes" : "No"}</strong></div>
    </div>
  `;
}

function renderTimeline() {
  if (!state.timeline.length) {
    els.timeline.className = "obs-timeline is-empty";
    els.timeline.textContent = "No observations yet.";
    return;
  }
  els.timeline.className = "obs-timeline";
  els.timeline.innerHTML = state.timeline.map(entry => `
    <article class="timeline-item">
      <h4>Step ${entry.observation.step_number}</h4>
      <p>${entry.observation.action_result || "State sync"}</p>
      <p class="tiny">reward=${entry.reward ? entry.reward.total : 0} · done=${entry.observation.episode_done}</p>
      ${entry.observation.logs?.length ? `<p class="tiny">logs: ${entry.observation.logs.map(l => l.message).join(" | ")}</p>` : ""}
    </article>
  `).join("");
}

function renderSessionState() {
  els.sessionState.textContent = state.sessionId ? "Active" : "Idle";
  renderAiTaskContext();
}

function renderAiTaskContext() {
  const task = selectedTask();
  els.aiSelectedTask.textContent = task ? task.task_id : "random-on-start";
  els.aiSelectedTier.textContent = task ? task.tier : state.activeTier;
  els.aiSelectedSeed.textContent = String(currentSeedValue());
  els.aiCurrentSession.textContent = state.sessionId || "none";
}

function setView(view) {
  state.currentView = view;
  els.tasksView.classList.toggle("is-active", view === "tasks");
  els.sessionView.classList.toggle("is-active", view === "session");
  els.runtimeView.classList.toggle("is-active", view === "runtime");
  els.aiControlView.classList.toggle("is-active", view === "ai-control");
  els.viewTabs.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.view === view);
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function selectedAiProviderName() {
  if (els.aiProvider.value !== "custom") {
    return els.aiProvider.value;
  }
  return els.aiCustomProvider.value.trim().toLowerCase();
}

function syncAiProviderFields() {
  const isCustom = els.aiProvider.value === "custom";
  els.aiCustomProviderField.classList.toggle("is-visible", isCustom);
  if (!isCustom) {
    els.aiCustomProvider.value = "";
  }
}

function collectAiRuntimeConfig() {
  return {
    provider: selectedAiProviderName() || "scripted",
    model: els.aiModel.value.trim() || null,
    api_key: els.aiCredentialMode.value === "memory" ? null : (els.aiApiKey.value.trim() || null),
    base_url: els.aiBaseUrl.value.trim() || null,
  };
}

function validateAiRuntimeConfig() {
  const provider = selectedAiProviderName();
  if (!provider) {
    return "Custom provider name is required.";
  }
  if (provider !== "scripted") {
    if (!els.aiModel.value.trim()) {
      return "Model is required for AI providers.";
    }
    if (els.aiCredentialMode.value === "request" && !els.aiApiKey.value.trim()) {
      return "API key is required when using request-scoped credentials.";
    }
  }
  return null;
}

function renderAiSettingsStatus(message = null) {
  const lines = [];
  const provider = selectedAiProviderName() || "scripted";
  lines.push(`provider=${escapeHtml(provider)}`);
  lines.push(`model=${escapeHtml(els.aiModel.value.trim() || "unset")}`);
  lines.push(`base_url=${escapeHtml(els.aiBaseUrl.value.trim() || "default")}`);
  lines.push(`credentials=${escapeHtml(els.aiApiKey.value ? "loaded" : "empty")}`);
  lines.push(`persist=${escapeHtml(els.aiPersistMode.value)}`);
  lines.push(`mode=${escapeHtml(els.aiCredentialMode.value)}`);
  els.aiSettingsStatus.className = "alert-list";
  els.aiSettingsStatus.innerHTML = [
    ...(message ? [`<article class="alert-item">${escapeHtml(message)}</article>`] : []),
    `<article class="alert-item">${lines.join(" · ")}</article>`,
  ].join("");
}

function renderAiValidation(message = null, isError = false) {
  if (!message) {
    els.aiValidationOutput.className = "alert-list is-empty";
    els.aiValidationOutput.textContent = "Provider validation messages appear here.";
    return;
  }
  els.aiValidationOutput.className = "alert-list";
  els.aiValidationOutput.innerHTML = `<article class="alert-item">${escapeHtml(message)}</article>`;
  if (isError) {
    setStatus(message, "error");
  }
}

function appendAiHistory(line) {
  state.aiHistory.unshift(`${new Date().toLocaleTimeString()} · ${line}`);
  state.aiHistory = state.aiHistory.slice(0, 8);
  renderAiHistory();
}

function renderAiHistory() {
  if (!state.aiHistory.length) {
    els.aiRunHistory.className = "is-empty";
    els.aiRunHistory.textContent = "Saved runtime actions and recent AI runs appear here.";
    return;
  }
  els.aiRunHistory.className = "";
  els.aiRunHistory.innerHTML = state.aiHistory.map((line) => `<p class="tiny">${escapeHtml(line)}</p>`).join("");
}

function loadAiRuntimeSettings() {
  const raw = window.localStorage.getItem(AI_RUNTIME_STORAGE_KEY);
  if (!raw) {
    syncAiProviderFields();
    renderAiSettingsStatus("No saved AI runtime settings found.");
    return;
  }
  try {
    const saved = JSON.parse(raw);
    els.aiProvider.value = saved.provider_select || "scripted";
    els.aiCustomProvider.value = saved.custom_provider || "";
    els.aiModel.value = saved.model || "";
    els.aiApiKey.value = saved.api_key || "";
    els.aiBaseUrl.value = saved.base_url || "";
    els.aiPersistMode.value = saved.persist_mode || "save";
    els.aiCredentialMode.value = saved.credential_mode || "request";
    els.aiRunSeed.value = String(saved.run_seed ?? currentSeedValue());
    els.aiBenchmarkSeeds.value = String(saved.benchmark_seeds ?? 1);
    syncAiProviderFields();
    renderAiSettingsStatus("Restored AI runtime settings from browser storage.");
  } catch (_error) {
    syncAiProviderFields();
    renderAiSettingsStatus("Saved AI runtime settings were unreadable and were ignored.");
  }
}

function saveAiRuntimeSettings() {
  const persistMode = els.aiPersistMode.value;
  const payload = {
    provider_select: els.aiProvider.value,
    custom_provider: els.aiCustomProvider.value.trim(),
    model: els.aiModel.value.trim(),
    api_key: els.aiCredentialMode.value === "request" && persistMode === "save" ? els.aiApiKey.value.trim() : "",
    base_url: els.aiBaseUrl.value.trim(),
    persist_mode: persistMode,
    credential_mode: els.aiCredentialMode.value,
    run_seed: Number(els.aiRunSeed.value || 0),
    benchmark_seeds: Number(els.aiBenchmarkSeeds.value || 1),
  };
  window.localStorage.setItem(AI_RUNTIME_STORAGE_KEY, JSON.stringify(payload));
  renderAiSettingsStatus("Saved AI runtime settings to browser storage.");
  appendAiHistory(`saved runtime settings for ${selectedAiProviderName() || "scripted"}`);
}

function clearAiRuntimeSettings() {
  window.localStorage.removeItem(AI_RUNTIME_STORAGE_KEY);
  els.aiProvider.value = "scripted";
  els.aiCustomProvider.value = "";
  els.aiModel.value = "";
  els.aiApiKey.value = "";
  els.aiBaseUrl.value = "";
  els.aiPersistMode.value = "save";
  els.aiCredentialMode.value = "request";
  els.aiRunSeed.value = String(currentSeedValue());
  els.aiBenchmarkSeeds.value = "1";
  syncAiProviderFields();
  renderAiSettingsStatus("Cleared saved AI runtime settings.");
  renderAiValidation();
  appendAiHistory("cleared saved runtime settings");
}

function syncAiWithSelectedTask() {
  els.aiRunSeed.value = String(currentSeedValue());
  renderAiTaskContext();
  renderAiSettingsStatus("Loaded the current task and session context into the AI page.");
}

function renderAiBaseline(result) {
  els.aiBaselineOutput.className = "";
  els.aiBaselineOutput.innerHTML = baselineMarkup(result);
}

function renderAiBenchmark(report) {
  els.aiBenchmarkOutput.className = "";
  els.aiBenchmarkOutput.innerHTML = benchmarkMarkup(report);
}

function renderAiCompare(payload) {
  const human = payload.human?.result || {};
  const selected = payload.selected?.summary || {};
  els.aiCompareOutput.className = "";
  els.aiCompareOutput.innerHTML = `
    <p class="tiny">scenario=${escapeHtml(payload.scenario_id)} seed=${escapeHtml(payload.seed)} session=${escapeHtml(payload.session_id)}</p>
    <p class="tiny">human score=${escapeHtml(human.final_score ?? "n/a")} solved=${escapeHtml(human.solved ?? false)}</p>
    <p class="tiny">${escapeHtml(selected.mode ?? "selected")} score=${escapeHtml(selected.score ?? "n/a")} solved=${escapeHtml(selected.solved ?? false)}${selected.error ? ` error=${escapeHtml(selected.error)}` : ""}</p>
    ${human.analytics ? `<p class="tiny">human ${analyticsLine(human.analytics)}</p>` : ""}
    ${selected.analytics ? `<p class="tiny">${escapeHtml(selected.mode)} ${analyticsLine(selected.analytics)}</p>` : ""}
  `;
}

async function runAiBaseline() {
  const task = ensureTaskSelection({ randomize: true });
  if (!task) return;
  const validationError = validateAiRuntimeConfig();
  if (validationError) {
    renderAiValidation(validationError, true);
    return;
  }
  setStatus("Running AI baseline…", "working");
  renderAiValidation("Running AI baseline with request-scoped provider settings.");
  try {
    const payload = await requestJson("/runtime/baseline", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tier: task.tier,
        task_id: task.task_id,
        seed: Number(els.aiRunSeed.value || 0),
        runtime: collectAiRuntimeConfig(),
      }),
    });
    renderAiBaseline(payload);
    renderAiValidation(`AI baseline completed for ${task.task_id}.`);
    appendAiHistory(`baseline ${selectedAiProviderName()} on ${task.task_id} score=${payload.score}`);
    if (els.aiPersistMode.value === "save") saveAiRuntimeSettings();
    setStatus("Ready");
  } catch (error) {
    reportError("AI baseline failed", error);
    renderAiValidation(error.message || "AI baseline failed.", true);
  }
}

async function runAiBenchmark() {
  const validationError = validateAiRuntimeConfig();
  if (validationError) {
    renderAiValidation(validationError, true);
    return;
  }
  setStatus("Running AI benchmark…", "working");
  renderAiValidation("Running AI benchmark with request-scoped provider settings.");
  try {
    const payload = await requestJson("/runtime/benchmark", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        seeds_per_scenario: Math.max(1, Number(els.aiBenchmarkSeeds.value || 1)),
        runtime: collectAiRuntimeConfig(),
      }),
    });
    renderAiBenchmark(payload);
    renderAiValidation(`AI benchmark completed with ${payload.scenario_count} scenarios.`);
    appendAiHistory(`benchmark ${selectedAiProviderName()} avg=${payload.overall_average_score.toFixed(2)}`);
    if (els.aiPersistMode.value === "save") saveAiRuntimeSettings();
    setStatus("Ready");
  } catch (error) {
    reportError("AI benchmark failed", error);
    renderAiValidation(error.message || "AI benchmark failed.", true);
  }
}

async function runAiCompare() {
  if (!state.sessionId) {
    renderAiValidation("Start or load a human session before running AI comparison.", true);
    return;
  }
  const validationError = validateAiRuntimeConfig();
  if (validationError) {
    renderAiValidation(validationError, true);
    return;
  }
  setStatus("Running AI comparison…", "working");
  renderAiValidation("Comparing the configured AI runtime against the active human session.");
  try {
    const payload = await requestJson("/runtime/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: state.sessionId,
        runtime: collectAiRuntimeConfig(),
      }),
    });
    renderAiCompare(payload);
    renderAiValidation(`AI comparison completed for session ${state.sessionId}.`);
    appendAiHistory(`compare ${selectedAiProviderName()} vs human session ${state.sessionId}`);
    if (els.aiPersistMode.value === "save") saveAiRuntimeSettings();
    setStatus("Ready");
  } catch (error) {
    reportError("AI comparison failed", error);
    renderAiValidation(error.message || "AI comparison failed.", true);
  }
}

function collectAction() {
  const payload = { action_type: els.actionType.value };
  const raw = {
    service: els.service.value.trim(),
    lines: els.lines.value.trim(),
    window_seconds: els.windowSeconds.value.trim(),
    target_version: els.targetVersion.value.trim(),
    replicas: els.replicas.value.trim(),
    root_cause_service: els.rootCauseService.value.trim(),
    root_cause_category: els.rootCauseCategory.value.trim(),
    fix_description: els.fixDescription.value.trim(),
  };
  Object.entries(raw).forEach(([k, v]) => {
    if (!v) return;
    payload[k] = ["lines", "window_seconds", "replicas"].includes(k) ? Number(v) : v;
  });
  return payload;
}

async function loadTasks() {
  setStatus("Loading…", "working");
  try {
    state.tasks = await requestJson("/tasks");
    renderTasks();
    renderSelectedTask();
    setStatus("Ready");
  } catch (error) { reportError("Load failed", error); }
}

function setActiveTier(nextTier) {
  if (state.activeTier === nextTier) return;
  state.activeTier = nextTier;
  state.selectedTaskId = null;
  clearSessionForTaskChange();
  renderTasks();
  renderSelectedTask();
}

async function startSession() {
  const task = ensureTaskSelection({ randomize: true });
  if (!task) return;
  setStatus("Starting…", "working");
  try {
    const seed = Number(els.sessionSeed.value || 0);
    const p = await requestJson("/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tier: task.tier, task_id: task.task_id, seed }),
    });
    state.sessionId = p.session_id;
    state.currentObservation = p.observation;
    state.currentResult = { steps_taken: 0, final_score: 0, solved: false, scenario_id: p.task_id };
    state.timeline = [{ observation: p.observation, reward: null }];
    renderSessionState(); renderObservation(); renderSummary(); renderTimeline();
    setStatus("Session live");
  } catch (error) { reportError("Start failed", error); }
}

async function syncState() {
  if (!state.sessionId) return;
  setStatus("Syncing…", "working");
  try {
    const p = await requestJson(`/state/${state.sessionId}`);
    state.currentObservation = p.observation;
    state.currentResult = p.result;
    renderObservation(); renderSummary();
    setStatus("Ready");
  } catch (error) { reportError("Sync failed", error); }
}

async function sendAction(action) {
  if (!state.sessionId) await startSession();
  if (!state.sessionId) throw new Error("No active session");
  const p = await requestJson("/step", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: state.sessionId, action }),
  });
  state.currentObservation = p.observation;
  state.currentResult = p.result;
  state.timeline.push({ observation: p.observation, reward: p.reward });
  renderObservation(); renderSummary(); renderTimeline();
}

async function runSingleAction() {
  setStatus("Running…", "working");
  try { await sendAction(collectAction()); setStatus("Ready"); }
  catch (error) { reportError("Step failed", error); }
}

async function runQueue() {
  setStatus("Running queue…", "working");
  try {
    for (const action of state.queuedActions) {
      await sendAction(action);
      if (state.currentObservation?.episode_done) break;
    }
    setStatus("Ready");
  } catch (error) { reportError("Queue failed", error); }
}

async function runBaseline() {
  const task = ensureTaskSelection({ randomize: true });
  if (!task) return;
  setStatus("Running baseline…", "working");
  try {
    const seed = Number(els.sessionSeed.value || 0);
    const provider = els.baselineProvider.value;
    const model = encodeURIComponent(els.baselineModel.value.trim());
    renderBaseline(await requestJson(`/baseline?tier=${task.tier}&task_id=${task.task_id}&seed=${seed}&provider=${provider}${model ? `&model=${model}` : ""}`));
    setStatus("Ready");
  } catch (error) { reportError("Baseline failed", error); }
}

async function runBenchmark() {
  setStatus("Running benchmark…", "working");
  try {
    const seeds = Math.max(1, Number(els.benchmarkSeeds.value || 1));
    const provider = els.benchmarkProvider.value;
    const model = encodeURIComponent(els.benchmarkModel.value.trim());
    renderBenchmark(await requestJson(`/benchmark?seeds_per_scenario=${seeds}&provider=${provider}${model ? `&model=${model}` : ""}`));
    setStatus("Ready");
  } catch (error) {
    reportError("Benchmark failed", error);
  }
}

async function exportReplay() {
  if (!state.sessionId) {
    setStatus("No active session", "error");
    return;
  }
  setStatus("Loading replay…", "working");
  try {
    renderReplay(await requestJson(`/replay/${state.sessionId}`));
    setStatus("Ready");
  } catch (error) {
    reportError("Replay failed", error);
  }
}

async function loadSessions() {
  setStatus("Loading sessions…", "working");
  try {
    renderSessions(await requestJson("/sessions"));
    setStatus("Ready");
  } catch (error) {
    reportError("Sessions failed", error);
  }
}

async function loadBenchmarkHistory() {
  setStatus("Loading benchmark history…", "working");
  try {
    renderBenchmarkHistory(await requestJson("/benchmark/history"));
    setStatus("Ready");
  } catch (error) {
    reportError("Benchmark history failed", error);
  }
}

async function loadComparison() {
  if (!state.sessionId) {
    setStatus("No active session", "error");
    return;
  }
  setStatus("Loading comparison…", "working");
  try {
    const provider = els.baselineProvider.value;
    const model = encodeURIComponent(els.baselineModel.value.trim());
    renderComparison(await requestJson(`/compare/${state.sessionId}?provider=${provider}${model ? `&model=${model}` : ""}`));
    setStatus("Ready");
  } catch (error) {
    reportError("Comparison failed", error);
  }
}

window.addEventListener("error", (event) => {
  reportError("Frontend error", event.error || event.message);
});

document.getElementById("refresh-tasks").addEventListener("click", loadTasks);
document.getElementById("start-session").addEventListener("click", startSession);
document.getElementById("refresh-state").addEventListener("click", syncState);
document.getElementById("run-baseline").addEventListener("click", runBaseline);
document.getElementById("run-benchmark").addEventListener("click", runBenchmark);
document.getElementById("export-replay").addEventListener("click", exportReplay);
document.getElementById("load-sessions").addEventListener("click", loadSessions);
document.getElementById("load-benchmark-history").addEventListener("click", loadBenchmarkHistory);
document.getElementById("load-comparison").addEventListener("click", loadComparison);
document.getElementById("queue-action").addEventListener("click", () => { state.queuedActions.push(collectAction()); renderQueue(); });
document.getElementById("run-single").addEventListener("click", runSingleAction);
document.getElementById("run-queued").addEventListener("click", runQueue);
document.getElementById("clear-actions").addEventListener("click", () => { state.queuedActions = []; renderQueue(); });
document.querySelectorAll(".tier-mode-button").forEach((button) => {
  button.addEventListener("click", () => setActiveTier(button.dataset.tier));
});
els.viewTabs.forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.view));
});
document.getElementById("ai-load-selected-task").addEventListener("click", syncAiWithSelectedTask);
document.getElementById("ai-save-settings").addEventListener("click", saveAiRuntimeSettings);
document.getElementById("ai-clear-settings").addEventListener("click", clearAiRuntimeSettings);
document.getElementById("ai-run-baseline").addEventListener("click", runAiBaseline);
document.getElementById("ai-run-benchmark").addEventListener("click", runAiBenchmark);
document.getElementById("ai-run-compare").addEventListener("click", runAiCompare);
els.aiProvider.addEventListener("change", () => {
  syncAiProviderFields();
  renderAiSettingsStatus("Updated provider selection.");
});

populateActionTypes();
syncAiProviderFields();
renderQueue(); renderObservation(); renderSummary(); renderTimeline(); renderSessionState(); renderAiHistory();
loadAiRuntimeSettings();
loadTasks();
