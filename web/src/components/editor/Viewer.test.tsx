import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import Viewer from "./Viewer";

const CUES = [
  { speaker: "SPEAKER_00", start: 0, end: 2.5, text: "Hello world" },
  { speaker: "SPEAKER_01", start: 3.0, end: 5.0, text: "مرحبا بالعالم" },
];

describe("Viewer", () => {
  it("commits an inline caption edit when clicking the Save button without reopening", async () => {
    const onEditCue = vi.fn();
    const user = userEvent.setup();

    render(
      <Viewer
        cues={CUES}
        currentTime={0.5}
        chunkWords={5}
        onChunkWords={() => {}}
        onSeek={() => {}}
        onEditCue={onEditCue}
        onDownload={() => {}}
        loading={false}
        error={false}
        hasTranscript={true}
      />,
    );

    await user.click(screen.getByRole("button", { name: /edit caption 1/i }));
    const input = screen.getByRole("textbox", { name: /edit caption 1/i });
    expect(input).toHaveAttribute("dir", "auto");

    await user.clear(input);
    await user.type(input, "Updated line");
    await user.click(screen.getByRole("button", { name: /save caption 1/i }));

    expect(onEditCue).toHaveBeenCalledWith(CUES[0], "Updated line");
    expect(
      screen.queryByRole("textbox", { name: /edit caption 1/i }),
    ).not.toBeInTheDocument();
  });
});
