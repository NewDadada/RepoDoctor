/* Repo Doctor · local UI logic (no build step, no external dependencies) */
(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);

  const TOOL_META = {
    clone_repo: { label: "克隆仓库", icon: "i-git" },
    search_code: { label: "搜索代码", icon: "i-search" },
    read_file: { label: "读取文件", icon: "i-file" },
    default: { label: "工具调用", icon: "i-terminal" },
  };

  const LABEL_MAP = {
    FINDING: "发现",
    LOCATION: "位置",
    QUOTE: "证据",
    PATCH: "修复",
    FIX: "修复",
    SEVERITY: "严重性",
    IMPACT: "影响",
    "ROOT CAUSE": "原因",
    CONCLUSION: "结论",
    EVIDENCE: "证据",
    "建议": "建议",
    "位置": "位置",
    "结论": "结论",
    "证据": "证据",
  };

  const LABEL_RE =
    /^\s*(FINDING|LOCATION|QUOTE|PATCH|FIX|SEVERITY|IMPACT|ROOT CAUSE|CONCLUSION|EVIDENCE|建议|位置|结论|证据)\s*[:：]\s*(.*)$/i;

  const state = {
    info: null,
    running: false,
    status: "idle",
    runId: null,
    steps: 0,
    startedAt: 0,
    timer: null,
    controller: null,
    abortTimer: null,
    stopRequested: false,
    rawAnswer: "",
    savedForm: null,
  };

  const el = {};

  function init() {
    el.form = $("#runForm");
    el.repo = $("#repo");
    el.goal = $("#goal");
    el.ref = $("#ref");
    el.maxSteps = $("#maxSteps");
    el.samples = $("#samples");
    el.keyWarn = $("#keyWarn");
    el.runBtn = $("#runBtn");
    el.emptyState = $("#emptyState");
    el.runView = $("#runView");
    el.statusbar = $("#statusbar");
    el.statusIcon = $("#statusIcon");
    el.statusTitle = $("#statusTitle");
    el.statusSub = $("#statusSub");
    el.stepCount = $("#stepCount");
    el.elapsed = $("#elapsed");
    el.stopBtn = $("#stopBtn");
    el.timeline = $("#timeline");
    el.thinking = $("#thinking");
    el.thinkingStep = $("#thinkingStep");
    el.finalCard = $("#finalCard");
    el.errorCard = $("#errorCard");
    el.modelChip = $("#modelChip");
    el.workspaceChip = $("#workspaceChip");
    el.versionChip = $("#versionChip");
    el.footVersion = $("#footVersion");
    el.themeBtn = $("#themeBtn");
    el.toast = $("#toast");

    restoreForm();
    bindTheme();
    bindForm();
    bindShortcuts();
    syncThemeButton();
    watchSystemTheme();
    loadInfo();
  }

  // ---------------------------------------------------------------------
  // boot / config
  // ---------------------------------------------------------------------

  async function loadInfo() {
    try {
      const res = await fetch("/api/info", { cache: "no-store" });
      if (!res.ok) throw new Error("info failed");
      const info = await res.json();
      state.info = info;

      el.modelChip.textContent = info.model || "unknown";
      el.modelChip.title = `模型：${info.model || "unknown"}`;
      if (info.workspace) {
        el.workspaceChip.textContent = info.workspace;
        el.workspaceChip.title = `工作目录：${info.workspace}`;
      }
      el.versionChip.textContent = `v${info.version || "1.0.0"}`;
      el.footVersion.textContent = `v${info.version || "1.0.0"}`;

      if (!state.savedForm) {
        el.goal.value = info.default_goal || el.goal.value;
      }
      if (!state.savedForm || !state.savedForm.maxSteps) {
        el.maxSteps.value = String(info.max_steps || 15);
      }
      if (!info.has_key) {
        el.keyWarn.hidden = false;
      }
      renderSamples(Array.isArray(info.samples) ? info.samples : []);
    } catch (_) {
      /* the page is only served by the API, so a failure here is informational */
    }
  }

  function renderSamples(samples) {
    el.samples.innerHTML = "";
    for (const sample of samples) {
      if (!sample || !sample.url) continue;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "chip-btn";
      button.textContent = sample.label || sample.url;
      button.title = `填入 ${sample.url}`;
      button.addEventListener("click", () => {
        el.repo.value = sample.url;
        el.repo.focus();
      });
      el.samples.append(button);
    }
  }

  function restoreForm() {
    try {
      const saved = JSON.parse(localStorage.getItem("rd-form") || "null");
      if (saved && typeof saved === "object") {
        state.savedForm = saved;
        if (saved.repo) el.repo.value = saved.repo;
        if (saved.goal) el.goal.value = saved.goal;
        if (saved.ref) el.ref.value = saved.ref;
        if (saved.maxSteps) el.maxSteps.value = String(saved.maxSteps);
      }
    } catch (_) {
      state.savedForm = null;
    }
  }

  function persistForm(payload) {
    try {
      localStorage.setItem(
        "rd-form",
        JSON.stringify({
          repo: payload.repo_url,
          goal: payload.goal,
          ref: payload.ref,
          maxSteps: payload.max_steps,
        }),
      );
      state.savedForm = JSON.parse(localStorage.getItem("rd-form") || "null");
    } catch (_) {
      /* storage may be disabled */
    }
  }

  // ---------------------------------------------------------------------
  // theme
  // ---------------------------------------------------------------------

  function bindTheme() {
    el.themeBtn.addEventListener("click", () => {
      const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try {
        localStorage.setItem("rd-theme", next);
      } catch (_) {}
      syncThemeButton();
    });
  }

  function syncThemeButton() {
    const dark = document.documentElement.dataset.theme === "dark";
    el.themeBtn.setAttribute("aria-label", dark ? "切换到浅色模式" : "切换到深色模式");
    el.themeBtn.title = dark ? "切换到浅色模式" : "切换到深色模式";
  }

  function watchSystemTheme() {
    if (!window.matchMedia) return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (event) => {
      try {
        if (localStorage.getItem("rd-theme")) return;
      } catch (_) {}
      document.documentElement.dataset.theme = event.matches ? "dark" : "light";
      syncThemeButton();
    };
    if (media.addEventListener) media.addEventListener("change", onChange);
  }

  // ---------------------------------------------------------------------
  // form
  // ---------------------------------------------------------------------

  function bindForm() {
    el.form.addEventListener("submit", (event) => {
      event.preventDefault();
      startRun();
    });

    el.stopBtn.addEventListener("click", requestStop);
  }

  function bindShortcuts() {
    document.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        event.preventDefault();
        if (!state.running) startRun();
      }
    });
  }

  function readForm() {
    const repo = el.repo.value.trim();
    const goal = el.goal.value.trim();
    if (!repo) {
      el.repo.focus();
      showToast("请先填写仓库地址");
      return null;
    }
    if (!goal) {
      el.goal.focus();
      showToast("请写一句体检目标");
      return null;
    }
    let maxSteps = parseInt(el.maxSteps.value, 10);
    if (!Number.isFinite(maxSteps)) maxSteps = 15;
    maxSteps = Math.max(1, Math.min(30, maxSteps));
    el.maxSteps.value = String(maxSteps);
    return {
      repo_url: repo,
      goal,
      ref: el.ref.value.trim(),
      max_steps: maxSteps,
    };
  }

  // ---------------------------------------------------------------------
  // run lifecycle
  // ---------------------------------------------------------------------

  async function startRun() {
    if (state.running) return;
    const payload = readForm();
    if (!payload) return;

    persistForm(payload);
    resetReport();
    state.running = true;
    state.status = "running";
    state.stopRequested = false;
    state.rawAnswer = "";
    state.steps = 0;
    state.runId = newRunId();
    state.startedAt = performance.now();
    el.emptyState.hidden = true;
    el.runView.hidden = false;
    setRunningUi(true);
    setStatus("running", "正在体检", "正在连接本地服务…", "spinner");
    updateStats(0, 0);
    startTimer();

    state.controller = new AbortController();

    if (window.innerWidth < 900) {
      el.statusbar.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    try {
      const res = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: state.controller.signal,
      });

      if (!res.ok) {
        let data = {};
        try {
          data = await res.json();
        } catch (_) {}
        finishError(data.error || `本地服务返回 ${res.status}`, data.hint || "");
        return;
      }
      if (!res.body) {
        finishError("当前浏览器不支持流式响应", "请使用较新的 Chrome、Edge 或 Safari。");
        return;
      }

      await consumeStream(res.body);
      if (state.running) {
        finishError("连接提前结束", "没有收到完成事件，请重试或查看服务端日志。");
      }
    } catch (error) {
      if (error && error.name === "AbortError") {
        if (state.stopRequested) {
          finishCancelled({
            status: "cancelled",
            steps: state.steps,
            elapsed_ms: elapsedMs(),
            final_answer: null,
          });
        } else {
          finishError("连接已中断", "本地服务可能已停止。");
        }
      } else {
        finishError("无法连接到本地服务", (error && error.message) || "未知错误");
      }
    }
  }

  async function consumeStream(body) {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let index;
      while ((index = buffer.indexOf("\n\n")) !== -1) {
        const chunk = buffer.slice(0, index);
        buffer = buffer.slice(index + 2);
        handleChunk(chunk);
      }
    }

    buffer += decoder.decode();
    if (buffer.trim()) handleChunk(buffer);
  }

  function handleChunk(raw) {
    let event = "message";
    const dataLines = [];
    for (const line of raw.split("\n")) {
      if (!line || line.startsWith(":")) continue;
      const colon = line.indexOf(":");
      const field = colon === -1 ? line : line.slice(0, colon);
      let value = colon === -1 ? "" : line.slice(colon + 1);
      if (value.startsWith(" ")) value = value.slice(1);
      if (field === "event") event = value;
      else if (field === "data") dataLines.push(value);
    }
    if (!dataLines.length) return;
    let payload;
    try {
      payload = JSON.parse(dataLines.join("\n"));
    } catch (_) {
      return;
    }
    dispatch(event, payload);
  }

  function dispatch(event, payload) {
    switch (event) {
      case "meta":
        if (payload.run_id) state.runId = payload.run_id;
        if (payload.max_steps) {
          el.maxSteps.value = String(payload.max_steps);
        }
        setStatus(
          "running",
          "正在体检",
          `已克隆任务 · 模型 ${payload.model || "unknown"} · 最多 ${payload.max_steps || "?"} 步`,
          "spinner",
        );
        break;
      case "thinking":
        setPhase(`第 ${payload.step || state.steps + 1} 步 · 模型正在规划下一步`);
        showThinking(payload.step || state.steps + 1);
        break;
      case "step":
        hideThinking();
        addStep(payload);
        state.steps = Math.max(state.steps, Number(payload.step) || 0);
        updateStats(state.steps);
        setPhase("已记录一步，继续分析…");
        break;
      case "done":
        finishRun(payload);
        break;
      case "error":
        finishError(payload.message || "运行失败", payload.hint || "");
        break;
      default:
        break;
    }
  }

  async function requestStop() {
    if (!state.running || state.stopRequested) return;
    state.stopRequested = true;
    el.stopBtn.disabled = true;
    const label = el.stopBtn.querySelector("span");
    if (label) label.textContent = "停止中…";
    setPhase("正在停止，等待当前步骤结束…");

    try {
      await fetch("/api/cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: state.runId }),
      });
    } catch (_) {}

    clearAbortTimer();
    state.abortTimer = setTimeout(() => {
      if (state.running && state.controller) state.controller.abort();
    }, 8000);
  }

  function clearAbortTimer() {
    if (state.abortTimer) {
      clearTimeout(state.abortTimer);
      state.abortTimer = null;
    }
  }

  function finishRun(data) {
    if (state.status === "finished") return;
    state.status = "finished";
    clearAbortTimer();
    stopTimer();
    hideThinking();
    setRunningUi(false);

    const status = data.status || "done";
    const elapsed = Number(data.elapsed_ms) || elapsedMs();
    const steps = Number(data.steps) || state.steps;
    state.rawAnswer = typeof data.final_answer === "string" ? data.final_answer : "";
    updateStats(steps, elapsed);

    el.finalCard.hidden = false;
    el.finalCard.className = "final";
    el.finalCard.innerHTML = "";

    if (status === "done" && state.rawAnswer.trim()) {
      setStatus("done", "体检完成", "已生成诊断结论", "check");
      el.finalCard.append(buildFinalHead("诊断结论", true));
      el.finalCard.append(buildAnswer(state.rawAnswer));
      el.finalCard.append(buildFinalFoot(data, elapsed, steps));
    } else if (status === "cancelled") {
      setStatus("cancelled", "已停止", "本次体检被手动停止", "stop");
      el.finalCard.classList.add("is-cancelled");
      el.finalCard.append(buildFinalHead("运行已停止", true));
      el.finalCard.append(
        buildNotice("i-stop", "本次体检已停止", "执行记录已保留，可以调整目标后重新开始。"),
      );
      el.finalCard.append(buildFinalFoot(data, elapsed, steps, "结束于"));
    } else if (status === "max_steps") {
      setStatus("incomplete", "未完成", "达到最大步数，结论可能不完整", "alert");
      el.finalCard.classList.add("is-incomplete");
      el.finalCard.append(buildFinalHead("尚未完成", true));
      el.finalCard.append(
        buildNotice(
          "i-alert",
          "达到最大步数",
          "Agent 在步数上限内没有给出最终答案。可以调高「最大步数」，或把体检目标写得更具体后重试。",
        ),
      );
      el.finalCard.append(buildFinalFoot(data, elapsed, steps, "结束于"));
    } else {
      state.status = "running";
      finishError("模型没有返回可用结论", "可以重试一次，或换一个更具体的目标。");
      return;
    }

    revealFinal();
  }

  function finishCancelled(data) {
    finishRun({
      status: "cancelled",
      final_answer: null,
      steps: data.steps || state.steps,
      elapsed_ms: data.elapsed_ms || elapsedMs(),
    });
  }

  function finishError(message, hint) {
    if (state.status === "finished") return;
    state.status = "finished";
    clearAbortTimer();
    stopTimer();
    hideThinking();
    setRunningUi(false);
    setStatus("error", "运行失败", "请检查配置或网络后重试", "alert");
    el.finalCard.hidden = true;
    updateStats(state.steps, elapsedMs());

    el.errorCard.hidden = false;
    el.errorCard.innerHTML = "";
    const alert = document.createElement("div");
    alert.className = "alert error";

    const icon = svgIcon("i-alert");
    const copy = document.createElement("div");
    copy.className = "alert-copy";

    const title = document.createElement("strong");
    title.textContent = "无法完成体检";
    const text = document.createElement("p");
    text.textContent = message || "未知错误";
    copy.append(title, text);

    if (hint) {
      const hintEl = document.createElement("p");
      hintEl.className = "alert-hint";
      hintEl.textContent = hint;
      copy.append(hintEl);
    }

    alert.append(icon, copy);
    el.errorCard.append(alert);
    el.errorCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function resetReport() {
    clearAbortTimer();
    stopTimer();
    state.controller = null;
    state.savedForm = state.savedForm || null;
    el.timeline.innerHTML = "";
    el.finalCard.hidden = true;
    el.finalCard.className = "final";
    el.finalCard.innerHTML = "";
    el.errorCard.hidden = true;
    el.errorCard.innerHTML = "";
    el.thinking.hidden = true;
    el.statusbar.className = "statusbar";
    el.stopBtn.disabled = false;
    const stopLabel = el.stopBtn.querySelector("span");
    if (stopLabel) stopLabel.textContent = "停止";
    state.status = "running";
    state.stopRequested = false;
  }

  function setRunningUi(running) {
    state.running = running;
    el.runBtn.disabled = running;
    el.runBtn.classList.toggle("is-busy", running);
    const label = el.runBtn.querySelector("span");
    if (label) label.textContent = running ? "体检中…" : "开始体检";
    for (const input of [el.repo, el.goal, el.ref, el.maxSteps]) {
      input.disabled = running;
    }
    el.stopBtn.hidden = !running;
  }

  function setStatus(tone, title, sub, icon) {
    el.statusbar.className = `statusbar ${tone}`;
    el.statusTitle.textContent = title;
    el.statusSub.textContent = sub;
    if (icon === "spinner") {
      el.statusIcon.innerHTML = '<span class="spinner"></span>';
    } else {
      const id = icon ? (icon.startsWith("i-") ? icon : `i-${icon}`) : "i-check";
      el.statusIcon.innerHTML = svgIconMarkup(id);
    }
    if (tone !== "running") {
      el.stopBtn.hidden = true;
    }
  }

  function setPhase(text) {
    if (!state.running) return;
    el.statusSub.textContent = text;
  }

  function updateStats(steps, elapsed) {
    el.stepCount.textContent = String(steps || 0);
    if (elapsed !== undefined && elapsed !== null) {
      el.elapsed.textContent = formatDuration(elapsed);
    }
  }

  function startTimer() {
    stopTimer();
    state.startedAt = performance.now();
    state.timer = setInterval(() => {
      if (state.running) {
        el.elapsed.textContent = formatDuration(elapsedMs());
      }
    }, 250);
  }

  function stopTimer() {
    if (state.timer) clearInterval(state.timer);
    state.timer = null;
  }

  function elapsedMs() {
    return Math.max(0, Math.round(performance.now() - state.startedAt));
  }

  function showThinking(step) {
    el.thinkingStep.textContent = String(step);
    el.thinking.hidden = false;
    if (isNearBottom()) {
      el.thinking.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  function hideThinking() {
    el.thinking.hidden = true;
  }

  function revealFinal() {
    const rect = el.finalCard.getBoundingClientRect();
    if (rect.top < 0 || rect.top > window.innerHeight - 120) {
      el.finalCard.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  // ---------------------------------------------------------------------
  // timeline
  // ---------------------------------------------------------------------

  function addStep(step) {
    const meta = TOOL_META[step.tool] || TOOL_META.default;
    const li = document.createElement("li");
    li.className = "step";
    li.dataset.tool = step.tool || "unknown";
    li.dataset.ok = step.ok ? "true" : "false";

    const rail = document.createElement("div");
    rail.className = "step-rail";
    const node = document.createElement("span");
    node.className = "step-node";
    node.innerHTML = svgIconMarkup(meta.icon);
    rail.append(node);

    const card = document.createElement("article");
    card.className = "step-card";

    const head = document.createElement("div");
    head.className = "step-head";

    const title = document.createElement("div");
    title.className = "step-title";
    const index = document.createElement("span");
    index.className = "step-index";
    index.textContent = String(step.step || 0).padStart(2, "0");
    const toolName = document.createElement("span");
    toolName.className = "tool-name";
    toolName.textContent = meta.label;
    title.append(index, toolName);

    if (step.data && step.data.path) {
      const file = document.createElement("code");
      file.className = "step-file";
      file.textContent = basename(step.data.path);
      file.title = step.data.path;
      title.append(file);
    }

    const metaBox = document.createElement("div");
    metaBox.className = "step-meta";
    const badge = document.createElement("span");
    badge.className = `badge ${step.ok ? "ok" : "fail"}`;
    badge.textContent = step.ok ? "成功" : "失败";
    const duration = document.createElement("span");
    duration.className = "duration";
    duration.textContent = formatMs(step.duration_ms);
    metaBox.append(badge, duration);

    const body = document.createElement("div");
    body.className = "step-body";
    body.hidden = true;
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "ghost-btn";
    toggle.setAttribute("aria-expanded", "false");
    toggle.innerHTML = '<span>详情</span>' + svgIconMarkup("i-chevron", "chev");
    toggle.addEventListener("click", () => {
      const open = body.hidden;
      body.hidden = !open;
      toggle.setAttribute("aria-expanded", String(open));
      const label = toggle.querySelector("span");
      if (label) label.textContent = open ? "收起" : "详情";
    });
    metaBox.append(toggle);

    head.append(title, metaBox);
    card.append(head);

    if (step.thought && step.thought.trim()) {
      const thought = document.createElement("p");
      thought.className = "step-thought";
      thought.textContent = step.thought.trim();
      card.append(thought);
    }

    const summary = summarizeStep(step);
    const summaryEl = document.createElement("div");
    summaryEl.className = `step-summary${summary.error ? " is-error" : ""}`;
    summaryEl.innerHTML = svgIconMarkup(summary.icon);
    const summaryText = document.createElement("span");
    summaryText.textContent = summary.text;
    summaryEl.append(summaryText);
    card.append(summaryEl);

    buildStepBody(step, body);
    card.append(body);

    if (!step.ok) {
      body.hidden = false;
      toggle.setAttribute("aria-expanded", "true");
      const label = toggle.querySelector("span");
      if (label) label.textContent = "收起";
    }

    li.append(rail, card);
    el.timeline.append(li);

    if (isNearBottom()) {
      li.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  function summarizeStep(step) {
    if (!step.ok) {
      return { icon: "i-alert", text: step.error || "调用失败", error: true };
    }
    const data = step.data || {};
    if (step.tool === "clone_repo") {
      const path = data.path || "workspace";
      return {
        icon: "i-git",
        text: data.cached ? `缓存命中 · ${path}` : `已克隆 · ${path}`,
      };
    }
    if (step.tool === "search_code") {
      const count = Number(data.count) || 0;
      if (!count) return { icon: "i-search", text: "没有命中，模型会换一种方式" };
      return { icon: "i-search", text: `命中 ${count} 处` };
    }
    if (step.tool === "read_file") {
      const lines = String(data.content || "").split("\n").length;
      const start = Number(data.start) || 1;
      const total = data.total_lines != null ? data.total_lines : "?";
      return { icon: "i-file", text: `第 ${start}–${start + lines - 1} 行 · 共 ${total} 行` };
    }
    return { icon: "i-terminal", text: "调用完成" };
  }

  function buildStepBody(step, body) {
    if (!step.ok) {
      const box = document.createElement("div");
      box.className = "error-box";
      box.innerHTML = svgIconMarkup("i-alert");
      const copy = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = "工具调用失败";
      const message = document.createElement("p");
      message.textContent = step.error || "未知错误";
      copy.append(title, message);
      if (step.hint) {
        const hint = document.createElement("p");
        hint.className = "hint";
        hint.textContent = step.hint;
        copy.append(hint);
      }
      box.append(copy);
      body.append(box);
      return;
    }

    if (step.tool === "read_file" && step.data) {
      const content = String(step.data.content || "");
      if (!content) {
        body.append(muted("文件为空。"));
        return;
      }
      body.append(codeView(step.data.path, step.data.start, content, step.data.total_lines, step.data.truncated));
      return;
    }

    if (step.tool === "search_code") {
      const args = step.args || {};
      const meta = document.createElement("p");
      meta.className = "body-meta";
      meta.textContent = `pattern: ${args.pattern || "—"} · glob: ${args.glob || "*.py"}`;
      body.append(meta);

      const hits = step.data && Array.isArray(step.data.hits) ? step.data.hits : [];
      if (!hits.length) {
        body.append(muted("没有命中。"));
        return;
      }
      const list = document.createElement("ul");
      list.className = "hits";
      for (const hit of hits) {
        const item = document.createElement("li");
        const button = document.createElement("button");
        button.type = "button";
        button.className = "hit";
        button.title = "点击复制引用";
        const ref = document.createElement("span");
        ref.className = "hit-ref";
        ref.textContent = hit.path || "?";
        const line = document.createElement("span");
        line.className = "hit-line";
        line.textContent = hit.line != null ? `:${hit.line}` : "";
        const code = document.createElement("span");
        code.className = "hit-code";
        code.textContent = hit.text || "";
        button.append(ref, line, code);
        button.addEventListener("click", async () => {
          const ok = await copyText(`${hit.path}:${hit.line}`);
          if (ok) showToast("已复制引用");
        });
        item.append(button);
        list.append(item);
      }
      body.append(list);
      if (step.data.count > hits.length) {
        body.append(muted(`共 ${step.data.count} 处，仅显示前 ${hits.length} 处。`));
      }
      return;
    }

    if (step.tool === "clone_repo") {
      const data = step.data || {};
      const args = step.args || {};
      body.append(
        kvList([
          ["仓库", args.repo_url || "—"],
          ["分支", args.ref || "默认分支"],
          ["路径", data.path || "—"],
          ["缓存", data.cached ? "命中" : "新克隆"],
        ]),
      );
      return;
    }

    const data = step.data;
    if (data && typeof data === "object" && Object.keys(data).length) {
      const pre = document.createElement("pre");
      pre.className = "json-view";
      try {
        pre.textContent = JSON.stringify(data, null, 2);
      } catch (_) {
        pre.textContent = String(data);
      }
      body.append(pre);
    } else {
      body.append(muted("没有附加数据。"));
    }
  }

  function codeView(path, start, content, totalLines, truncated) {
    const wrap = document.createElement("div");
    wrap.className = "code-view";

    const head = document.createElement("div");
    head.className = "code-head";
    const left = document.createElement("span");
    left.className = "code-path";
    left.textContent = path || "file";
    const right = document.createElement("span");
    const startLine = Number(start) || 1;
    const lines = content.split("\n");
    right.textContent = `${startLine}–${startLine + lines.length - 1} / ${totalLines != null ? totalLines : "?"}`;
    head.append(left, right);

    const scroll = document.createElement("div");
    scroll.className = "code-scroll";
    const fragment = document.createDocumentFragment();
    lines.forEach((line, offset) => {
      const row = document.createElement("div");
      row.className = "code-line";
      const number = document.createElement("span");
      number.className = "ln";
      number.textContent = String(startLine + offset);
      const source = document.createElement("span");
      source.className = "src";
      source.textContent = line.length ? line : " ";
      row.append(number, source);
      fragment.append(row);
    });
    scroll.append(fragment);
    wrap.append(head, scroll);

    if (truncated) {
      const note = document.createElement("div");
      note.className = "code-note";
      note.textContent = "内容较长，已截断显示。";
      wrap.append(note);
    }
    return wrap;
  }

  function kvList(rows) {
    const grid = document.createElement("div");
    grid.className = "kv";
    for (const [key, value] of rows) {
      const keyEl = document.createElement("span");
      keyEl.className = "kv-key";
      keyEl.textContent = key;
      const valueEl = document.createElement("span");
      valueEl.className = "kv-val";
      valueEl.textContent = value || "—";
      grid.append(keyEl, valueEl);
    }
    return grid;
  }

  // ---------------------------------------------------------------------
  // final card
  // ---------------------------------------------------------------------

  function buildFinalHead(label, withActions) {
    const head = document.createElement("div");
    head.className = "final-head";

    const badge = document.createElement("span");
    badge.className = "final-badge";
    const dot = document.createElement("span");
    dot.className = "badge-dot";
    badge.append(dot, document.createTextNode(label));

    head.append(badge);
    if (!withActions) return head;

    const actions = document.createElement("div");
    actions.className = "final-actions";

    if (state.rawAnswer) {
      const copy = document.createElement("button");
      copy.type = "button";
      copy.className = "btn-soft";
      copy.innerHTML = svgIconMarkup("i-copy") + "<span>复制</span>";
      copy.addEventListener("click", async () => {
        const ok = await copyText(state.rawAnswer);
        if (!ok) return;
        copy.classList.add("copied");
        const text = copy.querySelector("span");
        if (text) text.textContent = "已复制";
        showToast("报告已复制");
        setTimeout(() => {
          copy.classList.remove("copied");
          if (text) text.textContent = "复制";
        }, 1800);
      });
      actions.append(copy);
    }

    const again = document.createElement("button");
    again.type = "button";
    again.className = "btn-soft";
    again.innerHTML = svgIconMarkup("i-refresh") + "<span>再跑一次</span>";
    again.addEventListener("click", () => {
      if (!state.running) startRun();
    });
    actions.append(again);

    head.append(actions);
    return head;
  }

  function buildAnswer(raw) {
    const answer = document.createElement("div");
    answer.className = "answer";
    answer.innerHTML = renderAnswer(raw);
    answer.addEventListener("click", async (event) => {
      const target = event.target.closest(".loc");
      if (!target) return;
      const ok = await copyText(target.textContent.trim());
      if (ok) showToast("已复制位置");
    });
    return answer;
  }

  function buildNotice(icon, title, text) {
    const notice = document.createElement("div");
    notice.className = "notice";
    const iconBox = document.createElement("div");
    iconBox.className = "notice-icon";
    iconBox.innerHTML = svgIconMarkup(icon);
    const copy = document.createElement("div");
    copy.className = "notice-copy";
    const heading = document.createElement("strong");
    heading.textContent = title;
    const paragraph = document.createElement("p");
    paragraph.textContent = text;
    copy.append(heading, paragraph);
    notice.append(iconBox, copy);
    return notice;
  }

  function buildFinalFoot(data, elapsed, steps, finishedLabel = "完成于") {
    const foot = document.createElement("div");
    foot.className = "final-foot";
    const parts = [`用时 ${formatDuration(elapsed)}`];
    if (steps) parts.push(`${steps} 步`);
    if (state.info && state.info.model) parts.push(`模型 ${state.info.model}`);
    parts.push(`${finishedLabel} ${new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}`);

    parts.forEach((part, index) => {
      if (index) {
        const sep = document.createElement("span");
        sep.className = "sep";
        foot.append(sep);
      }
      const span = document.createElement("span");
      span.textContent = part;
      foot.append(span);
    });
    return foot;
  }

  // ---------------------------------------------------------------------
  // lightweight markdown
  // ---------------------------------------------------------------------

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => {
      switch (char) {
        case "&":
          return "&amp;";
        case "<":
          return "&lt;";
        case ">":
          return "&gt;";
        case '"':
          return "&quot;";
        default:
          return "&#39;";
      }
    });
  }

  function inlineMd(text) {
    const codes = [];
    let html = escapeHtml(text).replace(/`([^`]+)`/g, (_, code) => {
      codes.push(code);
      return `\u0000${codes.length - 1}\u0000`;
    });
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
    html = html.replace(
      /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
    );
    html = html.replace(/\u0000(\d+)\u0000/g, (_, index) => `<code>${codes[Number(index)]}</code>`);
    return html;
  }

  function renderMarkdown(text) {
    const lines = String(text).replace(/\r\n/g, "\n").split("\n");
    const out = [];
    let paragraph = [];
    let list = null;

    const flushParagraph = () => {
      if (!paragraph.length) return;
      out.push(`<p>${paragraph.map(inlineMd).join("<br>")}</p>`);
      paragraph = [];
    };

    const flushList = () => {
      if (!list) return;
      out.push(`<${list.type}>${list.items.map((item) => `<li>${item}</li>`).join("")}</${list.type}>`);
      list = null;
    };

    for (let i = 0; i < lines.length; i += 1) {
      const line = lines[i];

      if (/^```/.test(line.trim())) {
        flushParagraph();
        flushList();
        const language = line.trim().slice(3).trim();
        const code = [];
        i += 1;
        while (i < lines.length && !/^```/.test(lines[i].trim())) {
          code.push(lines[i]);
          i += 1;
        }
        const langAttr = language ? ` data-lang="${escapeHtml(language)}"` : "";
        out.push(`<pre${langAttr}><code>${escapeHtml(code.join("\n"))}</code></pre>`);
        continue;
      }

      if (!line.trim()) {
        flushParagraph();
        flushList();
        continue;
      }

      const heading = line.match(/^(#{1,4})\s+(.*)$/);
      if (heading) {
        flushParagraph();
        flushList();
        const level = Math.min(6, heading[1].length + 2);
        out.push(`<h${level}>${inlineMd(heading[2])}</h${level}>`);
        continue;
      }

      if (/^(---|\*\*\*|___)\s*$/.test(line)) {
        flushParagraph();
        flushList();
        out.push("<hr>");
        continue;
      }

      const quote = line.match(/^>\s?(.*)$/);
      if (quote) {
        flushParagraph();
        flushList();
        const quoted = [quote[1]];
        while (i + 1 < lines.length && /^>\s?/.test(lines[i + 1])) {
          i += 1;
          quoted.push(lines[i].replace(/^>\s?/, ""));
        }
        out.push(`<blockquote>${renderMarkdown(quoted.join("\n"))}</blockquote>`);
        continue;
      }

      const unordered = line.match(/^\s*[-*+]\s+(.*)$/);
      const ordered = line.match(/^\s*\d+[.)]\s+(.*)$/);
      if (unordered || ordered) {
        flushParagraph();
        const type = unordered ? "ul" : "ol";
        if (!list || list.type !== type) {
          flushList();
          list = { type, items: [] };
        }
        list.items.push(inlineMd((unordered || ordered)[1]));
        continue;
      }

      if (list) flushList();
      paragraph.push(line);
    }

    flushParagraph();
    flushList();
    return out.join("");
  }

  function renderAnswer(raw) {
    const text = String(raw || "").trim();
    if (!text) return '<p class="muted">模型没有返回内容。</p>';

    const lines = text.replace(/\r\n/g, "\n").split("\n");
    const blocks = [];
    const preamble = [];
    let current = null;
    let inFence = false;

    for (const line of lines) {
      if (/^```/.test(line.trim())) inFence = !inFence;
      const match = inFence ? null : line.match(LABEL_RE);
      if (match) {
        if (current) blocks.push(current);
        current = { label: match[1].toUpperCase(), lines: [] };
        if (match[2].trim()) current.lines.push(match[2]);
      } else if (current) {
        current.lines.push(line);
      } else {
        preamble.push(line);
      }
    }
    if (current) blocks.push(current);

    if (blocks.length < 2) return renderMarkdown(text);

    let html = "";
    const lead = preamble.join("\n").trim();
    if (lead) html += renderMarkdown(lead);

    html += '<div class="findings">';
    for (const block of blocks) {
      const body = block.lines.join("\n").trim();
      const label = LABEL_MAP[block.label] || block.label;
      let bodyHtml;
      if (block.label === "LOCATION") {
        const cleaned = body.replace(/`/g, "").trim();
        if (/^[\w./\\-]+(?::\d+(?:-\d+)?)?$/.test(cleaned)) {
          bodyHtml = `<code class="loc" title="点击复制">${escapeHtml(cleaned)}</code>`;
        } else {
          bodyHtml = renderMarkdown(body);
        }
      } else {
        bodyHtml = body ? renderMarkdown(body) : '<p class="muted">—</p>';
      }
      html += `<div class="finding-row"><span class="finding-label">${escapeHtml(label)}</span><div class="finding-body">${bodyHtml}</div></div>`;
    }
    html += "</div>";
    return html;
  }

  // ---------------------------------------------------------------------
  // utils
  // ---------------------------------------------------------------------

  function svgIconMarkup(id, extraClass) {
    return `<svg class="icon${extraClass ? ` ${extraClass}` : ""}" aria-hidden="true"><use href="#${id}"></use></svg>`;
  }

  function svgIcon(id, extraClass) {
    const template = document.createElement("template");
    template.innerHTML = svgIconMarkup(id, extraClass);
    return template.content.firstChild;
  }

  function muted(text) {
    const p = document.createElement("p");
    p.className = "muted";
    p.textContent = text;
    return p;
  }

  function basename(path) {
    return String(path || "").split(/[\\/]/).pop() || String(path || "");
  }

  function formatMs(ms) {
    const value = Number(ms) || 0;
    if (!value) return "—";
    if (value < 1000) return `${value}ms`;
    return `${(value / 1000).toFixed(1)}s`;
  }

  function formatDuration(ms) {
    const value = Math.max(0, Number(ms) || 0);
    if (value < 60000) {
      const seconds = value / 1000;
      return `${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)}s`;
    }
    const minutes = Math.floor(value / 60000);
    const seconds = Math.floor((value % 60000) / 1000);
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }

  function isNearBottom() {
    const gap = document.documentElement.scrollHeight - window.scrollY - window.innerHeight;
    return gap < 280;
  }

  function newRunId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    return `run-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  let toastTimer = null;
  function showToast(message) {
    el.toast.textContent = message;
    el.toast.classList.add("show");
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.toast.classList.remove("show"), 2000);
  }

  async function copyText(text) {
    const value = String(text || "");
    if (!value) return false;
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch (_) {
      try {
        const area = document.createElement("textarea");
        area.value = value;
        area.setAttribute("readonly", "");
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.append(area);
        area.select();
        const ok = document.execCommand("copy");
        area.remove();
        return ok;
      } catch (_) {
        return false;
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
