import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { DiseaseSearch } from "@/components/disease-search";
import { api, type DiseaseLookupResult } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: { ...actual.api, diseaseLookup: vi.fn() },
  };
});

const mockLookup = api.diseaseLookup as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockLookup.mockReset();
});

describe("DiseaseSearch", () => {
  it("disables the button when input is empty", () => {
    render(<DiseaseSearch onApply={() => {}} />);
    expect(screen.getByRole("button", { name: /Auto-fill/ })).toBeDisabled();
  });

  it("calls onApply with returned params on a successful lookup", async () => {
    const onApply = vi.fn();
    mockLookup.mockResolvedValueOnce({
      status: "ok",
      params: {
        label: "Ebola",
        r0: 1.8,
        incubation_days: 8,
        infectious_days: 7,
        cfr_pct: 50,
        sources: ["WHO 2024"],
        confidence: "high",
        notes: "Test.",
        likely_origin_iso3: "NGA",
        likely_origin_reason: "Filovirus outbreak history.",
      },
      retrieved: [],
      cached: false,
    } satisfies DiseaseLookupResult);

    render(<DiseaseSearch onApply={onApply} />);
    fireEvent.change(screen.getByPlaceholderText(/Type any virus/), {
      target: { value: "ebola" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Auto-fill/ }));

    await waitFor(() => expect(onApply).toHaveBeenCalledTimes(1));
    expect(onApply).toHaveBeenCalledWith(
      expect.objectContaining({ label: "Ebola", r0: 1.8, cfr_pct: 50 }),
    );
    expect(await screen.findByText(/Loaded/)).toBeInTheDocument();
    expect(screen.getByText(/Ebola/)).toBeInTheDocument();
  });

  it("shows the rejection message when the lookup fails validation", async () => {
    const onApply = vi.fn();
    mockLookup.mockResolvedValueOnce({
      status: "rejected",
      message: "Model output failed validation (hard mode).",
    } satisfies DiseaseLookupResult);

    render(<DiseaseSearch onApply={onApply} />);
    fireEvent.change(screen.getByPlaceholderText(/Type any virus/), {
      target: { value: "fakepathogen" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Auto-fill/ }));

    await waitFor(() =>
      expect(screen.getByText(/failed validation/i)).toBeInTheDocument(),
    );
    expect(onApply).not.toHaveBeenCalled();
  });
});
