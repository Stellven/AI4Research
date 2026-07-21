const ENDPOINTS = ["http://127.0.0.1:8788", "http://127.0.0.1:8765"];

chrome.action.onClicked.addListener(async (tab) => {
  await setBadge("...", "#666666");
  try {
    if (!tab.id) throw new Error("No active tab");
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: capturePage,
    });
    if (!result || !result.ok) throw new Error(result?.error || "Capture failed");

    const response = result.kind === "chatgpt"
      ? await postJson("/chatgpt-import", result.payload)
      : await postWebCapture(result.payload);

    if (!response.ok) throw new Error(response.error || "Solar capture failed");
    await setBadge("OK", "#1f7a3a");
    console.log("Solar Knowledge Capture OK", response);
  } catch (error) {
    await setBadge("ERR", "#b42318");
    console.error("Solar Knowledge Capture failed", error);
  } finally {
    setTimeout(() => chrome.action.setBadgeText({ text: "" }), 3000);
  }
});

async function setBadge(text, color) {
  await chrome.action.setBadgeText({ text });
  await chrome.action.setBadgeBackgroundColor({ color });
}

async function postJson(path, payload) {
  let lastError = "";
  for (const base of ENDPOINTS) {
    try {
      const res = await fetch(base + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (res.ok && data.ok) return data;
      lastError = data.error || `${res.status} ${res.statusText}`;
    } catch (error) {
      lastError = String(error);
    }
  }
  return { ok: false, error: lastError || "Solar capture server is not running" };
}

async function postForm(path, fields) {
  let lastError = "";
  const body = new URLSearchParams(fields);
  for (const base of ENDPOINTS) {
    try {
      const res = await fetch(base + path, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body,
      });
      const data = await res.json();
      if (res.ok && data.ok) return data;
      lastError = data.error || `${res.status} ${res.statusText}`;
    } catch (error) {
      lastError = String(error);
    }
  }
  return { ok: false, error: lastError || "Solar capture server is not running" };
}

async function postWebCapture(payload) {
  const structured = await postJson("/capture-json", payload);
  if (structured.ok) return structured;
  return postForm("/capture", {
    title: payload.title,
    source_url: payload.url,
    content: payload.content,
  });
}

