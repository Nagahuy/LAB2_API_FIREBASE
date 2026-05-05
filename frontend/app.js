const API_BASE = "http://127.0.0.1:8000";
const TOKEN_KEY = "study_chatbot_id_token";

const state = {
  user: null,
  sessions: [],
  activeSessionId: null,
  messages: [],
  loading: false,
};

const el = {
  authView: document.querySelector("#auth-view"),
  chatView: document.querySelector("#chat-view"),
  loginTab: document.querySelector("#login-tab"),
  signupTab: document.querySelector("#signup-tab"),
  loginForm: document.querySelector("#login-form"),
  signupForm: document.querySelector("#signup-form"),
  googleLoginBtn: document.querySelector("#google-login-btn"),
  logoutBtn: document.querySelector("#logout-btn"),
  newChatBtn: document.querySelector("#new-chat-btn"),
  reloadHistoryBtn: document.querySelector("#reload-history-btn"),
  sessionList: document.querySelector("#session-list"),
  accountStatus: document.querySelector("#account-status"),
  accountEmail: document.querySelector("#account-email"),
  loginMessage: document.querySelector("#login-message"),
  signupMessage: document.querySelector("#signup-message"),
  messageCount: document.querySelector("#message-count"),
  messages: document.querySelector("#messages"),
  emptyState: document.querySelector("#empty-state"),
  chatForm: document.querySelector("#chat-form"),
  chatInput: document.querySelector("#chat-input"),
  sendBtn: document.querySelector("#send-btn"),
  toast: document.querySelector("#toast"),
};

function setBusy(isBusy) {
  state.loading = isBusy;
  el.sendBtn.disabled = isBusy;
  el.chatInput.disabled = isBusy;
  el.sendBtn.textContent = isBusy ? "Thinking" : "Send";
  el.chatForm.classList.toggle("is-loading", isBusy);
}

function token() {
  return sessionStorage.getItem(TOKEN_KEY);
}

function setToken(value) {
  if (value) {
    sessionStorage.setItem(TOKEN_KEY, value);
  } else {
    sessionStorage.removeItem(TOKEN_KEY);
  }
}

async function requestJson(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };

  const currentToken = token();
  if (currentToken) {
    headers.Authorization = `Bearer ${currentToken}`;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (response.ok) {
    return response.json();
  }

  let detail = "Request failed";
  try {
    const payload = await response.json();
    detail = payload.detail || detail;
  } catch {
    detail = response.statusText || detail;
  }

  if (response.status === 401 && path !== "/auth/login") {
    logout(true, false);
    throw new Error("Please login again");
  }

  throw new Error(detail);
}

function showToast(message, type = "info") {
  el.toast.textContent = message;
  el.toast.className = `toast ${type}`;
  el.toast.classList.remove("hidden");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    el.toast.classList.add("hidden");
  }, 4200);
}

function showError(message) {
  showToast(message, "error");
}

function setFormMessage(target, message, type = "error") {
  target.textContent = message;
  target.className = `form-message ${type}`;
  target.classList.toggle("hidden", !message);
}

function clearFormMessages() {
  setFormMessage(el.loginMessage, "", "info");
  setFormMessage(el.signupMessage, "", "info");
}

function formatTime(value) {
  if (!value) {
    return "";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }

  return date.toLocaleString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "2-digit",
  });
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderText(value) {
  return escapeHtml(value || "")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br>");
}

function renderLatex(container) {
  if (!window.renderMathInElement) {
    return;
  }

  try {
    window.renderMathInElement(container, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "\\[", right: "\\]", display: true },
        { left: "\\(", right: "\\)", display: false },
        { left: "$", right: "$", display: false },
      ],
      throwOnError: false,
    });
  } catch {
    return;
  }
}

function renderMessages() {
  el.messages.innerHTML = "";
  el.emptyState.classList.toggle("hidden", state.messages.length > 0);
  el.messageCount.textContent = `${state.messages.length} messages`;

  for (const message of state.messages) {
    const role = message.role === "user" ? "user" : "assistant";
    const item = document.createElement("article");
    item.className = `message ${role}`;

    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.textContent = role === "user" ? "U" : "AI";

    const wrap = document.createElement("div");
    wrap.className = "bubble-wrap";

    const bubble = document.createElement("div");
    bubble.className = message.loading ? "bubble loading-bubble" : "bubble";
    bubble.innerHTML = renderText(message.content || "");
    renderLatex(bubble);
    wrap.appendChild(bubble);

    const shownTime = formatTime(message.created_at);
    if (shownTime) {
      const time = document.createElement("div");
      time.className = "message-time";
      time.textContent = shownTime;
      wrap.appendChild(time);
    }

    item.appendChild(avatar);
    item.appendChild(wrap);
    el.messages.appendChild(item);
  }

  window.requestAnimationFrame(() => {
    window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
  });
}

