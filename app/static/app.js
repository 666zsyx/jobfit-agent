const state = {
  token: localStorage.getItem("jobfit_token") || "",
  currentUser: null,
  jobs: [],
  resumes: [],
  tasks: [],
  selectedJobId: null,
  selectedResumeId: null,
  selectedResumeVersionId: null,
  selectedTaskId: null,
  selectedTaskStatus: null,
  pendingConfirmation: null,
  streaming: false,
  streamController: null,
  activeStreamTaskId: null,
};

const $ = (id) => document.getElementById(id);

function showToast(message, type = "") {
  const toast = $("toast");
  toast.textContent = message;
  toast.className = `toast${type ? ` ${type}` : ""}`;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    toast.className = "toast hidden";
  }, 4200);
}

function setConnectionStatus(text, kind = "") {
  const element = $("connection-status");
  element.textContent = text;
  element.dataset.kind = kind;
}

function authHeaders(headers = {}) {
  const result = new Headers(headers);
  if (state.token) {
    result.set("Authorization", `Bearer ${state.token}`);
  }
  return result;
}

async function api(path, options = {}) {
  const headers = authHeaders(options.headers || {});
  const body = options.body;
  if (body && !(body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, { ...options, headers });
  let payload = null;
  try {
    payload = await response.json();
  } catch (_) {
    payload = null;
  }
  if (!response.ok) {
    if (response.status === 401) {
      logout(false, "登录已过期，请重新登录");
    }
    throw new Error(payload?.message || `请求失败：HTTP ${response.status}`);
  }
  return payload?.data ?? payload;
}

function formatDate(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function formatNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString("zh-CN") : "-";
}

function formatDuration(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  if (number < 1000) return `${Math.round(number)} ms`;
  return `${(number / 1000).toFixed(2)} s`;
}

function statusClass(status) {
  if (status === "completed") return "success";
  if (status === "failed" || status === "cancelled") return "failed";
  if (status === "waiting_confirmation" || status === "interrupted") return "warning";
  return "";
}

function createItem(title, meta, selected, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `item${selected ? " selected" : ""}`;
  button.addEventListener("click", onClick);

  const titleElement = document.createElement("div");
  titleElement.className = "item-title";
  titleElement.textContent = title;

  const metaElement = document.createElement("div");
  metaElement.className = "item-meta";
  metaElement.textContent = meta;

  button.append(titleElement, metaElement);
  return button;
}

function setEmpty(container, text) {
  container.replaceChildren();
  container.classList.add("empty");
  container.textContent = text;
}

function updateSelectionSummary() {
  const resume = state.resumes.find((item) => item.resume_id === state.selectedResumeId);
  const job = state.jobs.find((item) => item.job_id === state.selectedJobId);
  const resumeText = resume
    ? `${resume.title} v${state.selectedResumeVersionId || "-"}`
    : "未选择简历";
  const jobText = job
    ? `${job.title || "未命名岗位"}${job.company_name ? ` @ ${job.company_name}` : ""}`
    : "未选择岗位";
  $("selection-summary").textContent = `${resumeText} · ${jobText}`;
}

function renderJobs() {
  const container = $("job-list");
  $("job-count").textContent = String(state.jobs.length);
  if (!state.jobs.length) {
    setEmpty(container, "暂无岗位");
    return;
  }
  container.classList.remove("empty");
  container.replaceChildren(
    ...state.jobs.map((job) =>
      createItem(
        job.title || `岗位 #${job.job_id}`,
        `${job.company_name || "公司未填写"} · ${job.job_description_preview || ""}`,
        job.job_id === state.selectedJobId,
        () => selectJob(job.job_id),
      ),
    ),
  );
}

function renderResumes() {
  const container = $("resume-list");
  $("resume-count").textContent = String(state.resumes.length);
  if (!state.resumes.length) {
    setEmpty(container, "暂无简历");
    return;
  }
  container.classList.remove("empty");
  container.replaceChildren(
    ...state.resumes.map((resume) =>
      createItem(
        resume.title,
        `最新 v${resume.latest_version_no} · ${resume.latest_source_type || "-"} · ${resume.latest_char_count} 字`,
        resume.resume_id === state.selectedResumeId,
        () => loadResumeDetail(resume.resume_id),
      ),
    ),
  );
}

function renderResumeVersions(versions) {
  const container = $("resume-version-list");
  $("resume-versions").classList.remove("hidden");
  container.replaceChildren(
    ...versions.map((version) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `chip${version.resume_version_id === state.selectedResumeVersionId ? " selected" : ""}`;
      button.textContent = `v${version.version_no} · ${version.source_type} · ${version.char_count}字`;
      button.addEventListener("click", () => selectResumeVersion(version.resume_version_id));
      return button;
    }),
  );
}

