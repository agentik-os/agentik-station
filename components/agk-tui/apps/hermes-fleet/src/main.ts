import "./styles.css";

import {
  ORGANISATIONS,
  STORAGE_KEY,
  colorSchemeForHex,
  consolePath,
  dashboardPath,
  getOrganisation,
  resolveOrganisationId,
  withOrganisation,
  type OrganisationId,
} from "./organisations";

const appElement = document.querySelector<HTMLDivElement>("#app");

if (!appElement) {
  throw new Error("Application root is missing");
}

const app = appElement;

app.innerHTML = `
  <main class="fleet-shell">
    <header class="topbar">
      <a class="brand" href="/" aria-label="Hermes Fleet, accueil">
        <span class="brand-icon-shell" aria-hidden="true">
          <img
            class="brand-icon"
            src="/hermes-icon.webp"
            alt=""
            width="32"
            height="32"
            draggable="false"
          />
        </span>
        <span class="brand-copy">
          <strong>Hermes</strong>
          <small>Fleet</small>
        </span>
      </a>

      <div class="organisation-picker">
        <button
          class="organisation-trigger"
          type="button"
          aria-label="Changer d’organisation"
          aria-haspopup="menu"
          aria-expanded="false"
          aria-controls="organisation-menu"
        >
          <span class="status-dot" data-status-dot aria-hidden="true"></span>
          <span class="trigger-copy" aria-live="polite">
            <small>Organisation</small>
            <strong data-current-name>Operator</strong>
            <span data-current-description>Infrastructure et opérations</span>
          </span>
          <svg class="chevron" aria-hidden="true" viewBox="0 0 16 16" fill="none">
            <path d="m4 6 4 4 4-4" />
          </svg>
        </button>

        <div
          class="organisation-menu"
          id="organisation-menu"
          role="menu"
          aria-label="Choisir une organisation"
          hidden
        >
          <div class="menu-heading">
            <span>Espaces Hermes</span>
            <kbd>Esc</kbd>
          </div>
          <div class="menu-options">
            ${ORGANISATIONS.map(
              (organisation) => `
                <button
                  class="organisation-option"
                  type="button"
                  role="menuitemradio"
                  aria-checked="false"
                  data-organisation="${organisation.id}"
                >
                  <span
                    class="option-icon"
                    style="--organisation-accent: ${organisation.accent}"
                    aria-hidden="true"
                  >${organisation.label.slice(0, 1)}</span>
                  <span class="option-copy">
                    <strong>${organisation.label}</strong>
                    <small>${organisation.description}</small>
                  </span>
                  <svg class="option-check" aria-hidden="true" viewBox="0 0 16 16" fill="none">
                    <path d="m3 8 3 3 7-7" />
                  </svg>
                </button>
              `,
            ).join("")}
          </div>
          <p class="menu-note">
            Les sessions, secrets et connexions restent isolés dans chaque espace.
          </p>
        </div>
      </div>

      <div class="topbar-actions">
        <div class="tailnet-badge" aria-label="Connexion privée via Tailscale">
          <svg aria-hidden="true" viewBox="0 0 16 16" fill="none">
            <rect x="3.5" y="7" width="9" height="6.5" rx="2" />
            <path d="M5.5 7V5.25a2.5 2.5 0 0 1 5 0V7" />
          </svg>
          <span class="tailnet-dot" aria-hidden="true"></span>
          <span class="tailnet-label">Tailnet privé</span>
        </div>

        <a
          class="open-separately"
          data-open-separately
          href="#"
          target="_blank"
          rel="noopener noreferrer"
        >
          <svg aria-hidden="true" viewBox="0 0 16 16" fill="none">
            <path d="M6 3h7v7M13 3 5 11M11 9v4H3V5h4" />
          </svg>
          <span>Ouvrir séparément</span>
        </a>
      </div>
    </header>

    <section class="dashboard-stage" aria-label="Tableau de bord Hermes">
      <div class="dashboard-loading" data-loading role="status">
        <span class="loading-orbit" aria-hidden="true"></span>
        <span>Connexion à Hermes</span>
      </div>
      <iframe
        class="dashboard-frame"
        data-dashboard-frame
        title="Dashboard Hermes Operator"
        referrerpolicy="same-origin"
      ></iframe>
    </section>
  </main>
`;

function requiredElement<T extends Element>(selector: string): T {
  const element = app.querySelector<T>(selector);
  if (!element) {
    throw new Error(`Hermes Fleet UI element is missing: ${selector}`);
  }
  return element;
}

