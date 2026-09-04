/**
 * Agentik OS catalog for the Hermes web dashboard.
 *
 * This is an authored, build-free IIFE. React and the shadcn/ui primitives
 * come from the official Hermes dashboard plugin SDK.
 */
(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  const registry = window.__HERMES_PLUGINS__;
  if (!SDK || !registry) return;

  const { React, fetchJSON } = SDK;
  const h = React.createElement;
  const {
    Card,
    CardHeader,
    CardTitle,
    CardContent,
    Badge,
    Button,
    Separator,
    Tabs,
    TabsList,
    TabsTrigger,
  } = SDK.components;
  const { useCallback, useEffect, useMemo, useState } = SDK.hooks;

  function text(value, fallback) {
    return typeof value === "string" && value.trim() ? value : fallback;
  }

  function array(value) {
    return Array.isArray(value) ? value : [];
  }

  function statusVariant(active) {
    return active ? "default" : "secondary";
  }

  function EmptyState(props) {
    return h("div", { className: "agk-os-empty" },
      h("strong", null, props.title),
      h("p", null, props.message),
    );
  }

  function SummaryCard(props) {
    return h(Card, { className: "agk-os-summary-card" },
      h(CardContent, { className: "agk-os-summary-card-content" },
        h("span", { className: "agk-os-summary-value" }, String(props.value)),
        h("span", { className: "agk-os-summary-label" }, props.label),
      ),
    );
  }

  function CatalogTrigger(props) {
    const entity = props.entity;
    const active = props.selectedKey === props.entityKey;
    const badges = props.kind === "agent"
      ? array(entity.sessions).filter(function (session) { return !!session.active; }).length
      : array(entity.scope).length;
    return h(Button, {
      type: "button",
      variant: active ? "secondary" : "ghost",
      className: "agk-os-catalog-trigger" + (active ? " is-active" : ""),
      onClick: function () { props.onSelect(props.entityKey); },
      "aria-pressed": active,
    },
      h("span", { className: "agk-os-trigger-copy" },
        h("strong", null, text(entity.name, entity.id || "Unnamed")),
        h("small", null, text(entity.description, props.kind === "agent" ? "Hermes agent" : "Operative System")),
      ),
      h(Badge, { variant: "outline" }, String(badges)),
    );
  }

  function CatalogNavigation(props) {
    const packages = array(props.catalog.registry && props.catalog.registry.packages);
    const agents = array(props.catalog.agents);
    const items = props.section === "systems"
      ? packages.map(function (entity) { return { kind: "system", entity: entity }; })
      : agents.map(function (entity) { return { kind: "agent", entity: entity }; });

    return h("nav", { className: "agk-os-catalog-navigation", "aria-label": "Agentik OS catalog" },
      items.length
        ? items.map(function (item) {
          const key = item.kind + ":" + item.entity.id + ":" + (item.entity.version || "");
          return h(CatalogTrigger, {
            key: key,
            entityKey: key,
            entity: item.entity,
            kind: item.kind,
            selectedKey: props.selectedKey,
            onSelect: props.onSelect,
          });
        })
        : h(EmptyState, {
          title: props.section === "systems" ? "No installed OS" : "No installed agent",
          message: "Install and verify a package in this Zone to make it available here.",
        }),
    );
  }

  function TagList(props) {
    const values = array(props.values);
    if (!values.length) return h("span", { className: "agk-os-muted" }, "None declared");
    return h("div", { className: "agk-os-tags" }, values.map(function (value) {
      return h(Badge, { key: String(value), variant: "outline" }, String(value));
    }));
  }

  function EntityDetail(props) {
    const entity = props.entity;
    const isAgent = props.kind === "agent";
    const sessions = array(entity.sessions);
    const fields = isAgent
      ? ["scope", "runtime"]
      : ["scope", "capabilities", "skills", "workflows", "agents", "tools", "commands", "knowledge", "evals"];

    return h("div", { className: "agk-os-detail-body agk-os-detail-body--entity" },
      h("div", { className: "agk-os-entity-heading" },
        h("div", null,
          h("span", { className: "agk-os-eyebrow" }, isAgent ? "Hermes profile" : "Operative System"),
          h("h2", null, text(entity.name, entity.id || "Unnamed")),
          h("p", null, text(entity.description, "No public description.")),
        ),
        h(Badge, { variant: entity.allowed_here ? "default" : "secondary" }, entity.allowed_here ? "Allowed here" : "Other scope"),
      ),
      h(Separator, null),
      h("dl", { className: "agk-os-metadata" },
        h("div", null, h("dt", null, "Identifier"), h("dd", null, text(entity.id, "unknown"))),
        h("div", null, h("dt", null, "Version"), h("dd", null, text(entity.version, "unversioned"))),
        isAgent
          ? h("div", null, h("dt", null, "Active sessions"), h("dd", null, String(sessions.filter(function (session) { return !!session.active; }).length)))
          : null,
      ),
      fields.map(function (field) {
        const values = field === "runtime" ? [entity.runtime] : entity[field];
        return h("section", { className: "agk-os-field", key: field },
          h("h3", null, field.charAt(0).toUpperCase() + field.slice(1)),
          h(TagList, { values: values }),
        );
      }),
      isAgent && sessions.length
        ? h("section", { className: "agk-os-field" },
          h("h3", null, "Runtime sessions"),
          h("div", { className: "agk-os-session-list" }, sessions.map(function (session) {
            return h("div", { className: "agk-os-session", key: session.id },
              h("span", null, text(session.name, session.id)),
              h(Badge, { variant: statusVariant(session.active) }, text(session.status, "unknown")),
            );
          })),
        )
        : null,
    );
  }

  function DashboardDetail(props) {
    const catalog = props.catalog;
    const registryState = catalog.registry || {};
    return h("div", { className: "agk-os-detail-body agk-os-detail-body--dashboard" },
      h("div", { className: "agk-os-welcome" },
        h("span", { className: "agk-os-eyebrow" }, "Hermes control context"),
        h("h2", null, "OS & Agents"),
        h("p", null, "Inspect the verified Operative Systems, Hermes profiles, and live sessions attached to this isolated Zone."),
      ),
      h("div", { className: "agk-os-summary-grid" },
        h(SummaryCard, { value: registryState.package_count || 0, label: "Installed OS" }),
        h(SummaryCard, { value: catalog.sync && catalog.sync.agent_count || 0, label: "Hermes agents" }),
        h(SummaryCard, { value: catalog.sync && catalog.sync.active_session_count || 0, label: "Active sessions" }),
      ),
      h("div", { className: "agk-os-integrity" },
        h(Badge, { variant: registryState.healthy ? "default" : "secondary" }, registryState.healthy ? "Registry healthy" : "Registry not verified"),
        h("span", null, "Zone: " + text(catalog.environment, "unknown")),
      ),
    );
  }

  function AgentikOSPage() {
    const [catalog, setCatalog] = useState(null);
    const [error, setError] = useState("");
    const [section, setSection] = useState("systems");
    const [selectedKey, setSelectedKey] = useState("");

    const load = useCallback(function () {
      setError("");
      return fetchJSON("/api/plugins/agentik-os/catalog")
        .then(function (payload) { setCatalog(payload); })
        .catch(function (reason) { setError(reason && reason.message ? reason.message : "Catalog unavailable"); });
    }, []);

    useEffect(function () { load(); }, [load]);

    const selected = useMemo(function () {
      if (!catalog || !selectedKey) return null;
      const parts = selectedKey.split(":");
      const kind = parts[0];
      const id = parts[1];
      const values = kind === "agent" ? array(catalog.agents) : array(catalog.registry && catalog.registry.packages);
      const entity = values.find(function (candidate) { return candidate.id === id; });
      return entity ? { kind: kind, entity: entity } : null;
    }, [catalog, selectedKey]);

    return h("main", { className: "agk-os-hub agk-os-workspace" },
      h(Card, { className: "agk-os-context-panel" },
        h(CardHeader, null,
          h("div", { className: "agk-os-header-row" },
            h(CardTitle, null, "Catalog"),
            h(Button, { type: "button", variant: "outline", size: "sm", onClick: load }, "Refresh"),
          ),
          h(Tabs, { value: section, onValueChange: function (value) { setSection(value); setSelectedKey(""); } },
            h(TabsList, { className: "agk-os-section-switcher" },
              h(TabsTrigger, { value: "systems" }, "Systems"),
              h(TabsTrigger, { value: "agents" }, "Agents"),
            ),
          ),
        ),
        h(CardContent, null,
          error
            ? h(EmptyState, { title: "Catalog unavailable", message: error })
            : catalog
              ? h(CatalogNavigation, { catalog: catalog, section: section, selectedKey: selectedKey, onSelect: setSelectedKey })
              : h(EmptyState, { title: "Loading catalog", message: "Reading the active Hermes Zone." }),
        ),
      ),
      h(Card, { className: "agk-os-detail-panel" },
        h(CardContent, { className: "agk-os-detail-content" },
          !catalog
            ? h(EmptyState, { title: "Loading", message: "Waiting for the local Hermes API." })
            : selected
              ? h(EntityDetail, { kind: selected.kind, entity: selected.entity })
              : h(DashboardDetail, { catalog: catalog }),
        ),
      ),
    );
  }

  registry.register("agentik-os", AgentikOSPage);
})();
