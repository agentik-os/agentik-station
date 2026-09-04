import { describe, expect, it } from "vitest";

import {
  ORGANISATIONS,
  colorSchemeForHex,
  consolePath,
  dashboardPath,
  getOrganisation,
  resolveOrganisationId,
  withOrganisation,
} from "./organisations.js";

describe("organisation routing", () => {
  it("keeps the exact four workspaces and their descriptions", () => {
    expect(
      ORGANISATIONS.map(({ id, description }) => ({ id, description })),
    ).toEqual([
      { id: "operator", description: "Infrastructure et opérations" },
      { id: "agentik", description: "Organisation et produits" },
      { id: "mission", description: "Missions et espaces clients" },
      { id: "private", description: "Espace personnel isolé" },
    ]);
  });

  it("prefers a valid query organisation over persisted state", () => {
    expect(resolveOrganisationId("?org=mission", "private")).toBe("mission");
  });

  it("falls back to persisted state and then operator", () => {
    expect(resolveOrganisationId("?org=unknown", "agentik")).toBe("agentik");
    expect(resolveOrganisationId("?org=unknown", "unknown")).toBe("operator");
  });

  it("maps every organisation to its dedicated Hermes port", () => {
    expect(getOrganisation("operator").port).toBe(8460);
    expect(getOrganisation("agentik").port).toBe(8461);
    expect(getOrganisation("mission").port).toBe(8462);
    expect(getOrganisation("private").port).toBe(8463);
  });

  it("maps dashboards to same-origin reverse-proxy paths", () => {
    expect(dashboardPath("operator")).toBe("/operator/");
    expect(dashboardPath("agentik")).toBe("/agentik/");
    expect(dashboardPath("mission")).toBe("/mission/");
    expect(dashboardPath("private")).toBe("/private/");
  });

  it("maps console requests to each profile System page", () => {
    expect(consolePath("operator")).toBe("/operator/system?agk-console=1");
    expect(consolePath("agentik")).toBe("/agentik/system?agk-console=1");
    expect(consolePath("mission")).toBe("/mission/system?agk-console=1");
    expect(consolePath("private")).toBe("/private/system?agk-console=1");
  });

  it("maps Hermes background tokens to the matching Fleet color scheme", () => {
    expect(colorSchemeForHex("#0d0d0d")).toBe("dark");
    expect(colorSchemeForHex("#fbfbfa")).toBe("light");
    expect(colorSchemeForHex("#fff")).toBe("light");
    expect(colorSchemeForHex("not-a-color")).toBe("dark");
  });

  it("updates org without discarding unrelated query parameters", () => {
    expect(withOrganisation("?view=fleet&org=operator", "private")).toBe(
      "?view=fleet&org=private",
    );
  });
});
