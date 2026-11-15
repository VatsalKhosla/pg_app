import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  PoliceDetailsForm,
  type PoliceDetailsText,
} from "@/components/agreements/police-details-form";
import { SignAgreement, type SignAgreementText } from "@/components/agreements/sign-agreement";
import * as client from "@/lib/agreements/client";
import type { RentAgreement, StudentPoliceVerification } from "@/lib/agreements/client";
import {
  fieldOf,
  holdsAadhaarLikeNumber,
  policeFormSchema,
  toRequest,
} from "@/lib/agreements/police-form";
import { ApiError } from "@/lib/api/errors";
import { parseMarkdown } from "@/lib/content/markdown";

import messages from "../../messages/en-IN.json";
import { WCAG_22_AA } from "../wcag";

vi.mock("@/lib/agreements/client", () => ({
  askForSigningCode: vi.fn(),
  signAgreement: vi.fn(),
  givePoliceDetails: vi.fn(),
}));
const router = { refresh: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const CODE = "BK-7F3K2Q9M";
const HASH = "a".repeat(64);
const sign = messages.Agreements.sign;
const form = messages.PoliceVerification.form;
// The rent agreement's templates, as the API writes the text from them (ADR 0070).
const TEMPLATES = path.resolve(process.cwd(), "../api/src/app/modules/agreements/data/templates");

function problem(status: number, code: string, detail?: string, pointer?: string): ApiError {
  return new ApiError({
    message: code,
    status,
    code,
    problem: {
      type: "about:blank",
      title: code,
      status,
      code,
      detail,
      errors: pointer === undefined ? null : [{ detail: detail ?? code, code, pointer }],
    },
  });
}

const signText: SignAgreementText = {
  ...sign,
  developmentCode: sign.developmentCode.replace("{code}", "{code}"),
  errors: sign.errors,
};

describe("SignAgreement", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  function show() {
    return render(<SignAgreement side="student" code={CODE} textSha256={HASH} text={signText} />);
  }

  it("asks for a code first, then signs the text it was shown with the code and the name", async () => {
    vi.mocked(client.askForSigningCode).mockResolvedValue({
      expiresAt: "2027-07-14T10:10:00Z",
      resendAfter: "2027-07-14T10:00:30Z",
      developmentCode: null,
    });
    vi.mocked(client.signAgreement).mockResolvedValue({} as RentAgreement);
    const { container } = show();

    fireEvent.click(screen.getByRole("button", { name: sign.getCode }));
    fireEvent.change(await screen.findByLabelText(sign.code), { target: { value: "123456" } });
    fireEvent.change(screen.getByLabelText(sign.fullName), { target: { value: " Asha Verma " } });
    const results = await axe.run(container, { runOnly: [...WCAG_22_AA] });
    fireEvent.click(screen.getByRole("button", { name: sign.agree }));

    await waitFor(() => {
      expect(router.refresh).toHaveBeenCalled();
    });
    expect(client.askForSigningCode).toHaveBeenCalledWith("student", CODE);
    expect(client.signAgreement).toHaveBeenCalledWith("student", CODE, {
      code: "123456",
      fullName: "Asha Verma",
      textSha256: HASH,
    });
    expect(results.violations).toEqual([]);
  });

  it("signs nothing without six digits and a name in letters", async () => {
    vi.mocked(client.askForSigningCode).mockResolvedValue({
      expiresAt: "2027-07-14T10:10:00Z",
      resendAfter: "2027-07-14T10:00:30Z",
    });
    show();

    fireEvent.click(screen.getByRole("button", { name: sign.getCode }));
    fireEvent.change(await screen.findByLabelText(sign.code), { target: { value: "12" } });
    fireEvent.change(screen.getByLabelText(sign.fullName), { target: { value: "Asha 2" } });
    fireEvent.click(screen.getByRole("button", { name: sign.agree }));

    expect(await screen.findByText(sign.needCode)).toBeTruthy();
    expect(screen.getByText(sign.needName)).toBeTruthy();
    expect(client.signAgreement).not.toHaveBeenCalled();
  });

  it("shows a wrong code by the code, with what the API says is left", async () => {
    vi.mocked(client.askForSigningCode).mockResolvedValue({
      expiresAt: "2027-07-14T10:10:00Z",
      resendAfter: "2027-07-14T10:00:30Z",
    });
    vi.mocked(client.signAgreement).mockRejectedValue(
      problem(400, "SIGNING_CODE_INVALID", "4 attempts left."),
    );
    show();

    fireEvent.click(screen.getByRole("button", { name: sign.getCode }));
    fireEvent.change(await screen.findByLabelText(sign.code), { target: { value: "000000" } });
    fireEvent.change(screen.getByLabelText(sign.fullName), { target: { value: "Asha Verma" } });
    fireEvent.click(screen.getByRole("button", { name: sign.agree }));

    expect(
      await screen.findByText(`${sign.errors.SIGNING_CODE_INVALID} 4 attempts left.`),
    ).toBeTruthy();
    expect(screen.getByLabelText(sign.code).getAttribute("aria-invalid")).toBe("true");
  });

  it("loads the new text when the agreement changed while it was read", async () => {
    vi.mocked(client.askForSigningCode).mockResolvedValue({
      expiresAt: "2027-07-14T10:10:00Z",
      resendAfter: "2027-07-14T10:00:30Z",
    });
    vi.mocked(client.signAgreement).mockRejectedValue(problem(409, "AGREEMENT_TEXT_CHANGED"));
    show();

    fireEvent.click(screen.getByRole("button", { name: sign.getCode }));
    fireEvent.change(await screen.findByLabelText(sign.code), { target: { value: "123456" } });
    fireEvent.change(screen.getByLabelText(sign.fullName), { target: { value: "Asha Verma" } });
    fireEvent.click(screen.getByRole("button", { name: sign.agree }));

    expect(await screen.findByText(sign.errors.AGREEMENT_TEXT_CHANGED)).toBeTruthy();
    expect(router.refresh).toHaveBeenCalled();
  });
});

