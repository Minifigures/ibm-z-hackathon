import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { SDGBadge } from "@/components/sdg-badge";

describe("SDGBadge", () => {
  it("renders the compact badge listing the five SDG numbers", () => {
    render(<SDGBadge />);
    const badge = screen.getByRole("button", { name: /UN Sustainable Development Goals/i });
    expect(badge).toHaveTextContent("3");
    expect(badge).toHaveTextContent("9");
    expect(badge).toHaveTextContent("11");
    expect(badge).toHaveTextContent("13");
    expect(badge).toHaveTextContent("17");
    expect(badge).toHaveAttribute("aria-expanded", "false");
  });

  it("toggles a details panel listing each SDG when clicked", () => {
    render(<SDGBadge />);
    const badge = screen.getByRole("button", { name: /UN Sustainable Development Goals/i });
    fireEvent.click(badge);
    expect(badge).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/Good Health and Well-being/)).toBeInTheDocument();
    expect(screen.getByText(/Climate Action/)).toBeInTheDocument();
    expect(screen.getByText(/Partnerships for the Goals/)).toBeInTheDocument();
  });

  it("hides the details panel when reopened and closed via the X button", () => {
    render(<SDGBadge />);
    const badge = screen.getByRole("button", { name: /UN Sustainable Development Goals/i });
    fireEvent.click(badge);
    fireEvent.click(screen.getByLabelText(/Close SDG details/i));
    expect(badge).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/Good Health and Well-being/)).not.toBeInTheDocument();
  });
});
