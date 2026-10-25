import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SignInFlow, type SignInText } from "@/components/auth/sign-in-flow";
import { ApiError } from "@/lib/api/errors";
import * as client from "@/lib/auth/client";

import { WCAG_22_AA } from "../wcag";

vi.mock("@/lib/auth/client", () => ({
  requestCode: vi.fn(),
  verifyCode: vi.fn(),
  privacyNotice: vi.fn(),
  updateProfile: vi.fn(),
  signInWithAuthenticator: vi.fn(),
}));

const text: SignInText = {
  phone: {
    title: "Your mobile number",
    intro: "We'll text you a code.",
    label: "Mobile number",
    hint: "Ten digits.",
    invalid: "Enter a 10-digit Indian mobile number.",
    humanCheck: "A quick check.",
    submit: "Send code",
    sending: "Sending",
  },
  code: {
    title: "Enter the code",
    intro: "Sent to {phone}.",
    developmentCode: "Local development: the code is {code}.",
    label: "Six-digit code",
    invalid: "The code is six digits.",
    submit: "Continue",
    checking: "Checking",
    resend: "Send a new code",
    resendLater: "Wait a moment.",
    otherNumber: "Use a different number",
  },
  consent: {
    title: "Before we create your account",
    intro: "We need your agreement.",
    notice: "Read the privacy notice",
    account: "I agree to keeping my account",
    accountRequired: "You need to agree to this.",
    marketing: "Send me offers",
    submit: "Agree and continue",
  },
  profile: {
    title: "About you",
    intro: "So we know what to call you.",
    form: {
      name: "Your name",
      nameHint: "What to call you.",
      nameRequired: "Enter your name.",
      nameTooLong: "Too long.",
      place: "College or workplace",
      placeHint: "Optional.",
      placeTooLong: "Too long.",
      gender: "Gender",
      genderHint: "Optional.",
      genderFemale: "Female",
      genderMale: "Male",
      genderOther: "Other",
      genderUnsaid: "Rather not say",
      submit: "Save",
      saving: "Saving",
      saved: "Saved.",
      errors: { generic: "Something went wrong." },
    },
  },
  authenticator: {
    title: "Your authenticator code",
    intro: "From the app.",
    label: "Authenticator code",
    invalid: "The code is six digits.",
    submit: "Sign in to staff tools",
    checking: "Checking",
  },
  errors: {
    generic: "Something went wrong.",
    OTP_EXPIRED: "That code has expired.",
    OTP_INVALID: "That code isn't right.",
  },
};

const challenge = {
  challengeId: "01a15508-0000-7000-8000-000000000001",
  expiresAt: new Date(Date.now() + 300_000).toISOString(),
  resendAfter: new Date(Date.now() + 30_000).toISOString(),
};

function person(name: string | null) {
  return {
    id: "01a15508-0000-7000-8000-000000000002",
    phone: "+919876543210",
    email: null,
    name,
    collegeOrWorkplace: null,
    gender: null,
    roles: ["student" as const],
    consentRequired: false,
  };
}

function problem(status: number, code: string, errors: { pointer: string; detail: string }[] = []) {
  return new ApiError({
    message: code,
    status,
    code,
    problem: {
      type: "about:blank",
      title: code,
      status,
      code,
      errors: errors.map((error) => ({ ...error, code: "invalid" })),
    },
  });
}

const assign = vi.fn();

beforeEach(() => {
  assign.mockReset();
  // jsdom can't navigate; the flow only ever calls assign.
  vi.stubGlobal("location", { href: "http://localhost:3000/sign-in", assign });
});

function type(label: string, value: string) {
  fireEvent.input(screen.getByLabelText(label), { target: { value } });
}

async function sendCode() {
  type("Mobile number", "98765 43210");
  fireEvent.click(screen.getByRole("button", { name: "Send code" }));
  await screen.findByRole("heading", { name: "Enter the code" });
}

function enterCode() {
  type("Six-digit code", "123456");
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
}

