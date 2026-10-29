import { readFileSync } from "node:fs";
import path from "node:path";

import { devices, type Page } from "@playwright/test";

import { expect, test, wcagViolations } from "./fixtures";
import { eventsOf } from "./posthog";
import { codeSentTo, logLength, newMobile } from "./sign-in-codes";
import { manage, newStaff, signInAsStaff } from "./staff";

// A visit end to end (BUILD_PLAN 3.7), on phones, against the real API and its worker: a student
// finds a sample PG and asks to visit it, ops book a time with a field agent, the agent checks in
// at the building and says how it went, and ops see the visit log. Along the way the booking
// funnel reaches PostHog's stand-in as one anonymous journey (BUILD_PLAN 3.9).

const ASTER = "fictional-sample-pg-aster-kamla-nagar";
const PHONE = devices["Pixel 7"];

interface Places {
  localities: { name: string; center: { lat: number; lng: number } }[];
}

// Where the agent's phone is: Kamla Nagar's centre, from the verified geo data the API loads.
const places = JSON.parse(
  readFileSync(path.resolve(process.cwd(), "../api/src/app/modules/geo/data/places.json"), "utf8"),
) as Places;
const here = places.localities.find((place) => place.name === "Kamla Nagar")?.center;
if (here === undefined) throw new Error("Kamla Nagar is missing from places.json");