function renderTasks() {
  const container = $("task-list");
  $("task-count").textContent = String(state.tasks.length);
  if (!state.tasks.length) {
    setEmpty(container, "暂无任务");
    return;
  }
  container.classList.remove("empty");
  container.replaceChildren(
    ...state.tasks.map((task) => {
      const cost = task.metrics_json?.estimated_cost;
      const currency = task.metrics_json?.currency || "";
      const reportText = task.report_id ? `报告 v${task.report_version}` : "无报告";
      const costText = cost != null ? `${cost} ${currency}` : "成本 -";
      return createItem(
        task.job_title || `任务 #${task.task_id}`,
        `${task.status} · ${reportText} · ${costText} · ${formatDate(task.created_at)}`,
        task.task_id === state.selectedTaskId,
        () => selectTask(task.task_id),
      );
    }),
  );
}

function renderReport(report) {
  $("report-meta").textContent = `报告 #${report.report_id} · 生成于 ${formatDate(report.created_at)}`;
  $("report-version").textContent = `v${report.version_no}`;
  $("report-summary").classList.remove("empty");
  $("report-summary").textContent = report.summary || "报告没有摘要";
  $("report-json").textContent = JSON.stringify(report.result_json, null, 2);

  const chunkIds = new Set();
  collectChunkIds(report.result_json, chunkIds);
  const container = $("citation-list");
  if (!chunkIds.size) {
    container.replaceChildren();
    container.classList.add("empty");
    container.textContent = "暂无引用";
    $("metric-citations").textContent = "0";
  } else {
    container.classList.remove("empty");
    container.replaceChildren(
      ...[...chunkIds].map((chunkId) => {
        const chip = document.createElement("span");
        chip.className = "chip";
        chip.textContent = `chunk ${chunkId}`;
        return chip;
      }),
    );
    $("metric-citations").textContent = String(chunkIds.size);
  }
}

function clearReport() {
  $("report-meta").textContent = "等待任务完成";
  $("report-version").textContent = "-";
  $("report-summary").classList.add("empty");
  $("report-summary").textContent = "暂无报告";
  $("report-json").textContent = "暂无报告";
  $("citation-list").replaceChildren();
  $("citation-list").classList.add("empty");
  $("citation-list").textContent = "暂无引用";
  $("metric-tokens").textContent = "-";
  $("metric-cost").textContent = "-";
  $("metric-citations").textContent = "-";
  $("metric-duration").textContent = "-";
}

function collectChunkIds(value, output) {
  if (Array.isArray(value)) {
    value.forEach((item) => collectChunkIds(item, output));
    return;
  }
  if (!value || typeof value !== "object") return;
  for (const [key, child] of Object.entries(value)) {
    if ((key === "chunk_id" || key === "chunkId") && child != null) {
      output.add(child);
    } else {
      collectChunkIds(child, output);
    }
  }
}

function applyTaskMetrics(task, fallbackUsage = null) {
  const metrics = task?.metrics_json || {};
  const usage = metrics.usage || fallbackUsage || {};
  if (usage.total_tokens != null) {
    $("metric-tokens").textContent = formatNumber(usage.total_tokens);
  }
  if (metrics.estimated_cost != null) {
    $("metric-cost").textContent = `${metrics.estimated_cost} ${metrics.currency || ""}`.trim();
  }
  if (metrics.total_ms != null) {
    $("metric-duration").textContent = formatDuration(metrics.total_ms);
  }
}