const trigger = requiredElement<HTMLButtonElement>(".organisation-trigger");
const menu = requiredElement<HTMLDivElement>(".organisation-menu");
const currentName = requiredElement<HTMLElement>("[data-current-name]");
const currentDescription = requiredElement<HTMLElement>(
  "[data-current-description]",
);
const statusDot = requiredElement<HTMLElement>("[data-status-dot]");
const openSeparately = requiredElement<HTMLAnchorElement>("[data-open-separately]");
const frame = requiredElement<HTMLIFrameElement>("[data-dashboard-frame]");
const loading = requiredElement<HTMLElement>("[data-loading]");
const options = Array.from(
  app.querySelectorAll<HTMLButtonElement>("[data-organisation]"),
);

const CONSOLE_FLAG = "agk-console";
const CONSOLE_WAIT_MS = 8_000;

let consoleObserver: MutationObserver | null = null;
let themeObserver: MutationObserver | null = null;
let consoleWaitTimeout: number | null = null;
let consoleBridgeGeneration = 0;
let consoleRequestPending = false;

function clearConsoleWait(): void {
  if (consoleWaitTimeout !== null) {
    window.clearTimeout(consoleWaitTimeout);
    consoleWaitTimeout = null;
  }
}

function cleanupConsoleBridge(): void {
  consoleBridgeGeneration += 1;
  consoleObserver?.disconnect();
  consoleObserver = null;
  themeObserver?.disconnect();
  themeObserver = null;
  clearConsoleWait();
}

function normalisedText(element: Element): string {
  return (element.textContent ?? "").replace(/\s+/g, " ").trim();
}

function syncShellColorScheme(frameDocument: Document): void {
  const computedStyle = frameDocument.defaultView?.getComputedStyle(
    frameDocument.documentElement,
  );
  const background =
    computedStyle?.getPropertyValue("--background-base").trim() ?? "";
  if (!background) {
    return;
  }
  document.documentElement.dataset.colorScheme = colorSchemeForHex(background);
}

function isChatLink(link: HTMLAnchorElement, frameWindow: Window): boolean {
  try {
    const pathname = new URL(link.href, frameWindow.location.href).pathname;
    return normalisedText(link) === "Chat" && /\/(?:chat)\/?$/.test(pathname);
  } catch {
    return false;
  }
}

function injectConsoleStyle(frameDocument: Document): void {
  if (frameDocument.getElementById("agk-console-nav-style")) {
    return;
  }

  const style = frameDocument.createElement("style");
  style.id = "agk-console-nav-style";
  style.textContent = `
    #app-sidebar [data-agk-console-nav] {
      width: 100%;
      padding: 0.5rem 0.625rem;
      border: 0;
      border-radius: calc(var(--radius, 0.625rem) - 2px);
      background: transparent;
      color: inherit;
      font-family: var(--theme-font-sans, ui-sans-serif, system-ui, sans-serif);
      font-size: 0.875rem;
      font-weight: 500;
      letter-spacing: -0.01em;
      text-align: left;
      text-transform: none;
      cursor: pointer;
    }

    #app-sidebar [data-agk-console-nav]:hover {
      background: color-mix(in srgb, currentColor 6%, transparent);
    }

    #app-sidebar [data-agk-console-nav]:focus-visible {
      outline: 2px solid var(--color-ring, currentColor);
      outline-offset: -2px;
    }

    #app-sidebar [data-agk-console-nav][aria-busy="true"] {
      cursor: progress;
      opacity: 0.66;
    }

    #app-sidebar .agk-console-glyph {
      display: inline-flex;
      width: 0.875rem;
      flex: 0 0 0.875rem;
      align-items: center;
      justify-content: center;
      font-family: var(--font-mono, ui-monospace, monospace);
      font-size: 0.6875rem;
      font-weight: 650;
      letter-spacing: -0.08em;
    }
  `;
  frameDocument.head.append(style);
}

