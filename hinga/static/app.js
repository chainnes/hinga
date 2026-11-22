const state = {
  boot: null,
  view: "today",
  entries: [],
  insight: null,
  search: null,
  safety: null,
  draft: "",
  mood: "",
  route: "journal",
  turn: null,
  busy: false,
  error: "",
  status: "",
};

const app = document.querySelector("#app");

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value == null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else node.setAttribute(key, String(value));
  }
  for (const child of [].concat(children)) {
    if (child == null || child === false) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

function messageOf(data) {
  if (!data) return "The desk couldn't do that.";
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail.map((item) => item.msg || "Check that field.").join(" ");
  }
  return "The desk couldn't do that.";
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(messageOf(data));
  return data;
}

function longDate(iso) {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
}

function captureDraft() {
  const note = document.querySelector("#note");
  const mood = document.querySelector("input[name=mood]:checked");
  if (note) state.draft = note.value;
  if (mood) state.mood = mood.value;
}

function shell() {
  const boot = state.boot;
  const userId = boot.user && boot.user.id;
  app.replaceChildren(
    el("header", { class: "top" }, [
      el("div", { class: "brand" }, [
        el("img", { class: "mark", src: "/static/favicon.svg", alt: "" }),
        el("div", {}, [
          el("h1", {}, ["Hinga"]),
          el("p", {}, ["Notes, habits, and a reflection that has to cite your own pages."]),
        ]),
      ]),
      el("nav", { class: "nav", "aria-label": "Desk" }, [
        navButton("today", "Today"),
        navButton("journal", "Journal"),
        navButton("habits", "Habits"),
        navButton("recall", "Recall"),
      ]),
    ]),
    el("div", { class: "personas" }, [
      el("span", { class: "meta" }, ["Reading as"]),
      ...boot.personas.map((person) =>
        el(
          "button",
          {
            type: "button",
            "aria-pressed": person.id === userId ? "true" : "false",
            onClick: () => switchPerson(person.id),
          },
          [person.display_name],
        ),
      ),
      el("span", { class: "meta" }, [boot.llm_label]),
      el("button", { type: "button", class: "ghost", onClick: onExport }, ["Export"]),
      el("button", { type: "button", class: "ghost", onClick: onDelete }, ["Delete my data"]),
    ]),
    boot.user && boot.user.profile
      ? el("p", { class: "meta" }, [`Values: ${boot.user.profile.values}`])
      : null,
    el("p", { class: "meta", id: "status", "aria-live": "polite" }, [state.error || state.status]),
    el("div", { id: "stage" }),
  );
  const status = document.querySelector("#status");
  if (state.error) status.dataset.kind = "error";
  document.querySelector("#disclaimer").textContent = boot.disclaimer;
}

function navButton(view, label) {
  return el(
    "button",
    {
      type: "button",
      "aria-current": state.view === view ? "page" : null,
      onClick: () => goto(view),
    },
    [label],
  );
}

function paint() {
  shell();
  const stage = document.querySelector("#stage");
  if (state.view === "today") stage.append(todayView());
  else if (state.view === "journal") stage.append(journalView());
  else if (state.view === "habits") stage.append(habitsView());
  else stage.append(recallView());
  app.removeAttribute("aria-busy");
}

function safetyBlock(payload) {
  return el("section", { class: "hold", id: "safety" }, [
    el("p", { class: "kicker" }, ["Support"]),
    el("h2", {}, [payload.title]),
    el("p", {}, [payload.message]),
    el(
      "ul",
      { class: "resources" },
      payload.resources.map((item) =>
        el("li", {}, [
          item.href
            ? el("a", { href: item.href, rel: item.href.startsWith("http") ? "noopener noreferrer" : null }, [item.name])
            : el("strong", {}, [item.detail]),
          item.href ? el("p", {}, [item.detail]) : null,
        ]),
      ),
    ),
    el("p", { class: "fine" }, [
      "Lines change. If one does not connect, try the next. Hinga is not an emergency service.",
    ]),
    el("p", { class: "fine" }, [payload.disclaimer]),
  ]);
}