function updateTaskControls(task = null) {
  const status = task?.status || "idle";
  const badge = $("task-state");
  badge.textContent = status;
  badge.className = `badge ${statusClass(status)}`.trim();

  const currentStep = Number(task?.current_step || 0);
  const maxSteps = Number(task?.max_steps || 8);
  $("progress-step").textContent = `step ${currentStep}/${maxSteps}`;
  $("progress-node").textContent = task?.current_node || status;
  $("progress-bar").style.width = `${Math.min((currentStep / Math.max(maxSteps, 1)) * 100, 100)}%`;
  $("resume-interrupted").disabled = !task || !["interrupted", "waiting_confirmation"].includes(status);
}

async function loadJobs() {
  state.jobs = (await api("/api/jobs")) || [];
  if (!state.jobs.some((item) => item.job_id === state.selectedJobId)) {
    state.selectedJobId = state.jobs[0]?.job_id || null;
  }
  renderJobs();
  updateSelectionSummary();
}

async function loadResumes() {
  state.resumes = (await api("/api/resumes")) || [];
  if (!state.resumes.some((item) => item.resume_id === state.selectedResumeId)) {
    state.selectedResumeId = state.resumes[0]?.resume_id || null;
    state.selectedResumeVersionId = null;
  }
  renderResumes();
  if (state.selectedResumeId) {
    await loadResumeDetail(state.selectedResumeId, false);
  } else {
    $("resume-versions").classList.add("hidden");
  }
  updateSelectionSummary();
}

async function loadTasks() {
  state.tasks = (await api("/api/agent/tasks")) || [];
  if (!state.tasks.some((item) => item.task_id === state.selectedTaskId)) {
    state.selectedTaskId = null;
    state.selectedTaskStatus = null;
  }
  renderTasks();
}

function selectJob(jobId) {
  state.selectedJobId = jobId;
  renderJobs();
  updateSelectionSummary();
}

function selectResumeVersion(versionId) {
  state.selectedResumeVersionId = versionId;
  const resume = state.resumes.find((item) => item.resume_id === state.selectedResumeId);
  if (resume) {
    // 重新渲染当前版本选择状态。
    loadResumeDetail(resume.resume_id, false).catch((error) => showToast(error.message, "error"));
  }
  updateSelectionSummary();
}

async function loadResumeDetail(resumeId, chooseLatest = true) {
  const detail = await api(`/api/resumes/${resumeId}`);
  state.selectedResumeId = resumeId;
  if (chooseLatest || !detail.versions.some((item) => item.resume_version_id === state.selectedResumeVersionId)) {
    const latest = [...detail.versions].sort((a, b) => b.version_no - a.version_no)[0];
    state.selectedResumeVersionId = latest?.resume_version_id || null;
  }
  renderResumes();
  renderResumeVersions(detail.versions || []);
  updateSelectionSummary();
}

function showLoggedIn() {
  document.body.classList.remove("logged-out");
  const user = state.currentUser || { username: "当前用户", role: "user" };
  $("user-display").textContent = `${user.username} · ${user.role}`;
  $("logout-button").classList.remove("hidden");
  setConnectionStatus("已登录，JWT 有效期 24 小时", "success");
}

function showLoggedOut(message = "未登录") {
  document.body.classList.add("logged-out");
  $("user-display").textContent = "未登录";
  $("logout-button").classList.add("hidden");
  setConnectionStatus(message, message === "未登录" ? "" : "error");
}

function clearWorkspace() {
  state.currentUser = null;
  state.jobs = [];
  state.resumes = [];
  state.tasks = [];
  state.selectedJobId = null;
  state.selectedResumeId = null;
  state.selectedResumeVersionId = null;
  state.selectedTaskId = null;
  state.selectedTaskStatus = null;
  state.pendingConfirmation = null;
  renderJobs();
  renderResumes();
  renderTasks();
  $("resume-versions").classList.add("hidden");
  clearReport();
  updateTaskControls(null);
  $("event-log").textContent = "执行事件将显示在这里。";
}

