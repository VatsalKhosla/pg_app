import { render, screen } from "@testing-library/react";
import axe from "axe-core";
import { describe, expect, it } from "vitest";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox, Field, FormOutcome, Select, Textarea } from "@/components/ui/fields";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";

import { WCAG_22_AA } from "../wcag";

describe("UI primitives", () => {
  it("renders buttons across variants, sizes, pill shape and asChild links", () => {
    render(
      <div>
        <Button>Primary action</Button>
        <Button variant="soft" shape="pill">
          Filter chip
        </Button>
        <Button asChild variant="outline" size="lg">
          <a href="/search">Browse PGs</a>
        </Button>
      </div>,
    );

    expect(screen.getByRole("button", { name: "Primary action" }).getAttribute("data-slot")).toBe(
      "button",
    );
    expect(screen.getByRole("button", { name: "Filter chip" }).className).toContain("rounded-full");
    expect(screen.getByRole("link", { name: "Browse PGs" }).getAttribute("href")).toBe("/search");
  });

  it("renders cards with semantic headings through CardTitle asChild", () => {
    render(
      <Card variant="raised">
        <CardHeader>
          <CardTitle asChild>
            <h2>Kaveri Residency</h2>
          </CardTitle>
          <CardDescription>Verified PG in Koramangala</CardDescription>
        </CardHeader>
        <CardContent>
          <p>Single and twin sharing rooms.</p>
        </CardContent>
        <CardFooter>
          <Badge variant="success">Verified</Badge>
        </CardFooter>
      </Card>,
    );

    expect(screen.getByRole("heading", { level: 2, name: "Kaveri Residency" })).toBeDefined();
    expect(screen.getByText("Verified").getAttribute("data-slot")).toBe("badge");
  });

  it("hides decorative skeletons and separators from assistive tech, and exposes semantic separators", () => {
    const { container } = render(
      <div>
        <Skeleton className="h-6 w-32" />
        <Separator />
        <Separator decorative={false} orientation="horizontal" />
      </div>,
    );

    const skeleton = container.querySelector('[data-slot="skeleton"]');
    expect(skeleton?.getAttribute("aria-hidden")).toBe("true");
    expect(screen.getAllByRole("separator")).toHaveLength(1);
  });

  it("wires form fields, hints, errors and outcomes for screen readers and passes WCAG 2.2 AA", async () => {
    const { container } = render(
      <main>
        <h1>Design system</h1>
        <Card variant="flat">
          <CardHeader>
            <CardTitle asChild>
              <h2>Enquiry details</h2>
            </CardTitle>
            <CardDescription>All fields are labelled.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Field id="city" label="City" hint="Where you study or work">
              {(control) => <Input {...control} defaultValue="Bengaluru" />}
            </Field>
            <Field id="sharing" label="Sharing" error="Pick a sharing type">
              {(control) => (
                <Select {...control} defaultValue="">
                  <option value="" disabled>
                    Choose one
                  </option>
                  <option value="single">Single</option>
                </Select>
              )}
            </Field>
            <Field id="notes" label="Notes">
              {(control) => <Textarea {...control} />}
            </Field>
            <Checkbox label="Notify me by SMS" />
            <FormOutcome failure={null} saved="Saved" />
          </CardContent>
          <CardFooter>
            <Badge variant="brand">New</Badge>
            <Badge variant="coral">Coral</Badge>
            <Badge variant="saffron">Saffron</Badge>
            <Badge variant="indigo">Indigo</Badge>
            <Badge variant="sage">Sage</Badge>
            <Badge variant="warning">Pending</Badge>
            <Badge variant="destructive">Expired</Badge>
            <Button type="button">Continue</Button>
          </CardFooter>
        </Card>
        <div className="grid gap-2">
          <Card variant="warm">Warm card</Card>
          <Card variant="teal">Teal card</Card>
          <Card variant="coral">Coral card</Card>
          <Card variant="saffron">Saffron card</Card>
          <Card variant="indigo">Indigo card</Card>
          <Card variant="sage">Sage card</Card>
        </div>
      </main>,
    );

    const sharing = screen.getByLabelText("Sharing");
    expect(sharing.getAttribute("aria-invalid")).toBe("true");
    expect(sharing.getAttribute("aria-describedby")).toBe("sharing-error");

    const results = await axe.run(container, { runOnly: { type: "tag", values: WCAG_22_AA } });
    const violations = results.violations.map((v) => `${v.id}: ${v.help}`);
    expect(violations).toEqual([]);
  });
});
