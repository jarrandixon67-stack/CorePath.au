const specialists = [
  ["Personal Development", "🌱", "Goals, habits, motivation and self-awareness", ["Habits", "Motivation", "Self-awareness"]],
  ["Physical Development", "🏃", "Movement, strength, fitness and mobility", ["Strength", "Mobility", "Movement"]],
  ["Nutrition", "🥑", "Food quality, nutrition and preparation", ["Whole foods", "Nutrition science", "Food production", "Food preservation"]],
  ["Mental Wellbeing", "🧠", "Emotional awareness and psychological wellbeing", ["Emotional regulation", "Stress and resilience", "Psychology"]],
  ["Relationships", "🤝", "Communication, family and social connection", ["Communication", "Family relationships", "Conflict resolution"]],
  ["Learning & Intelligence", "💡", "Learning, thinking and problem-solving", ["Memory", "Critical thinking", "Creativity"]],
  ["Financial Capability", "📈", "Financial literacy and informed decisions", ["Budgeting", "Investing principles", "Financial independence"]],
  ["Career & Business", "🧭", "Employment, entrepreneurship and leadership", ["Leadership", "Business development", "Career planning"]],
  ["Practical Life Skills", "🛠️", "Gardening, self-sufficiency and practical skills", ["Growing vegetables", "Seed saving", "Survival skills"]],
  ["Parenting & Family", "🏡", "Parenting and child development", ["Child development", "Parenting approaches", "Family wellbeing"]],
  ["Recreation & Discovery", "🌄", "Hobbies, outdoors and exploration", ["Outdoor skills", "Hobbies", "Adventure"]]
];

const sampleSources = {
  "Nutrition": [
    ["The Omnivore's Dilemma", "Michael Pollan", "Book · 2006", "Reference only", "Whole foods"],
    ["In Defense of Food", "Michael Pollan", "Book · 2008", "Reference only", "Whole foods"],
    ["Dietary patterns and health", "Research collection", "Research · Illustrative", "To review", "Nutrition science"]
  ],
  "Physical Development": [
    ["Built to Move", "Kelly & Juliet Starrett", "Book · 2023", "Reference only", "Mobility"],
    ["Exercise and physical function", "Research collection", "Research · Illustrative", "To review", "Movement"]
  ],
  "Practical Life Skills": [
    ["The Vegetable Gardener's Bible", "Edward C. Smith", "Book · 2009", "Reference only", "Growing vegetables"],
    ["Seed saving principles", "Traditional knowledge collection", "Knowledge · Illustrative", "To review", "Seed saving"]
  ]
};

const app = document.querySelector("#app");
const nav = document.querySelector("#specialist-nav");
let activeView = "overview";
let activeLibrary = null;

nav.innerHTML = specialists.map(s =>
  '<button class="nav-link specialist" data-library="' + s[0] + '"><span class="mini">' + s[1] + '</span>' + s[0] + '</button>'
).join("");

function setCrumb(value) {
  document.querySelector("#crumb-current").textContent = value;
}

function setNav() {
  document.querySelectorAll(".nav-link").forEach(button => {
    button.classList.toggle("active", button.dataset.view === activeView || button.dataset.library === activeLibrary);
  });
}