async function login() {
  const username = $("username-input").value.trim();
  const password = $("password-input").value;
  if (!username || !password) {
    showLoggedOut("请输入用户名和密码");
    return;
  }

  const button = $("login-button");
  button.disabled = true;
  button.textContent = "登录中...";
  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(payload?.message || "登录失败");
    }
    state.token = payload.data.access_token;
    state.currentUser = payload.data.user;
    localStorage.setItem("jobfit_token", state.token);
    $("password-input").value = "";
    showLoggedIn();
    try {
      await loadAll();
      showToast("登录成功");
    } catch (error) {
      showToast(`登录成功，但数据加载失败：${error.message}`, "error");
    }
  } catch (error) {
    state.token = "";
    localStorage.removeItem("jobfit_token");
    clearWorkspace();
    showLoggedOut(error.message);
    showToast(error.message, "error");
  } finally {
    button.disabled = false;
    button.textContent = "登录";
  }
}

async function restoreSession() {
  if (!state.token) {
    showLoggedOut();
    return;
  }
  try {
    state.currentUser = await api("/api/auth/me");
    showLoggedIn();
    await loadAll();
  } catch (error) {
    if (!state.token) {
      return;
    }
    showLoggedIn();
    setConnectionStatus(`已登录，但数据加载失败：${error.message}`, "error");
    showToast(error.message, "error");
  }
}

function logout(showMessage = true, message = "已退出") {
  if (state.streamController) {
    state.streamController.abort();
    state.streamController = null;
  }
  state.streaming = false;
  state.activeStreamTaskId = null;
  state.token = "";
  localStorage.removeItem("jobfit_token");
  clearWorkspace();
  showLoggedOut(message);
  if (showMessage && message === "已退出") {
    showToast("已退出登录");
  }
}

async function loadAll() {
  await Promise.all([loadJobs(), loadResumes(), loadTasks()]);
}

async function uploadResume() {
  const file = $("resume-file").files[0];
  if (!file) {
    showToast("请先选择简历文件", "error");
    return;
  }
  const form = new FormData();
  form.append("file", file);
  const title = $("resume-title").value.trim();
  if (title) form.append("title", title);
  form.append("extract_sections", $("resume-extract").checked ? "true" : "false");

  const button = $("upload-resume");
  button.disabled = true;
  button.textContent = "解析中...";
  try {
    const result = await api("/api/resumes/upload", { method: "POST", body: form });
    $("resume-title").value = "";
    $("resume-file").value = "";
    await loadResumes();
    await loadResumeDetail(result.resume_id, false);
    state.selectedResumeVersionId = result.resume_version_id;
    await loadResumeDetail(result.resume_id, false);
    showToast(`简历已保存，解析状态：${result.extraction_status}`);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    button.disabled = false;
    button.textContent = "上传并解析";
  }
}

async function createJob() {
  const description = $("job-description").value.trim();
  if (!description) {
    showToast("请粘贴岗位 JD", "error");
    return;
  }
  const button = $("create-job");
  button.disabled = true;
  button.textContent = "保存中...";
  try {
    const job = await api("/api/jobs", {
      method: "POST",
      body: JSON.stringify({
        job_description: description,
        title: $("job-title").value.trim() || null,
        company_name: $("job-company").value.trim() || null,
      }),
    });
    $("job-title").value = "";
    $("job-company").value = "";
    $("job-description").value = "";
    await loadJobs();
    selectJob(job.job_id);
    showToast("岗位已保存");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    button.disabled = false;
    button.textContent = "保存岗位";
  }
}

async function createAndRunTask() {
  if (!state.selectedJobId || !state.selectedResumeVersionId) {
    showToast("请先选择简历版本和岗位", "error");
    return;
  }
  const button = $("start-analysis");
  button.disabled = true;
  button.textContent = "创建任务...";
  try {
    const task = await api("/api/agent/tasks", {
      method: "POST",
      body: JSON.stringify({
        job_id: state.selectedJobId,
        resume_version_id: state.selectedResumeVersionId,
      }),
    });
    state.selectedTaskId = task.task_id;
    state.selectedTaskStatus = task;
    await loadTasks();
    updateTaskControls(task);
    await streamGraphTask(task.task_id);
  } catch (error) {
    showToast(error.message, "error");
    updateTaskControls(state.selectedTaskStatus);
  } finally {
    button.disabled = false;
    button.textContent = "开始分析";
  }
}