async function capturePage() {
  const clean = (value) => String(value || "")
    .replace(/\u00a0/g, " ")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  const normalizeLines = (value) => clean(value)
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .join("\n");
  const sha256Hex = async (value) => {
    try {
      const bytes = new TextEncoder().encode(value);
      const digest = await crypto.subtle.digest("SHA-256", bytes);
      return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, "0")).join("");
    } catch (_) {
      let hash = 0;
      for (let i = 0; i < value.length; i += 1) hash = ((hash << 5) - hash + value.charCodeAt(i)) | 0;
      return `fallback-${Math.abs(hash)}`;
    }
  };
  const textFrom = (node) => clean(node?.innerText || node?.textContent || "");
  const firstMeta = (selectors) => {
    for (const selector of selectors) {
      const node = document.querySelector(selector);
      const value = node?.getAttribute("content") || node?.getAttribute("datetime") || node?.textContent || "";
      if (clean(value)) return clean(value);
    }
    return "";
  };
  const collectMetadata = () => ({
    description: firstMeta(["meta[name='description']", "meta[property='og:description']"]),
    site_name: firstMeta(["meta[property='og:site_name']"]),
    author: firstMeta(["meta[name='author']", "meta[property='article:author']"]),
    published_at: firstMeta(["meta[property='article:published_time']", "time[datetime]"]),
    language: document.documentElement?.lang || "",
    canonical_url: document.querySelector("link[rel='canonical']")?.href || location.href,
  });
  const stripChatGPTBoilerplate = (value) => {
    const noise = [
      /^chatgpt can make mistakes/i,
      /^check important info/i,
      /^share$/i,
      /^copy$/i,
      /^edit$/i,
      /^regenerate$/i,
      /^try again$/i,
      /^good response$/i,
      /^bad response$/i,
      /^read aloud$/i,
      /^ask anything$/i,
      /^message chatgpt$/i,
      /^search$/i,
    ];
    return normalizeLines(value)
      .split("\n")
      .filter((line) => !noise.some((pattern) => pattern.test(line.trim())))
      .join("\n")
      .trim();
  };
  const chatgptMessageText = (node) => {
    const candidates = [
      node.querySelector("[data-message-content]"),
      node.querySelector(".markdown"),
      node.querySelector("[class*='markdown']"),
      node.querySelector(".whitespace-pre-wrap"),
      node,
    ].filter(Boolean);
    const best = candidates
      .map((candidate) => stripChatGPTBoilerplate(textFrom(candidate)))
      .filter(Boolean)
      .sort((a, b) => b.length - a.length)[0] || "";
    return best;
  };
  const messageIdFor = (node) => {
    const holder = node.closest("[data-message-id], [data-testid*='conversation-turn']");
    return node.getAttribute("data-message-id") || holder?.getAttribute("data-message-id") || holder?.getAttribute("data-testid") || "";
  };
  const extractConversationId = () => {
    const match = location.pathname.match(/\/c\/([^/?#]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  };
  const collectRoleMessages = () => {
    const messages = [];
    const seen = new Set();
    for (const node of Array.from(document.querySelectorAll("[data-message-author-role]"))) {
      const role = node.getAttribute("data-message-author-role") || "";
      if (!["user", "assistant"].includes(role)) continue;
      const text = chatgptMessageText(node);
      const key = `${role}\n${text}`;
      if (!text || text.length < 2 || seen.has(key)) continue;
      seen.add(key);
      messages.push({
        turn_index: messages.length + 1,
        role,
        text,
        message_id: messageIdFor(node),
      });
    }
    return messages;
  };
  const collectChatGPTTurns = () => {
    const selectors = [
      "[data-testid*='conversation-turn']",
      "main article",
      "article",
      "main [class*='group']",
    ];
    const turns = [];
    const seen = new Set();
    for (const selector of selectors) {
      for (const node of Array.from(document.querySelectorAll(selector))) {
        const roleNode = node.querySelector("[data-message-author-role]");
        let role = roleNode?.getAttribute("data-message-author-role") || "";
        const text = stripChatGPTBoilerplate(textFrom(roleNode || node));
        if (!text || text.length < 20) continue;
        if (!role) {
          const label = text.slice(0, 120).toLowerCase();
          role = label.startsWith("you") || label.startsWith("user") ? "user" : "assistant";
        }
        if (!["user", "assistant"].includes(role)) continue;
        const key = `${role}\n${text}`;
        if (seen.has(key)) continue;
        seen.add(key);
        turns.push({ turn_index: turns.length + 1, role, text, message_id: messageIdFor(node) });
      }
      if (turns.length) break;
    }
    return turns;
  };
  const collectReadablePageText = () => {
    const selectors = ["article", "main", "[role='main']", ".post-content", ".entry-content", "body"];
    const candidates = selectors
      .map((selector) => normalizeLines(Array.from(document.querySelectorAll(selector))
        .map((node) => node.innerText || node.textContent || "")
        .join("\n\n")))
      .filter(Boolean);
    return candidates.sort((a, b) => b.length - a.length)[0] || "";
  };
  const url = location.href;
  const title = document.title || "Untitled Page";
  const isChatGPT = /(^|\.)chatgpt\.com$|(^|\.)chat\.openai\.com$/.test(location.hostname);
  const metadata = collectMetadata();
  const selectedText = clean(window.getSelection?.().toString() || "");
  let captureMethod = "chatgpt-role-attribute";
  let messages = isChatGPT ? collectRoleMessages() : [];

  if (isChatGPT && !messages.length) {
    captureMethod = "chatgpt-turn-fallback";
    messages = collectChatGPTTurns();
  }

  if (isChatGPT && messages.length) {
    const contentHash = await sha256Hex(JSON.stringify(messages.map(({ role, text }) => ({ role, text }))));
    return {
      ok: true,
      kind: "chatgpt",
      payload: {
        source: "chrome-extension",
        capture_schema_version: 2,
        url,
        canonical_url: metadata.canonical_url,
        conversation_id: extractConversationId(),
        title,
        captured_at: new Date().toISOString(),
        capture_method: captureMethod,
        message_count: messages.length,
        content_hash: contentHash,
        selected_text: selectedText,
        metadata,
        messages,
      },
    };
  }

  const content = collectReadablePageText();
  if (!content) return { ok: false, error: "No page text found" };
  const contentHash = await sha256Hex(`${metadata.canonical_url || url}\n${content}`);
  return {
    ok: true,
    kind: "web",
    payload: {
      source: "chrome-extension",
      capture_schema_version: 2,
      url,
      canonical_url: metadata.canonical_url,
      title,
      captured_at: new Date().toISOString(),
      capture_method: "readable-dom",
      content_hash: contentHash,
      selected_text: selectedText,
      metadata,
      content,
    },
  };
}
