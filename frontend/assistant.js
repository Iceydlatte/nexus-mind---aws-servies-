(() => {
  const chat = document.getElementById("task-chat");
  const orb = document.getElementById("task-orb");
  const form = document.getElementById("chatForm");
  const input = document.getElementById("chatInput");
  const send = form?.querySelector(".chat-send");
  const log = document.getElementById("chatLog");
  const close = document.getElementById("chatClose");
  if (!chat || !orb || !form || !input || !send || !log) return;

  chat.setAttribute("aria-label", "Nexus Mind AI assistant");
  document.querySelector(".chatname").textContent = "Nexus Mind assistant";
  document.querySelector(".chatmeta").textContent = "AI productivity companion";
  document.getElementById("chatVoiceState").textContent = "AI READY";
  input.placeholder = "Ask about your tasks…";
  input.setAttribute("aria-label", "Message the Nexus Mind AI assistant");
  orb.setAttribute("aria-label", "Open Nexus Mind assistant");
  orb.title = "Open task assistant";
  const hint = document.querySelector(".chat-hint");
  hint.textContent = "Ask anything about planning, focus, study habits, or your signed-in tasks.";

  const prompts = document.createElement("div");
  prompts.className = "quick-prompts";
  prompts.setAttribute("aria-label", "Suggested messages");
  for (const text of ["What tasks are pending?", "Add a task", "What’s complete?"]) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = text;
    button.addEventListener("click", () => {
      input.value = text;
      form.requestSubmit();
    });
    prompts.append(button);
  }
  hint.before(prompts);

  function addMessage(text, role, extraClass = "") {
    const bubble = document.createElement("div");
    bubble.className = `bubble ${role} ${extraClass}`.trim();
    bubble.textContent = text;
    log.append(bubble);
    log.scrollTop = log.scrollHeight;
    return bubble;
  }

  function openChat() {
    chat.classList.add("open");
    if (window.matchMedia("(min-width: 621px)").matches) placePopover(chat, orb);
    orb.setAttribute("aria-expanded", "true");
    if (!log.children.length) {
      addMessage("Hi! I’m your Nexus Mind AI companion. I can help you plan, think through problems, and manage your tasks. What’s on your mind?", "agent");
    }
    input.focus();
  }

  orb.onclick = () => {
    if (orb.dataset.dragged === "1") { orb.dataset.dragged = "0"; return; }
    if (chat.classList.contains("open")) {
      chat.classList.remove("open");
      orb.setAttribute("aria-expanded", "false");
    } else openChat();
  };
  close.onclick = () => {
    chat.classList.remove("open");
    orb.setAttribute("aria-expanded", "false");
  };

  form.onsubmit = async (event) => {
    event.preventDefault();
    const message = input.value.trim();
    if (!message || send.disabled) return;
    addMessage(message, "user");
    input.value = "";
    send.disabled = true;
    send.textContent = "…";
    const pending = addMessage("Checking your tasks…", "agent", "pending");
    try {
      if (!window.NexusCloud?.sendAssistantMessage) throw new Error("The AWS assistant is not available. Refresh the page and try again.");
      const result = await window.NexusCloud.sendAssistantMessage(message);
      pending.textContent = result.reply || "I couldn’t find a response. Please try again.";
      pending.classList.remove("pending");
      document.getElementById("chatVoiceState").textContent = "READY";
    } catch (error) {
      pending.textContent = error.message || "Something went wrong while contacting the assistant.";
      pending.classList.remove("pending");
      pending.classList.add("error");
      document.getElementById("chatVoiceState").textContent = "RETRY";
    } finally {
      send.disabled = false;
      send.textContent = "Send";
      input.focus();
      log.scrollTop = log.scrollHeight;
    }
  };

  window.addEventListener("nexus:tasks-updated", (event) => {
    if (!Array.isArray(event.detail?.tasks)) return;
    window.applyAssistantTasks?.(event.detail.tasks);
  });

  document.querySelectorAll(".nav").forEach((button) => {
    const label = button.textContent.replace(/^[^\p{L}\p{N}]+/u, "").replace(/\s+/g, " ").trim();
    button.title = label;
    button.setAttribute("aria-label", label);
  });
  window.addEventListener("resize", () => {
    if (chat.classList.contains("open") && window.matchMedia("(min-width: 621px)").matches) placePopover(chat, orb);
  });
})();