function appendEvent(eventName, payload) {
  const log = $("event-log");
  const node = payload?.data?.node || payload?.current_node || payload?.data?.status || "";
  const content = payload?.content ? ` ${payload.content}` : "";
  const prefix = payload?.step ? `[step ${payload.step}] ` : "";
  const line = `${new Date().toLocaleTimeString()} ${eventName} ${node}${prefix}${content}`.trim();
  log.textContent = `${log.textContent === "执行事件将显示在这里。" ? "" : `${log.textContent}\n`}${line}`;
  log.scrollTop = log.scrollHeight;
}

async function handleAgentEvent(eventName, payload, taskId) {
  appendEvent(eventName, payload);
  const step = Number(payload?.step || payload?.data?.step || 0);
  const maxSteps = Number(state.selectedTaskStatus?.max_steps || 8);
  if (step > 0) {
    $("progress-step").textContent = `step ${step}/${maxSteps}`;
    $("progress-bar").style.width = `${Math.min((step / Math.max(maxSteps, 1)) * 100, 100)}%`;
  }
  if (eventName === "node_started" && payload?.data?.node) {
    $("progress-node").textContent = payload.data.node;
  }
  if (eventName === "waiting_confirmation") {
    $("progress-node").textContent = "等待人工确认";
    $("progress-bar").style.width = "85%";
    await loadConfirmation(taskId);
  }
  if (eventName === "task_completed") {
    $("progress-node").textContent = "completed";
    $("progress-bar").style.width = "100%";
    applyTaskMetrics(null, payload?.data?.usage);
    await loadTasks();
    await loadReport(taskId);
  }
  if (eventName === "task_failed" || eventName === "task_interrupted") {
    $("progress-node").textContent = eventName === "task_failed" ? "failed" : "interrupted";
    await loadTasks();
  }
}

function parseSseFrame(frame) {
  const dataLines = [];
  let eventName = "message";
  for (const rawLine of frame.split("\n")) {
    const line = rawLine.replace(/\r$/, "");
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return null;
  const rawData = dataLines.join("\n");
  if (rawData === "[DONE]") return { eventName: "done", payload: null };
  try {
    return { eventName, payload: JSON.parse(rawData) };
  } catch (_) {
    return { eventName, payload: { content: rawData } };
  }
}

async function streamGraphTask(taskId) {
  if (state.streamController) {
    state.streamController.abort();
  }
  const controller = new AbortController();
  state.streamController = controller;
  state.streaming = true;
  state.activeStreamTaskId = taskId;
  state.selectedTaskId = taskId;
  clearReport();
  $("event-log").textContent = "执行事件将显示在这里。";
  updateTaskControls({ ...(state.selectedTaskStatus || {}), task_id: taskId, status: "running" });

  try {
    const response = await fetch(`/api/agent/tasks/${taskId}/graph/stream`, {
      headers: authHeaders({ Accept: "text/event-stream" }),
      signal: controller.signal,
    });
    if (!response.ok) {
      let payload = null;
      try { payload = await response.json(); } catch (_) {}
      if (response.status === 401) {
        logout(false, "登录已过期，请重新登录");
      }
      throw new Error(payload?.message || `SSE 请求失败：HTTP ${response.status}`);
    }
    if (!response.body) throw new Error("浏览器不支持流式响应");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const parsed = parseSseFrame(frame);
        if (parsed?.eventName === "done") break;
        if (parsed && parsed.eventName !== "heartbeat") {
          if (
            state.activeStreamTaskId === taskId
            && state.streamController === controller
          ) {
            await handleAgentEvent(
              parsed.eventName,
              parsed.payload,
              taskId,
            );
          }
        }
        boundary = buffer.indexOf("\n\n");
      }
    }
  } catch (error) {
    if (error.name === "AbortError") {
      return;
    }
    appendEvent("error", { content: error.message });
    showToast(error.message, "error");
    $("progress-node").textContent = "error";
  } finally {
    if (state.streamController === controller) {
      state.streamController = null;
      state.streaming = false;
      state.activeStreamTaskId = null;
      await loadTasks().catch(() => {});
      const current = state.tasks.find((item) => item.task_id === taskId);
      state.selectedTaskStatus = current || state.selectedTaskStatus;
      updateTaskControls(state.selectedTaskStatus);
    }
  }
}

