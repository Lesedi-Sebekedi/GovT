(function () {
  "use strict";

  const listings = window.GOVVACANCY_LISTINGS;
  if (!Array.isArray(listings)) {
    throw new Error("Vacancy listing data failed to load.");
  }
  const savedStorageKey = "govvacancy-sa-saved";
  const searchInput = document.getElementById("search-input");
  const provinceFilter = document.getElementById("province-filter");
  const departmentFilter = document.getElementById("department-filter");
  const categoryFilter = document.getElementById("category-filter");
  const closingFilter = document.getElementById("closing-filter");
  const sortSelect = document.getElementById("sort-select");
  const vacancyList = document.getElementById("vacancy-list");
  const emptyState = document.getElementById("empty-state");
  const resultCount = document.getElementById("result-count");
  const resultLabel = document.getElementById("result-label");
  const savedToggle = document.getElementById("saved-toggle");
  const savedCount = document.getElementById("saved-count");
  const activeFilters = document.getElementById("active-filters");
  const closingList = document.getElementById("closing-list");
  const vacancyDialog = document.getElementById("vacancy-dialog");
  const dialogContent = document.getElementById("dialog-content");
  let savedIds = readSavedIds().filter((id) => listings.some((listing) => listing.id === id));
  let showingSaved = false;

  function readSavedIds() {
    try {
      const parsed = JSON.parse(window.localStorage.getItem(savedStorageKey) || "[]");
      return Array.isArray(parsed) ? parsed.filter((id) => typeof id === "string") : [];
    } catch (error) {
      console.error("Could not read saved vacancies from browser storage.", error);
      return [];
    }
  }

  function saveIds() {
    try {
      window.localStorage.setItem(savedStorageKey, JSON.stringify(savedIds));
    } catch (error) {
      console.error("Could not save vacancies to browser storage.", error);
    }
  }

  function formatDate(dateString, options) {
    return new Intl.DateTimeFormat("en-ZA", options || {
      day: "numeric",
      month: "long",
      year: "numeric"
    }).format(new Date(dateString + "T12:00:00"));
  }

  function daysUntil(dateString) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const closingDate = new Date(dateString + "T00:00:00");
    return Math.ceil((closingDate - today) / 86400000);
  }

  function addOptions(select, values) {
    values.sort((a, b) => a.localeCompare(b)).forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      select.appendChild(option);
    });
  }

  function populateFilters() {
    addOptions(provinceFilter, [...new Set(listings.map((item) => item.province))]);
    addOptions(departmentFilter, [...new Set(listings.map((item) => item.department))]);
    addOptions(categoryFilter, [...new Set(listings.map((item) => item.category))]);
  }

  function getFilteredListings() {
    const query = searchInput.value.trim().toLocaleLowerCase();
    const closingWithin = Number(closingFilter.value);
    let filtered = listings.filter((listing) => {
      const searchable = [
        listing.title,
        listing.department,
        listing.province,
        listing.location,
        listing.category,
        listing.salary,
        listing.reference,
        listing.summary,
        ...listing.requirements
      ].join(" ").toLocaleLowerCase();

      return (!query || searchable.includes(query)) &&
        (!provinceFilter.value || listing.province === provinceFilter.value) &&
        (!departmentFilter.value || listing.department === departmentFilter.value) &&
        (!categoryFilter.value || listing.category === categoryFilter.value) &&
        (!closingWithin || (daysUntil(listing.closingDate) >= 0 && daysUntil(listing.closingDate) <= closingWithin)) &&
        (!showingSaved || savedIds.includes(listing.id));
    });

    if (sortSelect.value === "title") {
      filtered = filtered.sort((a, b) => a.title.localeCompare(b.title));
    } else if (sortSelect.value === "newest") {
      filtered = filtered.sort((a, b) => b.publishedDate.localeCompare(a.publishedDate));
    } else {
      filtered = filtered.sort((a, b) => a.closingDate.localeCompare(b.closingDate));
    }
    return filtered;
  }

  function createTag(text, className) {
    const tag = document.createElement("span");
    tag.className = className;
    tag.textContent = text;
    return tag;
  }

  function createVacancyCard(listing) {
    const card = document.createElement("article");
    card.className = "vacancy-card";

    const top = document.createElement("div");
    top.className = "vacancy-card-top";
    const category = createTag(listing.category, "category-tag");
    const days = daysUntil(listing.closingDate);
    const closing = createTag(days < 0 ? "Closed" : days === 0 ? "Closes today" : days <= 3 ? "Closes in " + days + " days" : "Open", "closing-tag" + (days <= 3 ? " closing-urgent" : ""));
    top.append(category, closing);

    const title = document.createElement("h3");
    title.textContent = listing.title;
    const department = document.createElement("p");
    department.className = "vacancy-department";
    department.textContent = listing.department;

    const meta = document.createElement("div");
    meta.className = "vacancy-meta";
    meta.append(
      createMeta("⌖", listing.province + " · " + listing.location),
      createMeta("▤", listing.salary)
    );

    const footer = document.createElement("div");
    footer.className = "vacancy-card-footer";
    const deadline = document.createElement("p");
    deadline.className = "deadline";
    const deadlineLabel = document.createElement("span");
    deadlineLabel.textContent = "CLOSING DATE";
    const deadlineDate = document.createElement("strong");
    deadlineDate.textContent = formatDate(listing.closingDate, { day: "numeric", month: "short", year: "numeric" });
    deadline.append(deadlineLabel, deadlineDate);

    const actions = document.createElement("div");
    actions.className = "card-actions";
    const detailsButton = document.createElement("button");
    detailsButton.type = "button";
    detailsButton.className = "details-button";
    detailsButton.textContent = "View details";
    detailsButton.addEventListener("click", () => showDetails(listing));
    const saveButton = document.createElement("button");
    saveButton.type = "button";
    saveButton.className = "save-button" + (savedIds.includes(listing.id) ? " is-saved" : "");
    saveButton.setAttribute("aria-label", (savedIds.includes(listing.id) ? "Remove saved vacancy: " : "Save vacancy: ") + listing.title);
    saveButton.setAttribute("aria-pressed", String(savedIds.includes(listing.id)));
    saveButton.textContent = savedIds.includes(listing.id) ? "♥" : "♡";
    saveButton.addEventListener("click", () => toggleSaved(listing.id));
    actions.append(detailsButton, saveButton);
    footer.append(deadline, actions);

    card.append(top, title, department, meta, footer);
    return card;
  }

  function createMeta(icon, text) {
    const item = document.createElement("span");
    item.className = "meta-item";
    const mark = document.createElement("span");
    mark.className = "meta-icon";
    mark.setAttribute("aria-hidden", "true");
    mark.textContent = icon;
    const value = document.createElement("span");
    value.textContent = text;
    item.append(mark, value);
    return item;
  }

  function renderActiveFilters() {
    activeFilters.replaceChildren();
    if (showingSaved) activeFilters.append(createTag("Saved vacancies", "active-filter"));
    if (searchInput.value.trim()) activeFilters.append(createTag("Search: " + searchInput.value.trim(), "active-filter"));
    [provinceFilter, departmentFilter, categoryFilter].forEach((select) => {
      if (select.value) activeFilters.append(createTag(select.value, "active-filter"));
    });
    if (closingFilter.value) activeFilters.append(createTag("Closing in " + closingFilter.value + " days", "active-filter"));
  }

  function renderResults() {
    const filtered = getFilteredListings();
    vacancyList.replaceChildren(...filtered.map(createVacancyCard));
    resultCount.textContent = String(filtered.length);
    resultLabel.textContent = filtered.length === 1 ? "vacancy" : "vacancies";
    emptyState.hidden = filtered.length !== 0;
    vacancyList.hidden = filtered.length === 0;
    savedCount.textContent = String(savedIds.length);
    savedToggle.setAttribute("aria-pressed", String(showingSaved));
    savedToggle.classList.toggle("is-active", showingSaved);
    renderActiveFilters();
  }

  function toggleSaved(id) {
    savedIds = savedIds.includes(id) ? savedIds.filter((savedId) => savedId !== id) : [...savedIds, id];
    saveIds();
    renderResults();
  }

  function appendDetailRow(container, label, value) {
    const row = document.createElement("div");
    row.className = "detail-row";
    const key = document.createElement("dt");
    key.textContent = label;
    const content = document.createElement("dd");
    content.textContent = value;
    row.append(key, content);
    container.appendChild(row);
  }

  function showDetails(listing) {
    dialogContent.replaceChildren();
    const heading = document.createElement("p");
    heading.className = "eyebrow";
    heading.textContent = listing.category + " · " + listing.circular;
    const title = document.createElement("h2");
    title.id = "dialog-title";
    title.textContent = listing.title;
    const department = document.createElement("p");
    department.className = "dialog-department";
    department.textContent = listing.department + " · " + listing.province + " · " + listing.location;
    const summary = document.createElement("p");
    summary.className = "dialog-summary";
    summary.textContent = listing.summary;
    const facts = document.createElement("dl");
    facts.className = "detail-facts";
    appendDetailRow(facts, "Salary", listing.salary);
    appendDetailRow(facts, "Closing date", formatDate(listing.closingDate));
    appendDetailRow(facts, "Reference", listing.reference);

    const requirementsHeading = document.createElement("h3");
    requirementsHeading.textContent = "Requirements from the advertisement";
    const requirements = document.createElement("ul");
    requirements.className = "requirements-list";
    listing.requirements.forEach((requirement) => {
      const item = document.createElement("li");
      item.textContent = requirement;
      requirements.appendChild(item);
    });
    const sourceNotice = document.createElement("p");
    sourceNotice.className = "dialog-notice";
    sourceNotice.textContent = "Automatically extracted details can contain errors. The original DPSA advertisement is authoritative.";
    const source = document.createElement("a");
    source.className = "details-button source-button";
    source.href = listing.sourceUrl;
    source.target = "_blank";
    source.rel = "noreferrer";
    source.textContent = "Open official advertisement PDF ↗";
    dialogContent.append(heading, title, department, summary, facts, requirementsHeading, requirements, sourceNotice, source);
    vacancyDialog.showModal();
  }

  function renderClosingSoon() {
    const soon = listings
      .filter((listing) => daysUntil(listing.closingDate) >= 0)
      .sort((a, b) => a.closingDate.localeCompare(b.closingDate))
      .slice(0, 3);
    closingList.replaceChildren();
    soon.forEach((listing) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "closing-item";
      item.addEventListener("click", () => showDetails(listing));
      const date = document.createElement("span");
      date.className = "closing-date-box";
      date.innerHTML = "<strong></strong><span></span>";
      date.querySelector("strong").textContent = new Intl.DateTimeFormat("en-ZA", { day: "2-digit" }).format(new Date(listing.closingDate + "T12:00:00"));
      date.querySelector("span").textContent = new Intl.DateTimeFormat("en-ZA", { month: "short" }).format(new Date(listing.closingDate + "T12:00:00")).toUpperCase();
      const info = document.createElement("span");
      info.className = "closing-item-info";
      const title = document.createElement("strong");
      title.textContent = listing.title;
      const department = document.createElement("span");
      department.textContent = listing.department;
      info.append(title, department);
      item.append(date, info);
      closingList.appendChild(item);
    });
  }

  function resetFilters() {
    searchInput.value = "";
    provinceFilter.value = "";
    departmentFilter.value = "";
    categoryFilter.value = "";
    closingFilter.value = "";
    showingSaved = false;
    renderResults();
  }

  populateFilters();
  renderClosingSoon();
  renderResults();

  [searchInput, provinceFilter, departmentFilter, categoryFilter, closingFilter, sortSelect].forEach((control) => {
    control.addEventListener(control === searchInput ? "input" : "change", renderResults);
  });
  savedToggle.addEventListener("click", () => {
    showingSaved = !showingSaved;
    renderResults();
  });
  document.getElementById("reset-filters").addEventListener("click", resetFilters);
  document.getElementById("empty-reset").addEventListener("click", resetFilters);
  document.addEventListener("keydown", (event) => {
    if (event.key === "/" && document.activeElement !== searchInput && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault();
      searchInput.focus();
    }
  });
})();