function overview() {
  activeView = "overview";
  activeLibrary = null;
  setCrumb("Overview");
  setNav();
  app.innerHTML = `
    <div class="hero">
      <div><div class="eyebrow">THE KNOWLEDGE ENGINE · OVERVIEW</div><h1>Intelligence Centre</h1><p>A living knowledge system supporting every CorePath specialist.</p></div>
      <div class="hero-note">Discover, organise, compare and apply knowledge — while keeping every finding traceable to its source.</div>
    </div>
    <div class="metrics">
      <div class="metric"><span class="label">SPECIALIST LIBRARIES</span><strong>11</strong><small>One for each life area</small></div>
      <div class="metric"><span class="label">REGISTERED SOURCES</span><strong>0</strong><small>Live database records</small></div>
      <div class="metric"><span class="label">RESEARCH PROJECTS</span><strong>0</strong><small>No live projects yet</small></div>
      <div class="metric"><span class="label">SYSTEM STATUS</span><strong style="font-size:19px">Foundation</strong><small><span class="status-dot"></span>Prototype environment</small></div>
    </div>
    <div class="section-head"><h2>Specialist libraries</h2><span class="subtle">Select a library to explore →</span></div>
    <div class="library-grid">${specialists.map((s, i) => `<button class="library-card" data-open="${i}"><div class="lib-icon">${s[1]}</div><strong>${s[0]}</strong><small>${s[2]}</small><div class="card-foot"><span class="tag">Knowledge library</span><span class="arrow">↗</span></div></button>`).join("")}</div>
    <div class="lower-grid">
      <div class="panel"><h3>Recent system activity</h3>
        <div class="activity"><div class="activity-icon">▤</div><div><strong>Eleven specialist libraries established</strong><small>Knowledge infrastructure · Foundation milestone</small></div></div>
        <div class="activity"><div class="activity-icon">⌁</div><div><strong>Shared source registry created</strong><small>Sources can be linked across specialist areas</small></div></div>
        <div class="activity"><div class="activity-icon">✓</div><div><strong>Automated backend checks</strong><small>Database and API tests configured</small></div></div>
      </div>
      <div class="panel"><h3>How knowledge develops</h3><div class="research-note">Discover a source → assess its quality and context → extract useful material → compare with other sources → record findings and uncertainty → make knowledge traceable to its origin.<br><br><b>Our principle:</b> preserve differences in evidence rather than forcing agreement.</div></div>
    </div>`;
  app.querySelectorAll("[data-open]").forEach(button => button.onclick = () => library(Number(button.dataset.open)));
}

function library(index) {
  activeView = "libraries";
  activeLibrary = specialists[index][0];
  setCrumb(activeLibrary);
  setNav();

  const specialist = specialists[index];
  const sources = sampleSources[specialist[0]] || [];
  const categories = specialist[3];

  app.innerHTML = `
    <button class="back" id="back">← Back to overview</button>
    <div class="library-hero">
      <div><div class="eyebrow" style="color:#b7cfc0">SPECIALIST KNOWLEDGE LIBRARY</div><h1>${specialist[1]} ${specialist[0]}</h1><p>${specialist[2]}</p></div>
      <span class="pill">FOUNDATION LIBRARY</span>
    </div>
    <div class="library-info three-metrics">
      <div class="info-box"><small>REGISTERED SOURCES</small><strong>${sources.length}</strong><small>Illustrative entries</small></div>
      <div class="info-box"><small>VERIFIED RECORDS</small><strong>0</strong><small>Requires evidence review</small></div>
      <div class="info-box"><small>RESEARCH FINDINGS</small><strong>0</strong><small>Accepted findings</small></div>
    </div>
    <div class="section-head category-heading"><div><h2>Knowledge categories</h2><span class="subtle">Open a category to explore its contents.</span></div><button class="primary" id="add-source">＋ Add source</button></div>
    <div class="toolbar"><input class="search" id="source-search" placeholder="Search categories and sources..."><select class="filter" id="source-filter"><option value="">All source types</option><option>Book</option><option>Research</option><option>Knowledge</option></select></div>
    <div id="category-list"></div>
    <div class="lower-grid">
      <div class="panel"><h3>Evidence and verification</h3><div class="research-note">A registered source is not automatically a verified finding. We separately assess source quality, methods, limitations, context and supporting or conflicting evidence.</div></div>
      <div class="panel"><h3>Research principles</h3><div class="research-note">Compare different disciplines and traditions. Record uncertainty and disagreement. Distinguish established evidence, emerging research, traditional knowledge, professional opinion and unverified claims.</div></div>
    </div>
    <p class="prototype-note">Prototype content only. Sample entries are illustrative and are not stored in the live database.</p>`;

  document.querySelector("#back").onclick = overview;
  document.querySelector("#add-source").onclick = () => sourceModal(specialist[0], categories);
  document.querySelector("#source-search").oninput = () => renderCategories(categories, sources);
  document.querySelector("#source-filter").onchange = () => renderCategories(categories, sources);
  renderCategories(categories, sources);
}