const MESSAGES = form.messages;
const VALID = {
  fullName: "Asha Verma",
  parentName: "Ravi Verma",
  dateOfBirth: "2007-03-09",
  gender: "female",
  phone: "98765 00001",
  permanentAddress: {
    line: "House 9, a fictional lane",
    city: "Fictional Town",
    district: "Fictional District",
    state: "Fictional State",
    pinCode: "123456",
    policeStation: "",
  },
  occupation: "student",
  institution: "A fictional college",
  idType: "passport",
  idLast4: "567K",
  references: [],
  consent: true,
} as const;

describe("the police-verification form's rules", () => {
  const schema = policeFormSchema(MESSAGES);

  it("never lets an Aadhaar number through, whichever field it's in", () => {
    for (const changes of [
      { fullName: "Asha 2345 6789 0123" },
      { institution: "Roll 234567890123" },
      { permanentAddress: { ...VALID.permanentAddress, line: "2345-6789-0123, Delhi" } },
      { references: [{ name: "Meera 234567890123", phone: "9876500002", relation: "Aunt" }] },
    ]) {
      const result = schema.safeParse({ ...VALID, ...changes });
      expect(result.success).toBe(false);
      expect(JSON.stringify(result.error?.issues)).toContain(MESSAGES.aadhaar);
    }
    expect(holdsAadhaarLikeNumber("१२३४ ५६७८ ९०१२")).toBe(true);
    expect(holdsAadhaarLikeNumber("9876543210")).toBe(false);
  });

  it("takes only the last four characters, digits for an Aadhaar", () => {
    expect(schema.safeParse({ ...VALID, idLast4: "12345" }).success).toBe(false);
    const aadhaar = schema.safeParse({ ...VALID, idType: "aadhaar", idLast4: "12AB" });
    expect(JSON.stringify(aadhaar.error?.issues)).toContain(MESSAGES.aadhaarLast4);
    expect(schema.safeParse({ ...VALID, idType: "aadhaar", idLast4: "1234" }).success).toBe(true);
  });

  it("shares nothing without the student's own tick", () => {
    const result = schema.safeParse({ ...VALID, consent: false });
    expect(JSON.stringify(result.error?.issues)).toContain(MESSAGES.consent);
  });

  it("sends no police station that wasn't given, and consent as given", () => {
    const request = toRequest(schema.parse(VALID));
    expect(request.permanentAddress).not.toHaveProperty("policeStation");
    expect(request.consent).toBe(true);
  });

  it("places the API's errors by their fields", () => {
    expect(fieldOf("/permanentAddress/pinCode")).toBe("permanentAddress.pinCode");
    expect(fieldOf("/references/1/phone")).toBe("references.1.phone");
    expect(fieldOf("/idLast4")).toBe("idLast4");
    expect(fieldOf("/somethingElse")).toBeUndefined();
  });
});

