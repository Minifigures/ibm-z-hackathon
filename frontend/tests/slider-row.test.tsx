import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SliderRow } from "@/components/slider-row";

describe("SliderRow", () => {
  it("renders the formatted value next to the label", () => {
    render(
      <SliderRow
        label="R0"
        value={2.5}
        min={0.5}
        max={5}
        step={0.1}
        format={(v) => v.toFixed(1)}
        onChange={() => {}}
      />,
    );
    expect(screen.getByText("R0")).toBeInTheDocument();
    expect(screen.getByText("2.5")).toBeInTheDocument();
  });

  it("renders the optional hint text", () => {
    render(
      <SliderRow
        label="R0"
        hint="Basic reproduction number"
        value={2}
        min={0}
        max={5}
        step={0.1}
        onChange={() => {}}
      />,
    );
    expect(screen.getByText("Basic reproduction number")).toBeInTheDocument();
  });

  it("invokes onChange with a parsed number when the slider moves", () => {
    const onChange = vi.fn();
    render(
      <SliderRow label="R0" value={2} min={0} max={5} step={0.1} onChange={onChange} />,
    );
    const slider = screen.getByRole("slider") as HTMLInputElement;
    fireEvent.change(slider, { target: { value: "3.4" } });
    expect(onChange).toHaveBeenCalledWith(3.4);
  });

  it("uses a default integer format when no formatter is supplied for whole steps", () => {
    render(<SliderRow label="Days" value={30} min={1} max={120} step={1} onChange={() => {}} />);
    expect(screen.getByText("30")).toBeInTheDocument();
  });
});
