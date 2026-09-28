// Server-side admin rule: exactly one GitHub account; everyone else 403; no session → login.
import assert from "node:assert/strict";
import { test } from "node:test";
import { ADMIN_GITHUB_ID, ADMIN_GITHUB_LOGIN, adminAccess, authConfigured, safeAdminPath } from "../lib/admin/access.ts";

test("only nassimb (with the pinned account id) is allowed", () => {
  assert.equal(ADMIN_GITHUB_LOGIN, "nassimb");
  assert.equal(adminAccess({ login: "nassimb", ghid: ADMIN_GITHUB_ID }), "ok");
  assert.equal(adminAccess({ login: "NassimB", ghid: ADMIN_GITHUB_ID }), "ok");
});

test("another GitHub user is forbidden", () => {
  assert.equal(adminAccess({ login: "octocat", ghid: 583231 }), "forbidden");
  assert.equal(adminAccess({ login: "nassimb", ghid: 583231 }), "forbidden"); // re-registered handle, different account
  assert.equal(adminAccess({ login: "octocat", ghid: ADMIN_GITHUB_ID }), "forbidden");
  assert.equal(adminAccess({ login: "nassimb" }), "forbidden");
  assert.equal(adminAccess({ login: "nassimb-evil", ghid: ADMIN_GITHUB_ID }), "forbidden");
});

test("no session → login", () => {
  assert.equal(adminAccess(null), "login");
  assert.equal(adminAccess(undefined), "login");
  assert.equal(adminAccess({}), "login");
});

test("post-login redirect stays inside /admin", () => {
  assert.equal(safeAdminPath("/admin/comms/calendar"), "/admin/comms/calendar");
  for (const bad of ["https://evil.example", "//evil.example", "/admin/../x", "/", "/admin/login", 42]) assert.equal(safeAdminPath(bad), "/admin/comms");
});

test("auth fails closed without all three server-side secrets", () => {
  assert.equal(authConfigured({}), false);
  assert.equal(authConfigured({ AUTH_SECRET: "x", AUTH_GITHUB_ID: "y" }), false);
  assert.equal(authConfigured({ AUTH_SECRET: "x", AUTH_GITHUB_ID: "y", AUTH_GITHUB_SECRET: "z" }), true);
});