const policeText: PoliceDetailsText = {
  ...form,
  title: form.title,
  messages: form.messages,
  errors: messages.PoliceVerification.errors,
};

describe("PoliceDetailsForm", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  function show() {
    return render(<PoliceDetailsForm code={CODE} details={null} text={policeText} />);
  }

  function fillIn() {
    const fields: [string, string][] = [
      [form.fullName, VALID.fullName],
      [form.parentName, VALID.parentName],
      [form.dateOfBirth, VALID.dateOfBirth],
      [form.phone, VALID.phone],
      [form.line, VALID.permanentAddress.line],
      [form.city, VALID.permanentAddress.city],
      [form.district, VALID.permanentAddress.district],
      [form.state, VALID.permanentAddress.state],
      [form.pinCode, VALID.permanentAddress.pinCode],
      [form.institution, VALID.institution],
      [form.idLast4, VALID.idLast4],
    ];
    for (const [label, value] of fields) {
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    }
    fireEvent.click(screen.getByLabelText(form.genders.female));
    fireEvent.click(screen.getByLabelText(form.occupations.student));
    fireEvent.change(screen.getByLabelText(form.idType), { target: { value: "passport" } });
  }

  it("asks for the details with nothing ticked, and passes axe", async () => {
    const { container } = show();

    const consent = screen.getByRole<HTMLInputElement>("checkbox", { name: form.consent });
    expect(consent.checked).toBe(false);
    const results = await axe.run(container, { runOnly: [...WCAG_22_AA] });
    expect(results.violations).toEqual([]);
  });

  it("sends the details once consent is ticked", async () => {
    vi.mocked(client.givePoliceDetails).mockResolvedValue({} as StudentPoliceVerification);
    show();

    fillIn();
    fireEvent.click(screen.getByRole("button", { name: form.save }));
    expect(await screen.findByText(MESSAGES.consent)).toBeTruthy();
    expect(client.givePoliceDetails).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("checkbox", { name: form.consent }));
    fireEvent.click(screen.getByRole("button", { name: form.save }));

    await waitFor(() => {
      expect(router.refresh).toHaveBeenCalled();
    });
    expect(client.givePoliceDetails).toHaveBeenCalledWith(
      CODE,
      expect.objectContaining({ fullName: "Asha Verma", idLast4: "567K", consent: true }),
    );
  });

  it("shows the API's refusal next to the field it's about", async () => {
    vi.mocked(client.givePoliceDetails).mockRejectedValue(
      problem(422, "VALIDATION_ERROR", "A PIN code is 6 digits.", "/permanentAddress/pinCode"),
    );
    show();

    fillIn();
    fireEvent.click(screen.getByRole("checkbox", { name: form.consent }));
    fireEvent.click(screen.getByRole("button", { name: form.save }));

    expect(await screen.findByText("A PIN code is 6 digits.")).toBeTruthy();
    expect(screen.getByLabelText(form.pinCode).getAttribute("aria-invalid")).toBe("true");
  });
});

describe("every rent agreement template on file", () => {
  const versions = readdirSync(TEMPLATES).filter((name) => name.endsWith(".md"));

  it.each(versions)("%s uses only the Markdown the booking pages show", (name) => {
    const blocks = parseMarkdown(readFileSync(path.join(TEMPLATES, name), "utf8"));

    expect(blocks[0]).toMatchObject({ kind: "heading", level: 1 });
    for (const block of blocks) {
      const runs = block.kind === "list" ? block.items.flat() : block.content;
      for (const run of runs) expect(run.text).not.toMatch(/\*\*|^#/u);
      if (block.kind === "paragraph") expect(block.content[0]?.text).not.toMatch(/^\d+\. /u);
    }
  });
});