function reflectionCard(reflection, label) {
  if (!reflection) {
    return el("article", { class: "card" }, [
      el("p", { class: "kicker" }, ["Reflection"]),
      el("h3", {}, ["Nothing to cite yet."]),
      el("p", {}, ["Save a note. If an earlier page is close, it has to be quoted here, not invented."]),
    ]);
  }
  const source = reflection.fallback
    ? "Offline draft — the live model didn't return a valid reflection."
    : reflection.source === "llm"
      ? "Live model, schema-checked"
      : "Offline draft";
  return el("article", { class: "card", id: "reflection" }, [
    el("p", { class: "kicker" }, [label || "Reflection"]),
    el("p", { class: "source" }, [source]),
    el("h3", {}, [reflection.summary]),
    el("ul", { class: "themes" }, reflection.themes.map((theme) => el("li", {}, [theme]))),
    el("p", {}, [reflection.pattern_note]),
    ...reflection.citations.slice(0, 1).map((cite) =>
      el("blockquote", {}, [
        el("span", { class: "overlap" }, [`${cite.date_label} · overlap ${cite.overlap.toFixed(2)}`]),
        el("p", {}, [cite.excerpt]),
      ]),
    ),
    el("p", { class: "prompt" }, [reflection.gentle_prompt]),
    el("p", { class: "fine" }, [reflection.disclaimer]),
  ]);
}

function habitRow(habit, { strips }) {
  return el("article", { class: "habit" }, [
    el("div", {}, [
      el("h3", {}, [habit.name]),
      el("p", {}, [
        `${habit.done_days}/${habit.window_days} · streak ${habit.streak}. ${habit.intention}`,
      ]),
      habit.shrunk ? el("p", {}, ["Smaller this week, after several misses."]) : null,
      habit.reframe ? el("p", {}, [habit.reframe]) : null,
      strips ? strip(habit) : null,
    ]),
    el(
      "button",
      {
        type: "button",
        class: habit.days.find((day) => day.is_today && day.done) ? "primary" : "ghost",
        onClick: () => onToggle(habit.habit_id),
        disabled: state.busy,
      },
      [habit.days.find((day) => day.is_today && day.done) ? "Marked today" : "Mark today"],
    ),
  ]);
}

function strip(habit) {
  return el(
    "div",
    { class: "strip", "aria-hidden": "true" },
    habit.days.map((day) =>
      el("span", { class: day.is_today ? "day today" : "day" }, [
        day.label.slice(0, 2),
        el("span", { class: day.done ? "dot on" : "dot" }),
      ]),
    ),
  );
}

function todayView() {
  const wrap = el("div", { class: "layout" });
  const latest = state.entries.find((entry) => entry.reflection);
  const sheet = el("section", { class: "sheet" }, [
    el("p", { class: "kicker" }, ["Today"]),
    el("h2", {}, [longDate(state.boot.today)]),
    state.safety ? safetyBlock(state.safety) : null,
    el(
      "div",
      { class: "moods", role: "radiogroup", "aria-label": "What to run" },
      [
        ["journal", "Journal"],
        ["mindfulness", "Breath"],
        ["habit", "Habit"],
        ["insights", "Week"],
      ].map(([value, label]) =>
        el(
          "button",
          {
            type: "button",
            class: state.route === value ? "primary" : "ghost",
            onClick: () => {
              captureDraft();
              state.route = value;
              paint();
            },
          },
          [label],
        ),
      ),
    ),
    el("p", { class: "field" }, ["How does the day feel?"]),
    el(
      "div",
      { class: "moods", role: "radiogroup", "aria-label": "Mood" },
      [
        ["1", "Heavy"],
        ["2", "Low"],
        ["3", "Steady"],
        ["4", "Light"],
        ["5", "Bright"],
      ].map(([value, label]) =>
        el("label", { class: "mood" }, [
          el("input", {
            type: "radio",
            name: "mood",
            value,
            checked: state.mood === value ? "checked" : null,
          }),
          el("span", {}, [label]),
        ]),
      ),
    ),
    el("label", { class: "field", for: "note" }, ["What happened, in your own words."]),
    el("textarea", { id: "note" }, []),
    el("div", { class: "actions" }, [
      el("button", { type: "button", class: "primary", onClick: onSave, disabled: state.busy }, [
        state.busy ? "Reading earlier notes…" : "Save and reflect",
      ]),
      el("button", { type: "button", class: "ghost", onClick: useSample }, ["Use a sample note"]),
    ]),
    el("div", { class: "habits-inline" }, (state.insight ? state.insight.habits : []).map((habit) => habitRow(habit, { strips: false }))),
    el(
      "button",
      { type: "button", class: "ghost", onClick: onPreview, style: "margin-top:0.8rem" },
      ["Preview the crisis screen"],
    ),
  ]);
  const note = sheet.querySelector("#note");
  note.value = state.draft;
  wrap.append(
    sheet,
    sideCard(latest),
  );
  return wrap;
}

