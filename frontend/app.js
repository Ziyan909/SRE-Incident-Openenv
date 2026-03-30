const state = {
  tasks: [],
  activeTier: "easy",
  selectedTaskId: null,
  queuedActions: [],
  sessionId: null,
  currentObservation: null,
  currentResult: null,
  timeline: [],
};

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
  els.baselineOutput.innerHTML = `
    <div class="result-grid">
      <div class="result-stat"><span>Task</span><strong>${result.task_id}</strong></div>
      <div class="result-stat"><span>Mode</span><strong>${result.mode}</strong></div>
      <div class="result-stat"><span>Score</span><strong>${result.score}</strong></div>
      <div class="result-stat"><span>Steps</span><strong>${result.steps_taken}</strong></div>
    </div>
    <p class="tiny">solved=${result.solved} · seed=${result.seed}${result.model ? ` · model=${result.model}` : ""}</p>
    ${result.error ? `<p class="tiny">error=${result.error}</p>` : ""}
    ${renderAnalyticsTiny(result.analytics)}
  `;
}

function renderBenchmark(report) {
  els.benchmarkOutput.className = "";
  els.benchmarkOutput.innerHTML = `
    <div class="result-grid">
      <div class="result-stat"><span>Scenarios</span><strong>${report.scenario_count}</strong></div>
      <div class="result-stat"><span>Templates</span><strong>${report.template_count}</strong></div>
      <div class="result-stat"><span>Avg Score</span><strong>${report.overall_average_score.toFixed(2)}</strong></div>
      <div class="result-stat"><span>Solve Rate</span><strong>${(report.overall_solve_rate * 100).toFixed(0)}%</strong></div>
      <div class="result-stat"><span>Mode</span><strong>${report.mode}</strong></div>
    </div>
    <p class="tiny">public=${report.public_scenario_count} holdout=${report.holdout_scenario_count} generated_at=${report.generated_at}</p>
    ${report.tier_summaries.map((item) => `<p class="tiny">${item.tier}: avg=${item.average_score.toFixed(2)} solve_rate=${(item.solve_rate * 100).toFixed(0)}% steps=${item.average_steps.toFixed(1)}</p>`).join("")}
    ${renderAnalyticsTiny(report.analytics_summary)}
    <p class="tiny">families: ${Object.entries(report.family_breakdown).map(([name, count]) => `${name}=${count}`).join(" · ")}</p>
    ${report.hardest_scenarios.map((item) => `<p class="tiny">hard case: ${item.task_id} score=${item.score.toFixed(2)} solved=${item.solved}</p>`).join("")}
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
  const human = payload.human?.result || {};
  const scripted = payload.scripted?.summary || {};
  const selected = payload.selected?.summary || null;
  els.comparisonOutput.className = "";
  els.comparisonOutput.innerHTML = `
    <p class="tiny">scenario=${payload.scenario_id} seed=${payload.seed}</p>
    <p class="tiny">human score=${human.final_score ?? "n/a"} solved=${human.solved ?? false}</p>
    <p class="tiny">scripted score=${scripted.score ?? "n/a"} solved=${scripted.solved ?? false}</p>
    ${selected ? `<p class="tiny">${selected.mode} score=${selected.score ?? "n/a"} solved=${selected.solved ?? false}${selected.error ? ` error=${selected.error}` : ""}</p>` : `<p class="tiny">selected baseline not requested.</p>`}
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

populateActionTypes();
renderQueue(); renderObservation(); renderSummary(); renderTimeline(); renderSessionState();
loadTasks();