function createConsoleNavButton(
  frameDocument: Document,
  chatLink: HTMLAnchorElement,
): HTMLButtonElement {
  const button = frameDocument.createElement("button");
  button.type = "button";
  button.dataset.agkConsoleNav = "true";
  button.className = chatLink.className;
  button.setAttribute("aria-label", "Open console");
  button.title = "Open console";

  const glyph = frameDocument.createElement("span");
  glyph.className = "agk-console-glyph";
  glyph.setAttribute("aria-hidden", "true");
  glyph.textContent = "›_";

  const label = frameDocument.createElement("span");
  const chatLabel = Array.from(chatLink.children).find(
    (child) => child.tagName === "SPAN" && !child.hasAttribute("aria-hidden"),
  );
  label.className = chatLabel?.className ?? "truncate";
  label.textContent = "Open console";

  button.append(glyph, label);
  button.addEventListener("click", () => {
    button.setAttribute("aria-busy", "true");
    consoleRequestPending = true;
    cleanupConsoleBridge();
    loading.hidden = false;
    frame.classList.remove("is-ready");
    frame.src = consolePath(activeId);
    frame.focus();
  });

  return button;
}

function ensureConsoleNavigation(
  frameDocument: Document,
  frameWindow: Window,
): HTMLButtonElement | null {
  const existing = Array.from(
    frameDocument.querySelectorAll<HTMLButtonElement>("[data-agk-console-nav]"),
  );
  const current = existing.shift() ?? null;
  for (const duplicate of existing) {
    duplicate.closest("li")?.remove();
  }
  if (current) {
    return current;
  }

  const chatLink = Array.from(
    frameDocument.querySelectorAll<HTMLAnchorElement>("#app-sidebar nav a[href]"),
  ).find((link) => isChatLink(link, frameWindow));
  const chatItem = chatLink?.closest("li");
  if (!chatLink || !chatItem || !chatItem.parentElement) {
    return null;
  }

  const item = frameDocument.createElement("li");
  const button = createConsoleNavButton(frameDocument, chatLink);
  item.dataset.agkConsoleNavItem = "true";
  item.append(button);
  chatItem.insertAdjacentElement("afterend", item);
  return button;
}

function findOfficialConsoleButton(
  frameDocument: Document,
): HTMLButtonElement | null {
  const operationsHeading = Array.from(
    frameDocument.querySelectorAll<HTMLElement>("h1, h2, h3, [role='heading']"),
  ).find((heading) => normalisedText(heading) === "Operations");
  const operationsSection = operationsHeading?.closest("section");
  if (!operationsSection) {
    return null;
  }

  return (
    Array.from(operationsSection.querySelectorAll<HTMLButtonElement>("button")).find(
      (button) => normalisedText(button) === "Open console",
    ) ?? null
  );
}

function hideOfficialConsoleButton(button: HTMLButtonElement): void {
  button.dataset.agkConsoleOriginal = "true";
  button.hidden = true;
  button.setAttribute("aria-hidden", "true");
  button.tabIndex = -1;
}

function consumeConsoleFlag(frameWindow: Window): void {
  const url = new URL(frameWindow.location.href);
  url.searchParams.delete(CONSOLE_FLAG);
  frameWindow.history.replaceState(frameWindow.history.state, "", url);
}

function installConsoleBridge(): void {
  cleanupConsoleBridge();

  let frameDocument: Document | null;
  let frameWindow: Window | null;
  try {
    frameDocument = frame.contentDocument;
    frameWindow = frame.contentWindow;
    if (!frameDocument?.documentElement || !frameWindow) {
      return;
    }
    const currentUrl = new URL(frameWindow.location.href);
    consoleRequestPending =
      consoleRequestPending || currentUrl.searchParams.get(CONSOLE_FLAG) === "1";
  } catch {
    return;
  }

  const documentForFrame = frameDocument;
  const windowForFrame = frameWindow;
  const generation = consoleBridgeGeneration;
  let reconcileQueued = false;

  injectConsoleStyle(documentForFrame);
  syncShellColorScheme(documentForFrame);

  themeObserver = new MutationObserver(() => {
    if (generation === consoleBridgeGeneration) {
      syncShellColorScheme(documentForFrame);
    }
  });
  themeObserver.observe(documentForFrame.documentElement, {
    attributes: true,
    attributeFilter: ["style"],
  });

  const reconcile = (): void => {
    if (generation !== consoleBridgeGeneration) {
      return;
    }

    syncShellColorScheme(documentForFrame);

    const consoleNav = ensureConsoleNavigation(documentForFrame, windowForFrame);
    if (consoleNav && consoleRequestPending) {
      consoleNav.setAttribute("aria-busy", "true");
    }

    const officialButton = findOfficialConsoleButton(documentForFrame);
    if (!officialButton) {
      return;
    }

    hideOfficialConsoleButton(officialButton);
    if (!consoleRequestPending) {
      return;
    }

    consoleRequestPending = false;
    clearConsoleWait();
    consumeConsoleFlag(windowForFrame);
    officialButton.click();
  };

  const scheduleReconcile = (): void => {
    if (reconcileQueued || generation !== consoleBridgeGeneration) {
      return;
    }
    reconcileQueued = true;
    queueMicrotask(() => {
      reconcileQueued = false;
      reconcile();
    });
  };

  consoleObserver = new MutationObserver(scheduleReconcile);
  consoleObserver.observe(documentForFrame.documentElement, {
    childList: true,
    subtree: true,
  });

  if (consoleRequestPending) {
    consoleWaitTimeout = window.setTimeout(() => {
      if (generation !== consoleBridgeGeneration) {
        return;
      }
      consoleRequestPending = false;
      const consoleNav = documentForFrame.querySelector<HTMLButtonElement>(
        "[data-agk-console-nav]",
      );
      consoleNav?.removeAttribute("aria-busy");
      consoleNav?.focus({ preventScroll: true });
      consoleWaitTimeout = null;
    }, CONSOLE_WAIT_MS);
  }

  reconcile();
}

