"use strict";

const byId = id => document.getElementById(id);
const base = "/v1/persy";
const thread = byId("thread");
const privacy = byId("privacy");
const consent = byId("consent");
let active = null;
let revision = 0;
let busy = false;

async function api(path, method = "GET", body) {
  const response = await fetch(path, {
    method,
    headers: body === undefined ? {} : {"Content-Type": "application/json"},
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  const result = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    const error = new Error(typeof result.detail === "string" ? result.detail : "Request failed.");
    error.status = response.status;
    throw error;
  }
  return result;
}

async function run(action) {
  if (busy) return;
  busy = true;
  byId("status").textContent = "Working…";
  try {
    byId("status").textContent = await action() || "";
  } catch (error) {
    if (error.status === 401) signedOut();
    byId("status").textContent = error.message;
  } finally {
    busy = false;
  }
}

function signedOut() {
  active = null;
  thread.replaceChildren();
  byId("profile-items").replaceChildren();
  byId("conversations").replaceChildren();
  byId("metrics").textContent = "";
  byId("admin").hidden = true;
  for (const id of ["login", "chat", "privacy", "consent"]) byId(id).reset();
  byId("member").hidden = true;
  byId("login").hidden = false;
}

function append(parent, tag, text) {
  const node = document.createElement(tag);
  node.textContent = text;
  parent.append(node);
  return node;
}

function button(parent, label, action) {
  const node = append(parent, "button", label);
  node.type = "button";
  node.onclick = () => run(action);
  return node;
}

function renderResearch(parent, result) {
  append(parent, "p", result.message);
  if (result.assessed_domains?.length) {
    append(parent, "p", "Specialists assessed: " + result.assessed_domains.join(", "));
  }
  for (const card of [...(result.findings || []), ...(result.options || [])]) {
    append(parent, "p", card.statement || card.action);
    if (card.limitations) append(parent, "p", card.limitations);
    for (const citation of card.citations || []) {
      append(parent, "p", [citation.quote, citation.canonical_url || citation.source_title].filter(Boolean).join(" · "));
    }
  }
  for (const text of [...(result.clarifying_questions || []), ...(result.knowledge_gaps || []), ...(result.disagreements || [])]) {
    append(parent, "p", text);
  }
}

function renderReply(parent, result) {
  append(parent, "h3", "Percy");
  append(parent, "p", result.message);
  for (const step of result.next_steps || []) append(parent, "p", step);
  if (result.follow_up) append(parent, "p", result.follow_up);
}

function renderTurn(message, result, turnId, saved) {
  const card = append(thread, "article", "");
  append(card, "h3", "You");
  append(card, "p", message);
  if (saved && turnId) {
    const label = append(card, "label", " Select for Life Profile analysis");
    const check = document.createElement("input");
    check.type = "checkbox";
    check.value = turnId;
    label.prepend(check);
  }
  renderReply(card, result);
  if (result.research_proposal) {
    const proposal = result.research_proposal;
    const conversation = active;
    append(card, "h4", "Review specialist research");
    append(card, "p", "Only submit a general research question without identifying details.");
    append(card, "p", proposal.question);
    const approve = button(card, "Send this question to the Coordinator", async () => {
      const research = await api(base + "/conversations/" + conversation + "/research/" + proposal.id, "POST", {approve: true});
      approve.disabled = true;
      renderResearch(card, research);
    });
  }
}

async function openConversation(id) {
  active = id || null;
  byId("delete-chat").disabled = !active;
  thread.replaceChildren();
  if (!active) return;
  const {turns} = await api(base + "/conversations/" + active);
  for (const turn of turns) {
    if (turn.assistant_reply) renderTurn(turn.user_message, {...turn.assistant_reply, research_proposal: null}, turn.turn_id, true);
    if (turn.research_reply) renderResearch(append(thread, "article", ""), turn.research_reply);
  }
}

async function refreshConversations(selected) {
  const select = byId("conversations");
  const {conversations} = await api(base + "/conversations");
  select.replaceChildren(new Option("New conversation", ""));
  for (const conversation of conversations) {
    const label = new Date(conversation.created_at).toLocaleString();
    select.add(new Option(label, conversation.id));
  }
  select.value = selected || "";
}

async function enter() {
  const state = await api(base + "/privacy");
  revision = state.revision;
  for (const [key, value] of Object.entries(state.privacy)) {
    if (privacy.elements[key]) privacy.elements[key].checked = value;
  }
  if (state.revision) await refreshConversations();
  byId("login").hidden = true;
  byId("member").hidden = false;
  const flags = await api("/trial/flags");
  byId("admin").hidden = !flags.administrator;
}

byId("login").onsubmit = event => {
  event.preventDefault();
  run(async () => {
    const body = Object.fromEntries(new FormData(event.target));
    event.target.reset();
    await api("/trial/session", "POST", body);
    await enter();
  });
};

privacy.onsubmit = event => {
  event.preventDefault();
  run(async () => {
    const body = {expected_revision: revision, communication_style: "plain"};
    for (const input of privacy.querySelectorAll("input")) body[input.name] = input.checked;
    const state = await api(base + "/privacy", "PUT", body);
    revision = state.revision;
    if (!body.history_enabled) thread.replaceChildren();
    return "Privacy preferences saved.";
  });
};

byId("new-chat").onclick = () => run(async () => {
  byId("conversations").value = "";
  await openConversation(null);
});
byId("conversations").onchange = event => run(() => openConversation(event.target.value));
byId("delete-chat").onclick = () => run(async () => {
  if (!active || !confirm("Delete this conversation?")) return;
  await api(base + "/conversations/" + active, "DELETE");
  await refreshConversations();
  await openConversation(null);
});
byId("chat").onsubmit = event => {
  event.preventDefault();
  run(async () => {
    const form = event.target;
    if (!active) {
      const created = await api(base + "/conversations", "POST");
      active = created.conversation_id;
      await refreshConversations(active);
      byId("delete-chat").disabled = false;
    }
    const message = form.elements.message.value;
    const result = await api(base + "/conversations/" + active + "/messages", "POST", {
      message, use_profile_context: form.elements.profile.checked, max_specialists: 3
    });
    form.elements.message.value = "";
    renderTurn(message, result, result.turn_id, result.history_saved);
  });
};

for (const category of [
  "health_wellbeing", "relationships_connections", "pets_animals", "culture_heritage",
  "personal_growth_development", "career_finances", "nature_environment", "home_living",
  "other_connections_interests"
]) {
  const label = append(byId("categories"), "label", " " + category.replaceAll("_", " "));
  const input = document.createElement("input");
  input.type = "checkbox";
  input.name = "categories";
  input.value = category;
  label.prepend(input);
}

consent.onsubmit = event => {
  event.preventDefault();
  run(async () => {
    const formData = new FormData(consent);
    const body = {purpose: formData.get("purpose"), categories: formData.getAll("categories")};
    for (const input of consent.querySelectorAll("input[type=checkbox]:not([name=categories])")) {
      body[input.name] = input.checked;
    }
    await api(base + "/profile/consent", "PUT", body);
    return "Life Profile consent saved.";
  });
};

async function reviewProfile() {
  const {items, consent: saved} = await api(base + "/profile");
  for (const input of consent.querySelectorAll("input")) {
    if (input.name === "categories") input.checked = saved.categories.includes(input.value);
    else if (input.type === "checkbox") input.checked = saved[input.name];
    else input.value = saved[input.name];
  }
  const root = byId("profile-items");
  root.replaceChildren();
  for (const item of items) {
    const card = append(root, "article", "");
    append(card, "p", item.state + " · " + item.category.replaceAll("_", " "));
    const label = append(card, "label", "Life Profile statement");
    const statement = append(label, "textarea", "");
    statement.value = item.statement;
    statement.maxLength = 1000;
    const shareLabel = append(card, "label", " Share with Percy");
    const share = document.createElement("input");
    share.type = "checkbox";
    share.checked = item.shared_with_personal_ai;
    shareLabel.prepend(share);
    button(card, "Save approved statement", async () => {
      const corrected = statement.value.trim() !== item.statement;
      await api(base + "/profile/items/" + item.id + "/decision", "POST", {
        action: corrected ? "correct" : "accept",
        corrected_statement: corrected ? statement.value.trim() : null,
        expected_version: item.version,
        share_with_personal_ai: share.checked
      });
      await reviewProfile();
    });
    button(card, "Delete item", async () => {
      await api(base + "/profile/items/" + item.id, "DELETE");
      await reviewProfile();
    });
  }
}

byId("review").onclick = () => run(reviewProfile);
byId("analyse").onclick = () => run(async () => {
  const turnIds = [...thread.querySelectorAll("input:checked")].map(input => input.value);
  if (!turnIds.length || turnIds.length > 5) return "Select one to five saved messages.";
  if (!confirm("Send the selected messages to OpenAI for Life Profile analysis?")) return;
  await api(base + "/profile/analyse", "POST", {turn_ids: turnIds, purpose: consent.elements.purpose.value});
  await reviewProfile();
});
byId("delete-profile").onclick = () => run(async () => {
  if (!confirm("Delete your Life Profile and its consent settings?")) return;
  await api(base + "/profile", "DELETE");
  byId("profile-items").replaceChildren();
  consent.reset();
  return "Life Profile deleted.";
});
byId("logout").onclick = () => run(async () => {
  await api("/trial/session", "DELETE");
  signedOut();
});
byId("delete-account").onclick = () => run(async () => {
  if (!confirm("Permanently delete your trial account, stored conversations and Life Profile?")) return;
  await api("/trial/account", "DELETE");
  signedOut();
  return "Trial account deleted.";
});
byId("refresh-metrics").onclick = () => run(async () => {
  const services = await api("/trial/metrics");
  const root = byId("metrics");
  root.replaceChildren();
  for (const [service, operations] of Object.entries(services)) {
    append(root, "h3", service.replaceAll("_", " "));
    if (operations.status || !Object.keys(operations).length) {
      append(root, "p", operations.status ? "Metrics unavailable." : "No activity recorded.");
      continue;
    }
    const wrapper = append(root, "div", "");
    wrapper.className = "metrics-table";
    const table = append(wrapper, "table", "");
    const head = append(append(table, "thead", ""), "tr", "");
    for (const label of ["Operation", "Calls", "Errors", "Mean ms", "Input tokens", "Output tokens", "Est. USD"]) {
      append(head, "th", label).scope = "col";
    }
    const body = append(table, "tbody", "");
    for (const [name, values] of Object.entries(operations)) {
      const row = append(body, "tr", "");
      append(row, "th", name).scope = "row";
      const cost = values.estimated_usd_micros;
      for (const value of [
        values.calls, values.errors, Math.round(values.total_ms / values.calls),
        values.input_tokens, values.output_tokens, cost === undefined ? undefined : (cost / 1e6).toFixed(5)
      ]) {
        append(row, "td", value ?? "—");
      }
    }
  }
});

enter().catch(error => {
  signedOut();
  if (error.status !== 401) byId("status").textContent = error.message;
});
