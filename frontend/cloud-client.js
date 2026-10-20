(() => {
  "use strict";

  const config = window.NEXUS_AWS_CONFIG || {};
  const enabled = config.enabled === true && config.region && config.userPoolId && config.userPoolClientId && config.apiUrl;
  const keys = {
    activities: "nexus-mind-offline-demo-v3",
    goals: "nexus-goals",
    tasks: "nexus-tasks",
    habits: "nexus-habits",
    reflections: "nexus-reflections",
    preferences: "nexus-preferences"
  };
  const authKey = "nexus-cloud-session-v1";
  const freshStartKey = "nexus-cloud-fresh-start";
  const eraseKey = "nexus-cloud-erased";
  const authEndpoint = `https://cognito-idp.${config.region}.amazonaws.com/`;
  let session = readSession();
  let syncTimer = null;
  let syncing = false;
  let syncQueued = false;
  let ready = false;
  let cloudVersion = 0;
  let conflicted = false;
  let signupEmail = "";
  let syntheticActivitiesReady = Promise.resolve();

  function readSession() {
    try { return JSON.parse(localStorage.getItem(authKey) || "null"); } catch { return null; }
  }
  function setStatus(message, isError = false) {
    const node = document.getElementById("cloudStatus");
    if (node) {
      node.textContent = message;
      node.style.color = isError ? "#f1a3a3" : "";
    }
  }
  function setSession(value) {
    session = value;
    if (session) localStorage.setItem(authKey, JSON.stringify(session));
    else localStorage.removeItem(authKey);
  }
  function parseJwt(token) {
    try { return JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))); }
    catch { return {}; }
  }
  async function cognito(action, parameters) {
    const result = await fetch(authEndpoint, {
      method: "POST",
      headers: {
        "content-type": "application/x-amz-json-1.1",
        "x-amz-target": `AWSCognitoIdentityProviderService.${action}`
      },
      body: JSON.stringify({ ClientId: config.userPoolClientId, ...parameters })
    });
    const data = await result.json().catch(() => ({}));
    if (!result.ok) {
      const messages = {
        "NotAuthorizedException": "Email or password is incorrect.",
        "UsernameExistsException": "An account already exists for this email.",
        "CodeMismatchException": "That confirmation code is incorrect.",
        "ExpiredCodeException": "That code expired. Request a new one from the sign-in screen.",
        "UserNotConfirmedException": "Confirm your email before signing in.",
        "InvalidPasswordException": "Use at least 10 characters with a number, uppercase, and lowercase letter.",
        "TooManyRequestsException": "Too many attempts. Wait a few minutes and try again."
      };
      const name = String(data.__type || "").split("#").pop();
      throw new Error(messages[name] || data.message || "AWS sign-in failed. Check the details and try again.");
    }
    return data;
  }
  async function refreshSession() {
    if (!session?.refreshToken) throw new Error("Your sign-in expired. Please sign in again.");
    const result = await cognito("InitiateAuth", {
      AuthFlow: "REFRESH_TOKEN_AUTH",
      AuthParameters: { REFRESH_TOKEN: session.refreshToken }
    });
    const tokens = result.AuthenticationResult;
    if (!tokens?.AccessToken || !tokens?.IdToken) throw new Error("Your sign-in expired. Please sign in again.");
    setSession({ ...session, accessToken: tokens.AccessToken, idToken: tokens.IdToken, expiresAt: Date.now() + (tokens.ExpiresIn || 3600) * 1000 });
  }
  async function api(path, method = "GET", body) {
    if (!session?.idToken) throw new Error("Please sign in first.");
    if (Date.now() > (session.expiresAt || 0) - 30_000) await refreshSession();
    const request = () => fetch(config.apiUrl.replace(/\/$/, "") + path, {
      method,
      headers: { authorization: `Bearer ${session.idToken}`, ...(body ? { "content-type": "application/json" } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {})
    });
    let result = await request();
    if (result.status === 401 && session.refreshToken) {
      await refreshSession();
      result = await request();
    }
    const payload = await result.json().catch(() => ({}));
    if (!result.ok) {
      const error = new Error(payload.error || `Cloud request failed (${result.status}).`);
      error.status = result.status;
      throw error;
    }
    return payload;
  }
  function currentData() {
    const data = {};
    for (const [name, key] of Object.entries(keys)) {
      const raw = localStorage.getItem(key);
      if (raw !== null) {
        try { data[name] = JSON.parse(raw); } catch { /* Ignore invalid local cache entries. */ }
      }
    }
    return data;
  }
  function sameData(a, b) {
    const canonical = value => Array.isArray(value)
      ? value.map(canonical)
      : value && typeof value === "object"
        ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]))
        : value;
    return JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));
  }
  function applyData(data) {
    for (const [name, key] of Object.entries(keys)) {
      if (Object.hasOwn(data, name)) localStorage.setItem(key, JSON.stringify(data[name]));
      else localStorage.removeItem(key);
    }
  }
  function clearPersonalCache() {
    for (const key of Object.values(keys)) localStorage.removeItem(key);
  }
  function setAccountControls(email) {
    const account = document.getElementById("accountControls");
    const emailNode = document.getElementById("accountEmail");
    if (account) account.hidden = !email;
    if (emailNode) emailNode.textContent = email || "";
  }
  function buildSignIn() {
    const style = document.createElement("style");
    style.textContent = `#cloudGate{position:fixed;inset:0;z-index:100;background:#080b10ed;display:none;place-items:center;padding:18px}#cloudGate.open{display:grid}.cloud-card{width:min(440px,100%);background:#121720;border:1px solid #303b49;border-radius:16px;padding:24px;box-shadow:0 20px 80px #000b}.cloud-card h1{font-size:22px;margin:4px 0 8px}.cloud-card p{color:#aab5c2;font-size:13px}.cloud-card .field{margin:13px 0}.cloud-card input{width:100%;padding:11px;background:#0c1117;border:1px solid #34404d;border-radius:8px;color:#edf2f7}.cloud-card button{margin-top:8px}.cloud-actions{display:flex;gap:8px;flex-wrap:wrap}.cloud-link{border:0;background:none;color:#91c9b2;text-decoration:underline;cursor:pointer;padding:8px 0}.cloud-error{color:#ffb3b3!important;min-height:18px}.cloud-card[hidden],.cloud-card form[hidden]{display:none!important}#accountControls{display:flex;align-items:center;gap:10px}#accountControls[hidden]{display:none}#accountEmail{max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#c3ced9}`;
    document.head.appendChild(style);
    const gate = document.createElement("div");
    gate.id = "cloudGate";
    gate.innerHTML = `<div class="cloud-card"><div class="eyebrow">NEXUS MIND · PRIVATE ACCOUNT</div><h1 id="cloudTitle">Sign in to sync your data</h1><p id="cloudIntro">Your activities, goals, tasks, habits, reflections, and preferences are saved to your AWS account so they follow you between devices.</p><div id="cloudError" class="cloud-error" role="status"></div><form id="signInForm"><div class="field"><label for="signInEmail">Email</label><input id="signInEmail" type="email" autocomplete="username" required></div><div class="field"><label for="signInPassword">Password</label><input id="signInPassword" type="password" autocomplete="current-password" required></div><button class="primary" type="submit">Sign in and sync</button><div><button class="cloud-link" type="button" data-mode="signup">Create an account</button></div></form><form id="signUpForm" hidden><div class="field"><label for="signUpEmail">Email</label><input id="signUpEmail" type="email" autocomplete="email" required></div><div class="field"><label for="signUpPassword">Password</label><input id="signUpPassword" type="password" autocomplete="new-password" minlength="10" required></div><p class="small">Use at least 10 characters, including a number, uppercase letter, and lowercase letter.</p><button class="primary" type="submit">Create account</button><div><button class="cloud-link" type="button" data-mode="signin">I already have an account</button></div></form><form id="confirmForm" hidden><div class="field"><label for="confirmCode">Email confirmation code</label><input id="confirmCode" inputmode="numeric" autocomplete="one-time-code" required></div><p class="small">AWS sent a code to <span id="confirmAddress"></span>.</p><button class="primary" type="submit">Confirm email</button><div><button class="cloud-link" type="button" data-mode="signin">Back to sign in</button></div></form><div class="small" style="margin-top:14px">Your data is private to your account. Sign out on shared devices.</div></div>`;
    document.body.appendChild(gate);
    const signIn = gate.querySelector("#signInForm");
    const signUp = gate.querySelector("#signUpForm");
    const confirm = gate.querySelector("#confirmForm");
    const recoveryLink = document.createElement("button");
    recoveryLink.className = "cloud-link";
    recoveryLink.type = "button";
    recoveryLink.textContent = "Forgot password?";
    signIn.appendChild(recoveryLink);
    const recovery = document.createElement("form");
    recovery.hidden = true;
    recovery.innerHTML = `<div class="field"><label for="recoveryEmail">Account email</label><input id="recoveryEmail" type="email" autocomplete="email" required></div><div id="recoveryCodeFields" hidden><div class="field"><label for="recoveryCode">Email code</label><input id="recoveryCode" inputmode="numeric" autocomplete="one-time-code"></div><div class="field"><label for="recoveryPassword">New password</label><input id="recoveryPassword" type="password" autocomplete="new-password" minlength="10"></div></div><button class="primary" type="submit">Send recovery code</button><div><button class="cloud-link" type="button" id="backToSignIn">Back to sign in</button></div>`;
    gate.querySelector(".cloud-card").appendChild(recovery);
    let recoveryCodeSent = false;
    const setMode = (mode) => {
      signIn.hidden = mode !== "signin";
      signUp.hidden = mode !== "signup";
      confirm.hidden = mode !== "confirm";
      gate.querySelector("#cloudError").textContent = "";
      gate.querySelector("#cloudTitle").textContent = mode === "signup" ? "Create your account" : mode === "confirm" ? "Check your email" : "Sign in to sync your data";
    };
    gate.querySelectorAll("[data-mode]").forEach(button => button.addEventListener("click", () => setMode(button.dataset.mode)));
    recoveryLink.addEventListener("click", () => {
      setMode("signin");
      signIn.hidden = true;
      recovery.hidden = false;
      gate.querySelector("#cloudTitle").textContent = "Reset your password";
      gate.querySelector("#recoveryEmail").value = gate.querySelector("#signInEmail").value;
    });
    recovery.querySelector("#backToSignIn").addEventListener("click", () => {
      recovery.hidden = true;
      recoveryCodeSent = false;
      recovery.querySelector("#recoveryCodeFields").hidden = true;
      recovery.querySelector("button[type=submit]").textContent = "Send recovery code";
      setMode("signin");
    });
    recovery.addEventListener("submit", async event => {
      event.preventDefault();
      const email = recovery.querySelector("#recoveryEmail").value.trim().toLowerCase();
      await runForm(recovery, async () => {
        if (!recoveryCodeSent) {
          await cognito("ForgotPassword", { Username: email });
          recoveryCodeSent = true;
          recovery.querySelector("#recoveryCodeFields").hidden = false;
          recovery.querySelector("#recoveryCode").required = true;
          recovery.querySelector("#recoveryPassword").required = true;
          recovery.querySelector("button[type=submit]").textContent = "Set new password";
          gate.querySelector("#cloudError").textContent = "Recovery code sent. Check your inbox.";
          return;
        }
        await cognito("ConfirmForgotPassword", {
          Username: email,
          ConfirmationCode: recovery.querySelector("#recoveryCode").value.trim(),
          Password: recovery.querySelector("#recoveryPassword").value
        });
        recovery.hidden = true;
        recoveryCodeSent = false;
        recovery.querySelector("#recoveryCodeFields").hidden = true;
        recovery.querySelector("button[type=submit]").textContent = "Send recovery code";
        setMode("signin");
        gate.querySelector("#signInEmail").value = email;
        gate.querySelector("#cloudError").textContent = "Password reset. Sign in with the new password.";
      });
    });
    signUp.addEventListener("submit", async event => {
      event.preventDefault();
      const email = gate.querySelector("#signUpEmail").value.trim().toLowerCase();
      const password = gate.querySelector("#signUpPassword").value;
      await runForm(signUp, async () => {
        await cognito("SignUp", { Username: email, Password: password, UserAttributes: [{ Name: "email", Value: email }] });
        signupEmail = email;
        gate.querySelector("#confirmAddress").textContent = email;
        setMode("confirm");
        gate.querySelector("#confirmCode").focus();
      });
    });
    confirm.addEventListener("submit", async event => {
      event.preventDefault();
      await runForm(confirm, async () => {
        await cognito("ConfirmSignUp", { Username: signupEmail || gate.querySelector("#signUpEmail").value.trim().toLowerCase(), ConfirmationCode: gate.querySelector("#confirmCode").value.trim() });
        setMode("signin");
        gate.querySelector("#signInEmail").value = signupEmail;
        gate.querySelector("#signInPassword").focus();
        gate.querySelector("#cloudError").textContent = "Email confirmed. Now sign in.";
      });
    });
    signIn.addEventListener("submit", async event => {
      event.preventDefault();
      const email = gate.querySelector("#signInEmail").value.trim().toLowerCase();
      const password = gate.querySelector("#signInPassword").value;
      await runForm(signIn, async () => {
        const result = await cognito("InitiateAuth", { AuthFlow: "USER_PASSWORD_AUTH", AuthParameters: { USERNAME: email, PASSWORD: password } });
        const tokens = result.AuthenticationResult;
        if (!tokens?.AccessToken || !tokens?.IdToken) throw new Error("AWS did not return a complete sign-in session.");
        setSession({ email, accessToken: tokens.AccessToken, idToken: tokens.IdToken, refreshToken: tokens.RefreshToken, expiresAt: Date.now() + (tokens.ExpiresIn || 3600) * 1000 });
        await hydrateFromCloud();
      });
    });
    gate.dataset.setMode = "signin";
    gate._setMode = setMode;
    return gate;
  }
  async function runForm(form, action) {
    const error = document.getElementById("cloudError");
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    error.textContent = "";
    try { await action(); }
    catch (cause) { error.textContent = cause.message || "Something went wrong. Try again."; }
    finally { button.disabled = false; }
  }
  async function hydrateFromCloud() {
    setStatus("Loading your cloud data…");
    const response = await api("/me/data");
    cloudVersion = response.version || 0;
    if (response.data) {
      const previous = currentData();
      applyData(response.data);
      if (!sameData(previous, currentData())) {
        location.reload();
        return;
      }
    } else if (sessionStorage.getItem(eraseKey)) {
      sessionStorage.removeItem(eraseKey);
    } else if (sessionStorage.getItem(freshStartKey)) {
      sessionStorage.removeItem(freshStartKey);
      const saved = await api("/me/data", "PUT", { data: currentData(), expectedVersion: cloudVersion });
      cloudVersion = saved.version;
    } else {
      const importLocal = confirm("This cloud account has no saved Nexus Mind data yet. Copy the saved activities, goals, tasks, habits, reflections, and preferences from this browser into your AWS account so they sync on other devices? Choose Cancel to start with a fresh cloud profile.");
      if (importLocal) {
        const saved = await api("/me/data", "PUT", { data: currentData(), expectedVersion: cloudVersion });
        cloudVersion = saved.version;
      } else {
        clearPersonalCache();
        sessionStorage.setItem(freshStartKey, "1");
        location.reload();
        return;
      }
    }
    ready = true;
    setAccountControls(session.email);
    setStatus("● Synced to your AWS account");
    document.getElementById("cloudGate")?.classList.remove("open");
  }
  function snapshotReport() {
    const visibleReport = window.NexusDemo?.getReport?.();
    if (visibleReport) {
      const { title, note, ...report } = visibleReport;
      return report;
    }
    const data = currentData();
    const rows = Array.isArray(data.activities) ? data.activities.slice(-7) : [];
    const sum = (key) => rows.reduce((total, row) => total + (Number(row[key]) || 0), 0);
    return {
      days: rows.length,
      avgProductivity: rows.length ? Math.round(rows.reduce((total, row) => total + (Number(row.score) || 0), 0) / rows.length) : 0,
      studyMinutes: sum("study_minutes"),
      entertainmentMinutes: sum("entertainment_minutes"),
      tasksCompleted: sum("tasks_completed"),
      tasksPlanned: sum("tasks_planned")
    };
  }
  function installReportButton() {
    const download = document.getElementById("downloadReport");
    if (!download || download.dataset.cloudEmailInstalled) return;
    download.dataset.cloudEmailInstalled = "1";
    const button = document.createElement("button");
    button.className = "secondary";
    button.type = "button";
    button.textContent = "Email summary to my account";
    button.title = "Send this summary to your verified sign-in email address";
    button.addEventListener("click", async () => {
      if (!ready) return alert("Sign in to email a report.");
      button.disabled = true;
      try {
        await syntheticActivitiesReady;
        const result = await api("/me/email-report", "POST", { report: snapshotReport() });
        alert(result.message || "Report sent.");
      } catch (error) { alert(error.message); }
      finally { button.disabled = false; }
    });
    download.after(button);
  }
  async function saveReport(report) {
    if (!ready) throw new Error("Sign in to save reports to AWS.");
    return api("/me/report", "POST", { report });
  }
  async function sendAssistantMessage(text) {
    if (!ready) throw new Error("Sign in to use the Nexus Mind AI assistant.");
    const result = await api("/me/assistant", "POST", { text });
    if (Array.isArray(result.tasks)) {
      localStorage.setItem(keys.tasks, JSON.stringify(result.tasks));
      if (Number.isInteger(result.version)) cloudVersion = result.version;
      window.dispatchEvent(new CustomEvent("nexus:tasks-updated", { detail: { tasks: result.tasks } }));
    }
    return result;
  }
  async function loadSyntheticActivities() {
    if (!enabled) return;
    try {
      const result = await fetch(config.apiUrl.replace(/\/$/, "") + "/synthetic/activities", { cache: "no-store" });
      if (!result.ok) throw new Error(`Dataset request failed (${result.status}).`);
      const payload = await result.json();
      if (Array.isArray(payload.activities) && payload.activities.length) window.NexusDemo?.replaceSynthetic(payload.activities);
    } catch (error) {
      console.warn("The S3 demo dataset could not be loaded; keeping the offline example rows.", error);
    }
  }
  async function flushSync() {
    if (!ready || !session || conflicted) return;
    if (syncing) { syncQueued = true; return; }
    syncing = true;
    do {
      syncQueued = false;
      setStatus("Saving to your AWS account…");
      try {
        const saved = await api("/me/data", "PUT", { data: currentData(), expectedVersion: cloudVersion });
        cloudVersion = saved.version;
        setStatus("● Synced to your AWS account");
      } catch (error) {
        if (error.status === 409) conflicted = true;
        setStatus(error.status === 409 ? "Newer data is saved on another device · Reload latest to sync" : `Sync needs attention: ${error.message}`, true);
      }
    } while (syncQueued && !conflicted);
    syncing = false;
  }
  function scheduleSync() {
    if (!ready || !session || conflicted) return;
    clearTimeout(syncTimer);
    syncTimer = setTimeout(() => { void flushSync(); }, 500);
  }
  async function signOut() {
    try { if (session?.accessToken) await cognito("GlobalSignOut", { AccessToken: session.accessToken }); } catch { /* Local sign-out still removes this browser session. */ }
    clearPersonalCache();
    setSession(null);
    ready = false;
    setAccountControls("");
    document.getElementById("cloudGate")?.classList.add("open");
    document.getElementById("cloudGate")?._setMode("signin");
    setStatus("Signed out · your account data remains in AWS");
  }
  function installAccountControls() {
    const status = document.getElementById("cloudStatus");
    const top = document.querySelector(".top");
    if (!top) return;
    if (status) status.textContent = enabled ? "● Cloud sync ready" : "● Offline demo · cloud not configured";
    const controls = document.createElement("span");
    controls.id = "accountControls";
    controls.hidden = true;
    controls.innerHTML = `<span id="accountEmail"></span><button class="secondary" type="button" id="cloudReload" title="Load the newest saved copy">Reload latest</button><button class="secondary" type="button" id="cloudSignOut">Sign out</button>`;
    top.appendChild(controls);
    controls.querySelector("#cloudSignOut").addEventListener("click", () => { void signOut(); });
    controls.querySelector("#cloudReload").addEventListener("click", () => {
      if (conflicted && !confirm("Reload the newest cloud copy? Unsaved changes on this device will be replaced.")) return;
      location.reload();
    });
  }
  function installCloudDelete() {
    const button = document.getElementById("deleteData");
    if (!button) return;
    button.textContent = "Delete my cloud data";
    button.onclick = async () => {
      if (!ready) return alert("Sign in before deleting your account data.");
      if (!confirm("Permanently delete your saved Nexus Mind data from AWS and clear this device's saved copy? This cannot be undone. Your account will remain active.")) return;
      button.disabled = true;
      try {
        await api("/me/data", "DELETE");
        clearPersonalCache();
        sessionStorage.setItem(eraseKey, "1");
        location.reload();
      } catch (error) { alert(error.message); }
      finally { button.disabled = false; }
    };
  }
  function start() {
    installAccountControls();
    syntheticActivitiesReady = loadSyntheticActivities();
    if (!enabled) {
      const deleteButton = document.getElementById("deleteData");
      if (deleteButton) deleteButton.textContent = "Clear local data";
      const sideInfo = document.querySelector(".sideinfo");
      if (sideInfo) sideInfo.innerHTML = `<span class="green">● Offline demo</span><br><br>Cloud sync is not configured. This browser keeps the local demo data.`;
      const dashboardBanner = document.querySelector("#dashboard .banner");
      if (dashboardBanner) dashboardBanner.innerHTML = `<b>Offline mode</b> · Changes stay in this browser until AWS sync is configured.`;
      const settingsCopy = document.querySelector("#deleteData")?.parentElement.querySelector(".sub");
      if (settingsCopy) settingsCopy.textContent = "This offline build stores data in this browser. Export a copy or clear local records and preferences.";
      return;
    }
    installReportButton();
    buildSignIn();
    installCloudDelete();
    if (!session?.accessToken) {
      document.getElementById("cloudGate").classList.add("open");
      return;
    }
    void hydrateFromCloud().catch(error => {
      setStatus(`Sign in needed: ${error.message}`, true);
      clearPersonalCache();
      setSession(null);
      document.getElementById("cloudGate")?.classList.add("open");
    });
  }
  window.NexusCloud = { scheduleSync, enabled, saveReport, sendAssistantMessage };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