let activeId = resolveOrganisationId(
  window.location.search,
  window.localStorage.getItem(STORAGE_KEY),
);

function closeMenu({ restoreFocus = false } = {}): void {
  menu.hidden = true;
  trigger.setAttribute("aria-expanded", "false");
  if (restoreFocus) {
    trigger.focus();
  }
}

function openMenu(): void {
  menu.hidden = false;
  trigger.setAttribute("aria-expanded", "true");
  const selected = options.find(
    (option) => option.dataset.organisation === activeId,
  );
  (selected ?? options[0])?.focus();
}

function setOrganisation(id: OrganisationId): void {
  const organisation = getOrganisation(id);
  const path = dashboardPath(id);

  activeId = id;
  currentName.textContent = organisation.label;
  currentDescription.textContent = organisation.description;
  statusDot.style.setProperty("--current-accent", organisation.accent);
  openSeparately.href = path;
  openSeparately.setAttribute(
    "aria-label",
    `Ouvrir le dashboard ${organisation.label} séparément`,
  );

  for (const option of options) {
    const isCurrent = option.dataset.organisation === id;
    option.setAttribute("aria-checked", String(isCurrent));
    option.classList.toggle("is-current", isCurrent);
  }

  window.localStorage.setItem(STORAGE_KEY, id);
  const nextSearch = withOrganisation(window.location.search, id);
  window.history.replaceState(null, "", `${window.location.pathname}${nextSearch}${window.location.hash}`);

  if (frame.getAttribute("src") !== path) {
    consoleRequestPending = false;
    cleanupConsoleBridge();
    loading.hidden = false;
    frame.classList.remove("is-ready");
    frame.title = `Dashboard Hermes ${organisation.label}`;
    frame.src = path;
  }
}

trigger.addEventListener("click", () => {
  if (menu.hidden) {
    openMenu();
  } else {
    closeMenu();
  }
});

for (const option of options) {
  option.addEventListener("click", () => {
    const id = option.dataset.organisation;
    if (
      id === "operator" ||
      id === "agentik" ||
      id === "mission" ||
      id === "private"
    ) {
      setOrganisation(id);
      closeMenu({ restoreFocus: true });
    }
  });
}

menu.addEventListener("keydown", (event) => {
  const currentIndex = options.indexOf(document.activeElement as HTMLButtonElement);
  let nextIndex: number | null = null;

  if (event.key === "ArrowDown") {
    nextIndex = (currentIndex + 1) % options.length;
  } else if (event.key === "ArrowUp") {
    nextIndex = (currentIndex - 1 + options.length) % options.length;
  } else if (event.key === "Home") {
    nextIndex = 0;
  } else if (event.key === "End") {
    nextIndex = options.length - 1;
  }

  if (nextIndex !== null) {
    event.preventDefault();
    options[nextIndex]?.focus();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !menu.hidden) {
    event.preventDefault();
    closeMenu({ restoreFocus: true });
  }
});

document.addEventListener("pointerdown", (event) => {
  if (!menu.hidden && !menu.parentElement?.contains(event.target as Node)) {
    closeMenu();
  }
});

frame.addEventListener("load", () => {
  loading.hidden = true;
  frame.classList.add("is-ready");
  installConsoleBridge();
});

window.addEventListener("pagehide", cleanupConsoleBridge);

window.addEventListener("popstate", () => {
  setOrganisation(
    resolveOrganisationId(window.location.search, window.localStorage.getItem(STORAGE_KEY)),
  );
});

setOrganisation(activeId);