function sideCard(latest) {
  const turn = state.turn;
  if (turn && turn.exercise) {
    return el("article", { class: "card", id: "exercise" }, [
      el("p", { class: "kicker" }, [`${turn.exercise.minutes} min`]),
      el("h3", {}, [turn.exercise.name]),
      el("p", {}, [turn.exercise.note || ""]),
      el("p", { style: "white-space:pre-wrap" }, [turn.exercise.script]),
    ]);
  }
  if (turn && turn.route === "insights") {
    return el("article", { class: "card" }, [
      el("p", { class: "kicker" }, ["This week"]),
      el("p", {}, [turn.week_note]),
    ]);
  }
  if (turn && turn.habit_note) {
    return el("article", { class: "card" }, [
      el("p", { class: "kicker" }, ["Habit"]),
      el("p", {}, [turn.habit_note]),
    ]);
  }
  if (turn && turn.entry && turn.entry.analysis_status === "unanalyzed") {
    return el("article", { class: "card" }, [
      el("p", { class: "kicker" }, ["Saved"]),
      el("h3", {}, ["The note is kept. The analysis did not fit the schema."]),
    ]);
  }
  return reflectionCard(latest && latest.reflection, latest ? `Latest reflection · ${latest.date_label}` : "Reflection");
}

function journalView() {
  const shown = state.entries.slice(0, 20);
  const wrap = el("section", { class: "journal" }, [
    el("h2", {}, ["On paper"]),
    el("p", { class: "empty" }, [
      state.entries.length
        ? `${state.entries.length} notes on this desk. Showing ${shown.length}.`
        : "Nothing on paper yet. The desk is clear.",
    ]),
  ]);
  for (const entry of shown) {
    const body = [
      el("summary", {}, [`${entry.date_label} · ${entry.mood_label}`]),
      el("p", {}, [entry.body]),
    ];
    if (entry.safety_hold) {
      body.push(el("p", { class: "fine" }, ["Held. No reflection was written."]));
      body.push(
        el("button", { type: "button", class: "ghost", onClick: () => showStoredSupport(entry.id) }, [
          "Show support lines",
        ]),
      );
      const slot = el("div", { id: `hold-${entry.id}` });
      body.push(slot);
    } else if (entry.reflection) {
      body.push(el("p", {}, [entry.reflection.pattern_note]));
      body.push(el("p", { class: "prompt" }, [entry.reflection.gentle_prompt]));
    }
    wrap.append(el("article", { class: "entry" }, [el("details", {}, body)]));
  }
  return wrap;
}

function habitsView() {
  const insight = state.insight;
  const wrap = el("section", { class: "habits-page" });
  wrap.append(el("h2", {}, ["Habits"]));
  if (!insight) {
    wrap.append(el("p", { class: "empty" }, ["No habits on this desk yet."]));
    return wrap;
  }
  wrap.append(
    el("article", { class: "card" }, [
      el("p", { class: "source" }, [insight.fallback ? "Offline counts" : insight.source === "llm" ? "Live model, counts locked" : "Counts from the desk"]),
      el("p", {}, [insight.observation]),
      el("p", { class: "prompt" }, [insight.one_small_step]),
      insight.week_note ? el("p", {}, [insight.week_note]) : null,
      el("p", { class: "fine" }, [insight.disclaimer]),
    ]),
  );
  for (const habit of insight.habits) wrap.append(habitRow(habit, { strips: true }));
  return wrap;
}

function recallView() {
  const wrap = el("section", { class: "recall" }, [
    el("h2", {}, ["Recall"]),
    el("p", { class: "empty" }, [
      "Search is limited to this person's notes. The offline score follows shared wording and a small theme list, not a neural model.",
    ]),
    el("form", { class: "search", onSubmit: onSearch }, [
      el("input", {
        id: "query",
        type: "search",
        name: "q",
        placeholder: "Try “desk lunch” or “baby”",
        "aria-label": "Search your notes",
        value: state.search ? state.search.query : "",
      }),
      el("button", { class: "primary", type: "submit" }, ["Search"]),
    ]),
  ]);
  const input = wrap.querySelector("#query");
  input.value = state.search ? state.search.query : "";
  if (!state.search) {
    wrap.append(el("p", { class: "empty" }, ["Switch person and run the same phrase. The other desk should stay closed."]));
    return wrap;
  }
  if (!state.search.results.length) {
    wrap.append(el("p", { class: "empty" }, ["No earlier note is close to that."]));
    return wrap;
  }
  for (const hit of state.search.results) {
    wrap.append(
      el("article", { class: "hit" }, [
        el("h3", {}, [hit.date_label]),
        el("p", { class: "overlap" }, [`overlap ${hit.overlap.toFixed(2)}`]),
        el("p", {}, [hit.excerpt]),
      ]),
    );
  }
  return wrap;
}

