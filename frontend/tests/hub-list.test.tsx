import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { HubList } from "@/components/hub-list";
import type { HubRow } from "@/lib/api";

const ROWS: HubRow[] = [
  { iso3: "MEX", name: "Mexico", expected_cases: 320, per_100k: 2.5 },
  { iso3: "CAN", name: "Canada", expected_cases: 160, per_100k: 4.1 },
  { iso3: "BRA", name: "Brazil", expected_cases: 80, per_100k: 0.4 },
];

describe("HubList", () => {
  it("renders the title and ranks rows in the supplied order", () => {
    render(<HubList title="Top imports" rows={ROWS} valueKey="expected_cases" />);
    expect(screen.getByText("Top imports")).toBeInTheDocument();
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("MEX");
    expect(items[2]).toHaveTextContent("BRA");
  });

  it("formats expected-cases values as integers with thousands separators", () => {
    const big: HubRow[] = [{ iso3: "MEX", name: "Mexico", expected_cases: 12345.6 }];
    render(<HubList title="Top imports" rows={big} valueKey="expected_cases" />);
    expect(screen.getByText("12,346")).toBeInTheDocument();
  });

  it("invokes onSelect with the iso3 of the clicked row", () => {
    const onSelect = vi.fn();
    render(
      <HubList title="Top imports" rows={ROWS} valueKey="expected_cases" onSelect={onSelect} />,
    );
    fireEvent.click(screen.getAllByRole("listitem")[1]);
    expect(onSelect).toHaveBeenCalledWith("CAN");
  });
});