function renderSessions() {
  el.sessionList.innerHTML = "";

  if (!state.sessions.length) {
    const empty = document.createElement("p");
    empty.className = "session-empty";
    empty.textContent = "No chats yet";
    el.sessionList.appendChild(empty);
    return;
  }

  for (const session of state.sessions) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "session-button";
    button.classList.toggle("active", session.id === state.activeSessionId);

    const title = document.createElement("span");
    title.className = "session-title";
    title.textContent = session.title || "New chat";

    const time = document.createElement("span");
    time.className = "session-time";
    time.textContent = formatTime(session.updated_at) || "Just now";

    button.appendChild(title);
    button.appendChild(time);
    button.addEventListener("click", async () => {
      if (state.activeSessionId === session.id || state.loading) {
        return;
      }

      state.activeSessionId = session.id;
      state.messages = [];
      renderShell();
      try {
        await loadMessages();
      } catch (error) {
        showError(error.message);
      }
    });
    el.sessionList.appendChild(button);
  }
}

function renderShell() {
  const signedIn = Boolean(state.user);
  el.authView.classList.toggle("hidden", signedIn);
  el.chatView.classList.toggle("hidden", !signedIn);

  document.querySelectorAll(".signed-in-only").forEach((node) => {
    node.classList.toggle("hidden", !signedIn);
  });

  el.accountStatus.textContent = signedIn ? "Signed in" : "Not signed in";
  el.accountEmail.textContent = signedIn ? state.user.email : "";
  el.accountEmail.classList.toggle("hidden", !signedIn);
  el.logoutBtn.classList.toggle("hidden", !signedIn);

  renderSessions();
  renderMessages();
}

function setAuthTab(tab) {
  const isLogin = tab === "login";
  el.loginTab.classList.toggle("active", isLogin);
  el.signupTab.classList.toggle("active", !isLogin);
  el.loginForm.classList.toggle("hidden", !isLogin);
  el.signupForm.classList.toggle("hidden", isLogin);
}

async function loadProfile() {
  const profile = await requestJson("/auth/me");
  state.user = profile;
}

async function loadSessions() {
  const sessions = await requestJson("/chat/sessions?limit=30");
  state.sessions = Array.isArray(sessions) ? sessions : [];

  if (!state.sessions.length) {
    state.activeSessionId = null;
    state.messages = [];
    renderShell();
    return;
  }

  const activeExists = state.sessions.some((item) => item.id === state.activeSessionId);
  if (!activeExists) {
    state.activeSessionId = state.sessions[0].id;
  }

  renderShell();
}

async function loadMessages() {
  if (!state.activeSessionId) {
    state.messages = [];
    renderShell();
    return;
  }

  const params = new URLSearchParams({
    limit: "30",
    session_id: state.activeSessionId,
  });
  const messages = await requestJson(`/chat/messages?${params.toString()}`);
  state.messages = Array.isArray(messages) ? messages : [];
  renderShell();
}

async function loadWorkspace() {
  await loadSessions();
  await loadMessages();
}

