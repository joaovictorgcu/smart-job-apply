/**
 * "Upload your CV, check what we found."
 *
 * The service modules are mocked rather than the cache seeded, because what
 * matters here is what the wizard *sends*. Two promises are asserted directly:
 * reading a file writes nothing, and saving sends exactly what is on the screen
 * — including the corrections the user typed over a wrong parse, and only the
 * positions they left ticked.
 */

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Onboarding } from "@/pages/Onboarding";
import { renderWithProviders } from "@/test/utils";
import type { Profile, ResumeIntake, ResumeIntakeExperience } from "@/types/api";

vi.mock("@/services/profile", () => ({
  fetchProfile: vi.fn(),
  updateProfile: vi.fn(),
  uploadResume: vi.fn(),
  readResumeIntake: vi.fn(),
  readStoredResumeIntake: vi.fn(),
  applyResumeIntake: vi.fn(),
  fetchSettings: vi.fn(),
  updateSettings: vi.fn(),
  fetchAIStatus: vi.fn(),
  generateCoverLetter: vi.fn(),
  fetchHealth: vi.fn(),
}));

vi.mock("@/services/resumes", () => ({
  listExperiences: vi.fn(),
  fetchMasterResume: vi.fn(),
  listResumeVersions: vi.fn(),
  fetchApplicationResume: vi.fn(),
  adaptApplicationResume: vi.fn(),
  updateApplicationResume: vi.fn(),
  createExperience: vi.fn(),
  updateExperience: vi.fn(),
  deleteExperience: vi.fn(),
}));

import * as profileService from "@/services/profile";
import * as resumesService from "@/services/resumes";

const profileMock = vi.mocked(profileService);
const resumesMock = vi.mocked(resumesService);

const EMPTY_PROFILE: Profile = {
  headline: null,
  location: null,
  phone: null,
  years_of_experience: null,
  summary: null,
  resume_text: null,
  resume_filename: null,
  skills: [],
  preferred_languages: [],
  answer_bank: {},
  updated_at: null,
};

function buildExperience(overrides: Partial<ResumeIntakeExperience> = {}): ResumeIntakeExperience {
  return {
    role: "Desenvolvedor Full Stack",
    company: "GlobalThings",
    employment_type: null,
    location: "Recife, PE",
    started_on: "2023-01-01",
    ended_on: null,
    is_current: true,
    period_text: "Jan 2023 - Presente",
    summary: "",
    responsibilities: ["Construí APIs REST em .NET 8."],
    technologies: [".NET", "React"],
    is_complete: true,
    ...overrides,
  };
}

function buildIntake(overrides: Partial<ResumeIntake> = {}): ResumeIntake {
  return {
    full_name: "João Victor",
    headline: "Desenvolvedor Full Stack",
    location: "Recife, PE",
    email: "joao@example.com",
    phone: "+55 81 99999-1234",
    summary: "Full stack com foco em .NET e React.",
    skills: [".NET", "React"],
    languages: ["Português"],
    experiences: [buildExperience()],
    education: [],
    projects: [],
    certifications: [],
    warnings: [],
    resume_text: "texto do currículo",
    resume_filename: "user_1_resume.pdf",
    ...overrides,
  };
}

async function uploadAndConfirm(intake: ResumeIntake = buildIntake()) {
  profileMock.readResumeIntake.mockResolvedValue(intake);
  const user = userEvent.setup();
  renderWithProviders(<Onboarding />);

  const input = document.querySelector<HTMLInputElement>("#onboarding-resume");
  if (!input) throw new Error("the file input is missing");
  await user.upload(input, new File(["%PDF-1.4"], "cv.pdf", { type: "application/pdf" }));

  await screen.findByText(/encontramos estas informações/i);
  return user;
}