async function loadTaskStatus(taskId) {
  const task = await api(`/api/agent/tasks/${taskId}`);
  state.selectedTaskStatus = task;
  updateTaskControls(task);
  if (task.status === "completed") {
    await loadReport(taskId);
  } else if (task.status === "waiting_confirmation") {
    clearReport();
    await loadConfirmation(taskId);
  } else {
    $("confirmation-card").classList.add("hidden");
    clearReport();
  }
}

async function selectTask(taskId) {
  state.selectedTaskId = taskId;
  renderTasks();
  clearReport();
  try {
    await loadTaskStatus(taskId);
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function loadReport(taskId) {
  try {
    const report = await api(`/api/agent/tasks/${taskId}/report`);
    renderReport(report);
    const task = state.tasks.find((item) => item.task_id === taskId);
    applyTaskMetrics(task, report.result_json?.usage);
  } catch (error) {
    if (error.message.includes("报告不存在")) {
      clearReport();
      return;
    }
    showToast(error.message, "error");
  }
}

async function loadConfirmation(taskId) {
  try {
    const result = await api(`/api/agent/tasks/${taskId}/graph/confirmation`);
    if (result?.status !== "waiting_confirmation" || !result.pending_confirmation) {
      $("confirmation-card").classList.add("hidden");
      return;
    }
    state.pendingConfirmation = result.pending_confirmation;
    $("confirmation-json").value = JSON.stringify(result.pending_confirmation, null, 2);
    $("confirmation-card").classList.remove("hidden");
    $("task-state").textContent = "waiting_confirmation";
    $("task-state").className = "badge warning";
    $("resume-interrupted").disabled = false;
  } catch (error) {
    $("confirmation-card").classList.add("hidden");
    showToast(error.message, "error");
  }
}

async function submitConfirmation(decision) {
  if (!state.selectedTaskId) return;
  const body = { decision };
  if (decision === "revise") {
    let editedReport;
    try {
      editedReport = JSON.parse($("confirmation-json").value);
    } catch (_) {
      showToast("待确认报告必须是合法 JSON", "error");
      return;
    }
    body.edited_report = editedReport;
    const revision = $("resume-revision").value.trim();
    if (revision) body.resume_revision_text = revision;
  }

  try {
    const result = await api(`/api/agent/tasks/${state.selectedTaskId}/graph/resume`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    $("confirmation-card").classList.add("hidden");
    state.pendingConfirmation = null;
    appendEvent("human_confirmation", { content: decision, data: { status: result.status } });
    await loadTasks();
    state.selectedTaskStatus = { ...(state.selectedTaskStatus || {}), ...result };
    updateTaskControls(state.selectedTaskStatus);
    if (result.status === "completed") {
      await loadReport(state.selectedTaskId);
    } else {
      clearReport();
    }
    showToast(decision === "reject" ? "报告已拒绝" : "确认已提交");
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function retryInterrupted() {
  if (!state.selectedTaskId) return;
  if (state.selectedTaskStatus?.status === "waiting_confirmation") {
    await loadConfirmation(state.selectedTaskId);
    return;
  }
  await streamGraphTask(state.selectedTaskId);
}

function bindEvents() {
  $("login-button").addEventListener("click", login);
  $("logout-button").addEventListener("click", () => logout());
  $("password-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter") login();
  });
  $("upload-resume").addEventListener("click", uploadResume);
  $("create-job").addEventListener("click", createJob);
  $("start-analysis").addEventListener("click", createAndRunTask);
  $("resume-interrupted").addEventListener("click", retryInterrupted);
  $("refresh-all").addEventListener("click", () => {
    loadAll().then(() => showToast("数据已刷新")).catch((error) => showToast(error.message, "error"));
  });
  $("approve-confirmation").addEventListener("click", () => submitConfirmation("approve"));
  $("revise-confirmation").addEventListener("click", () => submitConfirmation("revise"));
  $("reject-confirmation").addEventListener("click", () => submitConfirmation("reject"));
}

function initialize() {
  if (!$("username-input").value) {
    $("username-input").value = "demo_user";
  }
  bindEvents();
  clearReport();
  showLoggedOut();
  restoreSession();
}

document.addEventListener("DOMContentLoaded", initialize);
