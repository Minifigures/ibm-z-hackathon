import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ExplainPanel } from "@/components/explain-panel";

describe("ExplainPanel", () => {
  it("shows the empty-state hint when no text has been generated", () => {
    render(
      <ExplainPanel
        text={null}
        source={null}
        loading={false}
        onRequest={() => {}}
        focusName={null}
      />,
    );
    expect(screen.getByText(/click/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Explain$/ })).toBeEnabled();
  });

  it("shows the focus region in the header when one is selected", () => {
    render(
      <ExplainPanel
        text={null}
        source={null}
        loading={false}
        onRequest={() => {}}
        focusName="Mexico"
      />,
    );
    expect(screen.getByText(/Mexico/)).toBeInTheDocument();
  });

  it("renders the generated text and the source badge when text is present", () => {
    render(
      <ExplainPanel
        text="Madrid is exposed via gravity from BRA."
        source="anthropic"
        loading={false}
        onRequest={() => {}}
        focusName="Madrid"
      />,
    );
    expect(screen.getByText(/gravity from BRA/)).toBeInTheDocument();
    expect(screen.getByText(/Claude Haiku/)).toBeInTheDocument();
  });

  it("disables the button while loading and surfaces the loading label", () => {
    render(
      <ExplainPanel
        text={null}
        source={null}
        loading
        onRequest={() => {}}
        focusName={null}
      />,
    );
    const button = screen.getByRole("button");
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent(/Generating/i);
  });

  it("invokes onRequest when the button is clicked", () => {
    const onRequest = vi.fn();
    render(
      <ExplainPanel
        text={null}
        source={null}
        loading={false}
        onRequest={onRequest}
        focusName={null}
      />,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(onRequest).toHaveBeenCalledTimes(1);
  });
});