async function login(email, password) {
  const data = await requestJson("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  setToken(data.idToken);
  await loadProfile();
  await loadWorkspace();
}

async function signup(email, password) {
  const data = await requestJson("/auth/signup", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  setToken(data.idToken);
  await loadProfile();
  await loadWorkspace();
}

function loginWithGoogle() {
  window.location.href = `${API_BASE}/auth/google/start`;
}

async function createSession() {
  const session = await requestJson("/chat/sessions", {
    method: "POST",
    body: JSON.stringify({}),
  });
  state.activeSessionId = session.id;
  state.messages = [];
  await loadSessions();
  renderShell();
}

function logout(render = true, notify = true) {
  setToken(null);
  state.user = null;
  state.sessions = [];
  state.activeSessionId = null;
  state.messages = [];
  state.loading = false;
  clearFormMessages();
  document.querySelectorAll("form").forEach((form) => form.reset());
  el.chatInput.value = "";
  autoResizeInput();
  setAuthTab("login");
  window.history.replaceState({}, document.title, window.location.pathname);
  if (render) {
    setBusy(false);
    renderShell();
    if (notify) {
      showToast("Logged out", "info");
    }
  }
}

async function sendMessage(content) {
  const localMessage = {
    role: "user",
    content,
    created_at: new Date().toISOString(),
  };

  state.messages.push(localMessage);
  renderMessages();
  setBusy(true);

  const loadingMessage = {
    role: "assistant",
    content: "AI đang suy nghĩ...",
    created_at: new Date().toISOString(),
    loading: true,
  };
  state.messages.push(loadingMessage);
  renderMessages();

  try {
    const body = { message: content };
    if (state.activeSessionId) {
      body.session_id = state.activeSessionId;
    }

    const data = await requestJson("/chat", {
      method: "POST",
      body: JSON.stringify(body),
    });
    if (data.session_id) {
      state.activeSessionId = data.session_id;
    }
    state.messages = state.messages.filter((item) => !item.loading);
    state.messages.push({
      role: "assistant",
      content: data.reply,
      created_at: new Date().toISOString(),
    });
    await loadSessions();
    renderMessages();
    showToast("Reply saved to history", "success");
  } finally {
    state.messages = state.messages.filter((item) => !item.loading);
    renderMessages();
    setBusy(false);
  }
}

function autoResizeInput() {
  el.chatInput.style.height = "auto";
  el.chatInput.style.height = `${Math.min(el.chatInput.scrollHeight, 140)}px`;
}

function bindEvents() {
  el.loginTab.addEventListener("click", () => {
    clearFormMessages();
    setAuthTab("login");
  });
  el.signupTab.addEventListener("click", () => {
    clearFormMessages();
    setAuthTab("signup");
  });
  el.googleLoginBtn.addEventListener("click", loginWithGoogle);
  el.logoutBtn.addEventListener("click", () => logout(true));

  el.newChatBtn.addEventListener("click", async () => {
    try {
      await createSession();
      el.chatInput.focus();
    } catch (error) {
      showError(error.message);
    }
  });

  el.reloadHistoryBtn.addEventListener("click", async () => {
    try {
      await loadWorkspace();
      showToast("Chats reloaded", "success");
    } catch (error) {
      showError(error.message);
    }
  });

  el.loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = document.querySelector("#login-email").value.trim();
    const password = document.querySelector("#login-password").value;
    clearFormMessages();
    try {
      await login(email, password);
      showToast("Logged in successfully", "success");
    } catch (error) {
      setFormMessage(el.loginMessage, error.message, "error");
      showError(error.message);
    }
  });

  el.signupForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = document.querySelector("#signup-email").value.trim();
    const password = document.querySelector("#signup-password").value;
    clearFormMessages();
    try {
      await signup(email, password);
      showToast("Account created", "success");
    } catch (error) {
      setFormMessage(el.signupMessage, error.message, "error");
      showError(error.message);
    }
  });

  el.chatInput.addEventListener("input", autoResizeInput);
  el.chatInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      el.chatForm.requestSubmit();
    }
  });

  el.chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = el.chatInput.value.trim();
    if (!message || state.loading) {
      return;
    }

    el.chatInput.value = "";
    autoResizeInput();

    try {
      await sendMessage(message);
    } catch (error) {
      showError(error.message);
    }
  });

  document.querySelectorAll(".prompt-chip").forEach((button) => {
    button.addEventListener("click", () => {
      el.chatInput.value = button.textContent.trim();
      autoResizeInput();
      el.chatInput.focus();
    });
  });
}

async function handleGoogleCallback() {
  const params = new URLSearchParams(window.location.search);
  const idToken = params.get("id_token");
  if (!idToken) {
    return false;
  }

  setToken(idToken);
  window.history.replaceState({}, document.title, window.location.pathname);
  await loadProfile();
  await loadWorkspace();
  showToast("Logged in with Google", "success");
  return true;
}

async function init() {
  bindEvents();
  renderShell();

  try {
    const handledGoogle = await handleGoogleCallback();
    if (!handledGoogle && token()) {
      await loadProfile();
      await loadWorkspace();
    }
  } catch (error) {
    logout(false);
    showError(error.message);
  }

  renderShell();
}

window.addEventListener("load", () => {
  renderMessages();
});

init();