describe("SignInFlow", () => {
  it("takes a new person from their number to consent, nothing ticked, to their profile", async () => {
    vi.mocked(client.requestCode).mockResolvedValue(challenge);
    vi.mocked(client.verifyCode)
      .mockRejectedValueOnce(problem(400, "CONSENT_REQUIRED"))
      .mockResolvedValueOnce({ user: person(null), csrfToken: "token", newUser: true });
    vi.mocked(client.privacyNotice).mockResolvedValue({
      version: "draft-1",
      purposes: [
        { purpose: "account", required: true },
        { purpose: "marketing", required: false },
      ],
    });
    vi.mocked(client.updateProfile).mockResolvedValue(person("Asha"));
    render(<SignInFlow text={text} next="/account" mode="people" />);

    await sendCode();
    expect(client.requestCode).toHaveBeenCalledWith("98765 43210", "not-checked");
    expect(screen.getByText("Sent to 98765 43210.")).toBeDefined();
    enterCode();
    await screen.findByRole("heading", { name: "Before we create your account" });

    const agree = screen.getByRole<HTMLInputElement>("checkbox", {
      name: "I agree to keeping my account",
    });
    const offers = screen.getByRole<HTMLInputElement>("checkbox", { name: "Send me offers" });
    expect([agree.checked, offers.checked]).toEqual([false, false]);
    fireEvent.click(screen.getByRole("button", { name: "Agree and continue" }));
    await screen.findByText("You need to agree to this.");
    expect(client.verifyCode).toHaveBeenCalledTimes(1);

    fireEvent.click(agree);
    fireEvent.click(screen.getByRole("button", { name: "Agree and continue" }));
    await screen.findByRole("heading", { name: "About you" });
    expect(client.verifyCode).toHaveBeenLastCalledWith(challenge.challengeId, "123456", {
      noticeVersion: "draft-1",
      purposes: ["account"],
    });

    type("Your name", "Asha");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith("/account");
    });
    expect(client.updateProfile).toHaveBeenCalledWith({
      name: "Asha",
      collegeOrWorkplace: null,
      gender: null,
    });
  });

  it("sends someone who has an account straight on", async () => {
    vi.mocked(client.requestCode).mockResolvedValue(challenge);
    vi.mocked(client.verifyCode).mockResolvedValue({
      user: person("Asha"),
      csrfToken: "token",
      newUser: false,
    });
    render(<SignInFlow text={text} next="/privacy" mode="people" />);

    await sendCode();
    enterCode();

    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith("/privacy");
    });
    expect(client.privacyNotice).not.toHaveBeenCalled();
  });

  it("shows the code where nothing sends it, and only there", async () => {
    vi.mocked(client.requestCode).mockResolvedValue({ ...challenge, developmentCode: "482916" });
    render(<SignInFlow text={text} next="/privacy" mode="people" />);

    await sendCode();

    expect(screen.getByText("Local development: the code is 482916.")).toBeTruthy();
  });

  it("shows no code when the API sends one by text", async () => {
    vi.mocked(client.requestCode).mockResolvedValue({ ...challenge, developmentCode: null });
    render(<SignInFlow text={text} next="/privacy" mode="people" />);

    await sendCode();

    expect(screen.queryByText(/Local development/)).toBeNull();
  });

  it("shows a number the API refuses next to its field", async () => {
    vi.mocked(client.requestCode).mockRejectedValue(
      problem(422, "VALIDATION_ERROR", [{ pointer: "/phone", detail: "Enter a number." }]),
    );
    render(<SignInFlow text={text} next="/account" mode="people" />);

    type("Mobile number", "12345 67890");
    fireEvent.click(screen.getByRole("button", { name: "Send code" }));

    const error = await screen.findByText("Enter a 10-digit Indian mobile number.");
    expect(screen.getByLabelText("Mobile number").getAttribute("aria-describedby")).toContain(
      error.id,
    );
  });

  it("sends someone back for a new code when theirs has expired", async () => {
    vi.mocked(client.requestCode).mockResolvedValue(challenge);
    vi.mocked(client.verifyCode).mockRejectedValue(problem(400, "OTP_EXPIRED"));
    render(<SignInFlow text={text} next="/account" mode="people" />);

    await sendCode();
    enterCode();

    await screen.findByRole("heading", { name: "Your mobile number" });
    expect(screen.getByRole("alert").textContent).toBe("That code has expired.");
    expect(screen.getByLabelText<HTMLInputElement>("Mobile number").value).toBe("98765 43210");
  });

  it("asks staff for their authenticator code after the phone code", async () => {
    vi.mocked(client.requestCode).mockResolvedValue(challenge);
    vi.mocked(client.verifyCode).mockResolvedValue({
      user: person("Asha"),
      csrfToken: "token",
      newUser: false,
    });
    vi.mocked(client.signInWithAuthenticator).mockResolvedValue({
      user: { ...person("Asha"), roles: ["ops"] },
      csrfToken: "token",
    });
    render(<SignInFlow text={text} next="/staff" mode="staff" />);

    await sendCode();
    enterCode();
    await screen.findByRole("heading", { name: "Your authenticator code" });
    type("Authenticator code", "654321");
    fireEvent.click(screen.getByRole("button", { name: "Sign in to staff tools" }));

    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith("/staff");
    });
    expect(client.signInWithAuthenticator).toHaveBeenCalledWith("654321");
  });

  it("meets WCAG 2.2 AA on the number and consent steps", async () => {
    vi.mocked(client.requestCode).mockResolvedValue(challenge);
    vi.mocked(client.verifyCode).mockRejectedValue(problem(400, "CONSENT_REQUIRED"));
    vi.mocked(client.privacyNotice).mockResolvedValue({
      version: "draft-1",
      purposes: [{ purpose: "account", required: true }],
    });
    const { container } = render(<SignInFlow text={text} next="/account" mode="people" />);

    const onPhone = await axe.run(container, { runOnly: [...WCAG_22_AA] });
    await sendCode();
    enterCode();
    await screen.findByRole("heading", { name: "Before we create your account" });
    const onConsent = await axe.run(container, { runOnly: [...WCAG_22_AA] });

    expect([...onPhone.violations, ...onConsent.violations].map((v) => v.id)).toEqual([]);
  });
});