beforeEach(() => {
  vi.clearAllMocks();
  profileMock.fetchProfile.mockResolvedValue(EMPTY_PROFILE);
  resumesMock.listExperiences.mockResolvedValue([]);
  profileMock.applyResumeIntake.mockResolvedValue({
    profile: EMPTY_PROFILE,
    experiences_created: 1,
    experiences_removed: 0,
  });
});

describe("Onboarding", () => {
  it("shows what the resume said without saving anything", async () => {
    await uploadAndConfirm();

    expect(screen.getByDisplayValue("João Victor")).toBeInTheDocument();
    expect(screen.getByDisplayValue("GlobalThings")).toBeInTheDocument();
    expect(screen.getByText("Jan 2023 - Presente")).toBeInTheDocument();
    expect(profileMock.applyResumeIntake).not.toHaveBeenCalled();
  });

  it("surfaces what could not be read instead of coming back silently empty", async () => {
    await uploadAndConfirm(
      buildIntake({ experiences: [], warnings: ["Não reconhecemos as suas experiências."] }),
    );

    expect(screen.getByText(/não reconhecemos as suas experiências/i)).toBeInTheDocument();
  });

  it("saves the corrections the user typed, not the parsed guess", async () => {
    const user = await uploadAndConfirm();

    const company = screen.getByDisplayValue("GlobalThings");
    await user.clear(company);
    await user.type(company, "Acme Tecnologia");
    await user.click(screen.getByRole("button", { name: /está certo, salvar/i }));

    await waitFor(() => expect(profileMock.applyResumeIntake).toHaveBeenCalledTimes(1));
    const payload = profileMock.applyResumeIntake.mock.calls[0][0];
    expect(payload.experiences).toHaveLength(1);
    expect(payload.experiences?.[0].company).toBe("Acme Tecnologia");
    // The bullets and technologies ride along untouched.
    expect(payload.experiences?.[0].technologies).toEqual([".NET", "React"]);
    expect(payload.replace_experiences).toBe(false);
  });

  it("leaves out a position the user unticked", async () => {
    const user = await uploadAndConfirm();

    await user.click(screen.getByRole("checkbox", { name: /incluir esta experiência/i }));
    await user.click(screen.getByRole("button", { name: /está certo, salvar/i }));

    await waitFor(() => expect(profileMock.applyResumeIntake).toHaveBeenCalledTimes(1));
    expect(profileMock.applyResumeIntake.mock.calls[0][0].experiences).toEqual([]);
  });

  it("refuses to save a ticked position with no company", async () => {
    const user = await uploadAndConfirm(
      buildIntake({ experiences: [buildExperience({ company: "", is_complete: false })] }),
    );

    expect(screen.getByRole("button", { name: /está certo, salvar/i })).toBeDisabled();
    expect(screen.getByText(/preencha o cargo e a empresa/i)).toBeInTheDocument();

    // Unticking it is the other way out, and it re-enables the button.
    await user.click(screen.getByRole("checkbox", { name: /incluir esta experiência/i }));
    expect(screen.getByRole("button", { name: /está certo, salvar/i })).toBeEnabled();
  });

  it("never replaces existing positions unless asked", async () => {
    resumesMock.listExperiences.mockResolvedValue([
      {
        id: 1,
        company: "Antiga",
        role: "Dev",
        employment_type: null,
        location: null,
        started_on: null,
        ended_on: null,
        is_current: false,
        summary: null,
        responsibilities: [],
        technologies: [],
        results: [],
        projects: [],
        position: 0,
        created_at: null,
        updated_at: null,
      },
    ]);
    const user = await uploadAndConfirm();

    await screen.findByText(/o seu perfil já tem 1 experiência/i);
    await user.click(screen.getByRole("checkbox", { name: /substituir as anteriores/i }));
    await user.click(screen.getByRole("button", { name: /está certo, salvar/i }));

    await waitFor(() => expect(profileMock.applyResumeIntake).toHaveBeenCalledTimes(1));
    expect(profileMock.applyResumeIntake.mock.calls[0][0].replace_experiences).toBe(true);
  });
});