/** "YYYY-MM-DDTHH:MM" in India, as a datetime-local field takes it. */
function indiaLocal(moment: Date): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(moment);
  const part = (type: string) => parts.find((each) => each.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}T${part("hour")}:${part("minute")}`;
}

/** A new student finds the PG by searching, then signs up on their phone to ask for a visit:
 * the code, consent (nothing ticked), their name. */
async function signUpAsStudent(page: Page, name: string) {
  await page.goto("/search?locality=kamla-nagar");
  await page
    .getByRole("link", { name: /Fictional Sample PG Aster/ })
    .first()
    .click();
  await expect(page).toHaveURL(new RegExp(`/pg/${ASTER}$`));
  await page.getByRole("link", { name: "Book a visit" }).first().click();
  await expect(page).toHaveURL(/\/sign-in\?next=/);
  const mobile = newMobile();
  await page.getByLabel("Mobile number", { exact: true }).fill(mobile);
  const from = await logLength();
  await page.getByRole("button", { name: "Send code" }).click();
  await page
    .getByLabel("Six-digit code", { exact: true })
    .fill(await codeSentTo(mobile, { after: from }));
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("checkbox", { name: /^I agree/ }).check();
  await page.getByRole("button", { name: "Agree and continue" }).click();
  await page.getByLabel("Your name", { exact: true }).fill(name);
  await page.getByRole("button", { name: "Save" }).click();
}

test.describe("a visit", () => {
  // First sign-ins are refused until consent is given (400 CONSENT_REQUIRED), by design.
  test.use({ expectedConsoleErrors: [/status of 400/] });

  test.beforeAll(async () => {
    await manage(["catalog", "samples"]);
  });

  test("a student asks on a phone, ops book it, the agent checks in, and ops see the log", async ({
    page,
    browser,
  }, testInfo) => {
    test.skip(testInfo.project.name !== "phone", "one run is enough, and phones are the case");
    test.slow();
    const run = String(Date.now()).slice(-6);
    const student = `Visit Tester ${run}`;
    const agentName = `Field Agent ${run}`;

    // The student: asks for tomorrow at 11 am, with nothing chosen for them.
    await signUpAsStudent(page, student);
    await expect(page).toHaveURL(new RegExp(`/pg/${ASTER}/visit$`));
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      /^Visit Fictional Sample PG Aster/,
    );
    const first = page.getByRole("group", { name: "Time 1" });
    await expect(first.getByLabel("Day")).toHaveValue("");
    expect(await wcagViolations(page)).toEqual([]);
    await first.getByLabel("Day").selectOption({ index: 2 });
    await first.getByLabel("Time").selectOption("11:00");
    await page.getByRole("button", { name: "Ask for a visit" }).click();
    await expect(page).toHaveURL(/\/visits$/);
    const mine = page
      .getByRole("listitem")
      .filter({ hasText: "Fictional Sample PG Aster" })
      .first();
    await expect(mine).toContainText("Asked for: we'll call you to book a time");
    expect(await wcagViolations(page)).toEqual([]);

    // Ops: book it for now, so the agent can check in, with the agent.
    const agent = await newStaff(["field_agent"], agentName);
    const ops = await newStaff(["ops"]);
    const opsContext = await browser.newContext({ ...PHONE });
    const opsPage = await opsContext.newPage();
    await opsPage.goto("/ops/visits?status=requested");
    await signInAsStaff(opsPage, ops);
    await expect(opsPage).toHaveURL(/\/ops\/visits\?status=requested$/);
    await opsPage
      .getByRole("listitem")
      .filter({ hasText: student })
      .getByRole("link", { name: "Fictional Sample PG Aster" })
      .click();
    await expect(opsPage.getByRole("heading", { level: 1 })).toHaveText(
      "Fictional Sample PG Aster",
    );
    await opsPage.getByRole("radio", { name: "Another time" }).check();
    await opsPage.getByLabel("Date and time, in India").fill(indiaLocal(new Date()));
    await opsPage.getByLabel("Field agent").selectOption({ label: agentName });
    await opsPage.getByRole("button", { name: "Book the visit" }).click();
    await expect(opsPage.getByText(/^Booked ·/)).toBeVisible();
    expect(await wcagViolations(opsPage)).toEqual([]);

    // The student now sees the address.
    await page.reload();
    await expect(mine).toContainText("Booked for");
    await expect(mine).toContainText("Address");

    // The agent: at the building, checks in, then says how it went.
    const agentContext = await browser.newContext({
      ...PHONE,
      geolocation: { latitude: here.lat, longitude: here.lng, accuracy: 15 },
      permissions: ["geolocation"],
    });
    const agentPage = await agentContext.newPage();
    await agentPage.goto("/field/student-visits");
    await signInAsStaff(agentPage, agent);
    await expect(agentPage).toHaveURL(/\/field\/student-visits$/);
    await agentPage.getByRole("link", { name: "Fictional Sample PG Aster" }).first().click();
    await agentPage.getByRole("button", { name: "Check in at the building" }).click();
    await expect(agentPage.getByText(/^Checked in at .+ from the building\.$/)).toBeVisible();
    await agentPage.getByRole("radio", { name: "Interested", exact: true }).check();
    await agentPage.getByLabel("Note for ops (optional)").fill("Liked the double room.");
    await agentPage.getByRole("button", { name: "Save" }).click();
    await expect(agentPage.getByText("Done: Interested.")).toBeVisible();
    expect(await wcagViolations(agentPage)).toEqual([]);

    // Ops: the visit log, the agent's check-in and how it went.
    await opsPage.reload();
    const log = opsPage.getByRole("region", { name: "Visit log" });
    await expect(log.getByText(/^Agent checked in at .+ from the building/)).toBeVisible();
    await expect(log.getByText(/: Interested$/)).toBeVisible();
    await expect(log.getByText("Agent's note: Liked the double room.")).toBeVisible();

    // The funnel, as PostHog will have it: one anonymous journey from search to the visit done,
    // the last step reported by the API under the id the student's tab asked with.
    const journey = await page.evaluate(() => sessionStorage.getItem("analytics-id"));
    expect(journey).not.toBeNull();
    await expect
      .poll(
        async () =>
          [...new Set((await eventsOf(journey ?? "")).map((event) => event.event))].filter(
            (event) => event !== "web_vital",
          ),
        { timeout: 30_000 },
      )
      .toEqual(["search_performed", "pg_viewed", "visit_requested", "visit_completed"]);
    const events = await eventsOf(journey ?? "");
    for (const event of events) {
      expect(event.properties).toMatchObject({
        $process_person_profile: false,
        $geoip_disable: true,
      });
      expect(JSON.stringify(event.properties)).not.toContain(student);
    }

    await opsContext.close();
    await agentContext.close();
  });
});