async function loadDesk() {
  const [entries, insight] = await Promise.all([api("/api/entries"), api("/api/habits")]);
  state.entries = entries.entries;
  state.insight = insight;
}

async function boot() {
  try {
    let data = await api("/api/bootstrap");
    if (!data.user) data = await api("/api/session", { method: "POST", body: JSON.stringify({ user_id: "maya" }) });
    state.boot = data;
    await loadDesk();
    paint();
  } catch (error) {
    app.replaceChildren(el("p", { class: "status", "data-kind": "error" }, [error.message]));
  }
}

async function goto(view) {
  captureDraft();
  state.view = view;
  state.error = "";
  if (view !== "today") state.safety = null;
  try {
    if (view === "habits" || view === "today") await loadDesk();
  } catch (error) {
    state.error = error.message;
  }
  paint();
}

async function switchPerson(userId) {
  if (state.boot.user && state.boot.user.id === userId) return;
  state.busy = true;
  state.error = "";
  state.safety = null;
  state.search = null;
  state.draft = "";
  state.mood = "";
  try {
    state.boot = await api("/api/session", { method: "POST", body: JSON.stringify({ user_id: userId }) });
    await loadDesk();
    state.status = `${state.boot.user.display_name}'s notes only.`;
  } catch (error) {
    state.error = error.message;
  } finally {
    state.busy = false;
    paint();
  }
}

function useSample() {
  state.draft = state.boot.sample_note;
  state.mood = state.mood || "2";
  paint();
}

async function onSave() {
  captureDraft();
  state.error = "";
  if (state.route === "journal" && !state.draft.trim()) {
    state.error = "Write a few words first.";
    paint();
    return;
  }
  if ((state.route === "journal" || state.route === "mindfulness") && !state.mood) {
    state.error = "Pick a mark for how the day feels.";
    paint();
    return;
  }
  state.busy = true;
  paint();
  try {
    const saved = await api("/api/turn", {
      method: "POST",
      body: JSON.stringify({
        route: state.route,
        body: state.draft,
        mood: state.mood ? Number(state.mood) : null,
      }),
    });
    state.turn = saved;
    state.draft = "";
    state.safety = saved.safety;
    await loadDesk();
    state.status = saved.safety ? "Note saved. Reflection stopped." : "Note saved.";
  } catch (error) {
    state.error = error.message;
  } finally {
    state.busy = false;
    paint();
  }
}

async function onToggle(habitId) {
  state.busy = true;
  state.error = "";
  captureDraft();
  try {
    const result = await api(`/api/habits/${habitId}/toggle`, { method: "POST" });
    state.insight = result.insight;
    state.status = result.done_today ? "Marked for today." : "Taken off today.";
  } catch (error) {
    state.error = error.message;
  } finally {
    state.busy = false;
    paint();
  }
}

async function onSearch(event) {
  event.preventDefault();
  const query = new FormData(event.currentTarget).get("q");
  state.error = "";
  try {
    state.search = await api(`/api/search?q=${encodeURIComponent(query)}`);
  } catch (error) {
    state.error = error.message;
  }
  paint();
}

async function onPreview() {
  captureDraft();
  try {
    state.safety = await api("/api/safety/preview", { method: "POST" });
    state.view = "today";
    state.error = "";
  } catch (error) {
    state.error = error.message;
  }
  paint();
  document.querySelector("#safety")?.scrollIntoView({ block: "nearest" });
}

async function showStoredSupport(entryId) {
  try {
    const payload = await api("/api/resources?stored=true");
    const slot = document.querySelector(`#hold-${entryId}`);
    if (slot) slot.replaceChildren(safetyBlock(payload));
  } catch (error) {
    state.error = error.message;
    paint();
  }
}

async function onExport() {
  try {
    const data = await api("/api/me/export");
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = el("a", { href: url, download: `hinga-${state.boot.user.id}.json` });
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    state.status = "Export downloaded. It is your copy of the decrypted notes.";
  } catch (error) {
    state.error = error.message;
  }
  paint();
}

async function onDelete() {
  const name = state.boot.user.display_name;
  if (!window.confirm(`Delete ${name}'s notes, habits, and profile from this desk? This cannot be undone.`)) return;
  try {
    await api("/api/me/delete", { method: "POST" });
    state.turn = null;
    state.draft = "";
    await loadDesk();
    state.boot = await api("/api/bootstrap");
    state.status = "Those notes, habits, and the profile are gone from this desk.";
  } catch (error) {
    state.error = error.message;
  }
  paint();
}

boot();