function renderCategories(categories, sources) {
  const query = document.querySelector("#source-search").value.toLowerCase();
  const filter = document.querySelector("#source-filter").value;
  const visible = sources.filter(source =>
    source.join(" ").toLowerCase().includes(query) && (!filter || source[2].startsWith(filter))
  );
  const list = document.querySelector("#category-list");
  const shownCategories = categories.filter(category =>
    category.toLowerCase().includes(query) || visible.some(source => source[4] === category)
  );

  list.innerHTML = shownCategories.map((category, index) => {
    const entries = visible.filter(source => source[4] === category);
    return `
      <details class="category-row" ${index === 0 ? "open" : ""}>
        <summary><span class="category-folder">▤</span><span class="category-name">${category}</span><span class="category-count">${entries.length} source${entries.length === 1 ? "" : "s"}</span><span class="category-chevron">⌄</span></summary>
        <div class="category-content">
          ${entries.length ? entries.map(source => `
            <div class="source-row"><div class="source-symbol">▤</div><div class="source-main"><strong>${source[0]}</strong><small>${source[1]} · ${source[2]}</small></div><span class="tag">${source[3]}</span></div>
          `).join("") : '<div class="category-empty">No sources in this category yet. Use Add source to begin building it.</div>'}
        </div>
      </details>`;
  }).join("") || '<div class="empty">No categories or sources match this search.</div>';
}

function sourceModal(libraryName, categories) {
  const overlay = document.createElement("div");
  overlay.className = "modal-backdrop";
  overlay.innerHTML = `
    <form class="modal">
      <button type="button" class="modal-close" aria-label="Close">×</button>
      <div class="eyebrow">SOURCE REGISTRY</div><h2>Add a source</h2>
      <p class="subtle">Add a reference to the ${libraryName} library. This is a local prototype interaction; it does not yet save to the live database.</p>
      <label>Source title<input required name="title" placeholder="Book, paper or resource title"></label>
      <label>Author / organisation<input name="author" placeholder="Author or publisher"></label>
      <label>Category<select name="category">${categories.map(category => `<option>${category}</option>`).join("")}</select></label>
      <label>Source type<select name="type"><option>Book</option><option>Research paper</option><option>Report</option><option>Website</option><option>Manual</option><option>Other</option></select></label>
      <label>URL or DOI<input name="url" placeholder="https:// or DOI (optional)"></label>
      <div class="modal-actions"><button type="button" class="secondary cancel">Cancel</button><button class="primary">Add to preview</button></div>
    </form>`;
  document.body.append(overlay);
  const close = () => overlay.remove();
  overlay.querySelector(".modal-close").onclick = close;
  overlay.querySelector(".cancel").onclick = close;
  overlay.onclick = event => { if (event.target === overlay) close(); };
  overlay.querySelector("form").onsubmit = event => {
    event.preventDefault();
    alert("Source details captured in this demonstration. Database saving will be connected in a later integration step.");
    close();
  };
}

function research() {
  activeView = "research";
  activeLibrary = null;
  setCrumb("Research activity");
  setNav();
  app.innerHTML = `<div class="hero"><div><div class="eyebrow">DISCOVERY · EVALUATION · SYNTHESIS</div><h1>Research activity</h1><p>Understand what specialists are investigating and how findings are evaluated.</p></div></div><div class="empty"><div style="font-size:30px;margin-bottom:10px">⌕</div><b>No active research projects yet</b><p>The research workspace will show questions, source reviews, evidence comparisons and findings as these capabilities are built.</p></div>`;
}

function libraries() {
  activeView = "libraries";
  activeLibrary = null;
  setCrumb("Knowledge libraries");
  setNav();
  app.innerHTML = `<div class="hero"><div><div class="eyebrow">ELEVEN CONNECTED DOMAINS</div><h1>Knowledge libraries</h1><p>Choose a specialist area to explore its knowledge collection.</p></div></div><div class="library-grid">${specialists.map((s, i) => `<button class="library-card" data-open="${i}"><div class="lib-icon">${s[1]}</div><strong>${s[0]}</strong><small>${s[2]}</small><div class="card-foot"><span class="tag">Open library</span><span class="arrow">↗</span></div></button>`).join("")}</div>`;
  app.querySelectorAll("[data-open]").forEach(button => button.onclick = () => library(Number(button.dataset.open)));
}

document.querySelectorAll("[data-view]").forEach(button => {
  button.onclick = () => ({ overview, libraries, research })[button.dataset.view]();
});
nav.querySelectorAll("[data-library]").forEach(button => {
  button.onclick = () => library(specialists.findIndex(s => s[0] === button.dataset.library));
});
overview();
