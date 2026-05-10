import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { TimeScrubber } from "@/components/time-scrubber";

describe("TimeScrubber", () => {
  it("renders Day n / horizon and the live badge when in live mode", () => {
    render(
      <TimeScrubber
        horizonDays={30}
        currentDay={null}
        playing={false}
        onScrub={() => {}}
        onPlayToggle={() => {}}
        onLive={() => {}}
      />,
    );
    expect(screen.getByText("Day 30 / 30")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /live/i })).toBeDisabled();
  });

  it("emits onScrub with the parsed day when the slider moves", () => {
    const onScrub = vi.fn();
    render(
      <TimeScrubber
        horizonDays={30}
        currentDay={5}
        playing={false}
        onScrub={onScrub}
        onPlayToggle={() => {}}
        onLive={() => {}}
      />,
    );
    fireEvent.change(screen.getByRole("slider"), { target: { value: "12" } });
    expect(onScrub).toHaveBeenCalledWith(12);
  });

  it("calls onPlayToggle when the play button is clicked", () => {
    const onPlayToggle = vi.fn();
    render(
      <TimeScrubber
        horizonDays={30}
        currentDay={5}
        playing={false}
        onScrub={() => {}}
        onPlayToggle={onPlayToggle}
        onLive={() => {}}
      />,
    );
    fireEvent.click(screen.getByLabelText("Play"));
    expect(onPlayToggle).toHaveBeenCalledTimes(1);
  });

  it("auto-advances the day while playing", () => {
    vi.useFakeTimers();
    try {
      const onScrub = vi.fn();
      render(
        <TimeScrubber
          horizonDays={5}
          currentDay={2}
          playing
          onScrub={onScrub}
          onPlayToggle={() => {}}
          onLive={() => {}}
        />,
      );
      vi.advanceTimersByTime(150);
      expect(onScrub).toHaveBeenCalledWith(3);
    } finally {
      vi.useRealTimers();
    }
  });
});
