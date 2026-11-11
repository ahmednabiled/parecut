import add from "@material-symbols/svg-400/rounded/add.svg";
import audioFile from "@material-symbols/svg-400/rounded/audio_file.svg";
import check from "@material-symbols/svg-400/rounded/check.svg";
import close from "@material-symbols/svg-400/rounded/close.svg";
import contentCopy from "@material-symbols/svg-400/rounded/content_copy.svg";
import dashboard from "@material-symbols/svg-400/rounded/dashboard.svg";
import download from "@material-symbols/svg-400/rounded/download.svg";
import edit from "@material-symbols/svg-400/rounded/edit.svg";
import graphicEq from "@material-symbols/svg-400/rounded/graphic_eq.svg";
import logout from "@material-symbols/svg-400/rounded/logout.svg";
import movie from "@material-symbols/svg-400/rounded/movie.svg";
import pause from "@material-symbols/svg-400/rounded/pause.svg";
import playArrow from "@material-symbols/svg-400/rounded/play_arrow.svg";
import settings from "@material-symbols/svg-400/rounded/settings.svg";
import upload from "@material-symbols/svg-400/rounded/upload.svg";
import volumeOff from "@material-symbols/svg-400/rounded/volume_off.svg";
import volumeUp from "@material-symbols/svg-400/rounded/volume_up.svg";
import type { CSSProperties } from "react";

const ICONS = {
  add,
  audio_file: audioFile,
  check,
  close,
  content_copy: contentCopy,
  dashboard,
  download,
  edit,
  graphic_eq: graphicEq,
  logout,
  movie,
  pause,
  play_arrow: playArrow,
  settings,
  upload,
  volume_off: volumeOff,
  volume_up: volumeUp,
};

export type IconName = keyof typeof ICONS;

export default function Icon({
  name,
  size = 18,
  className = "",
}: {
  name: IconName;
  size?: number;
  className?: string;
}) {
  const style: CSSProperties = {
    width: size,
    height: size,
    maskImage: `url("${ICONS[name]}")`,
    WebkitMaskImage: `url("${ICONS[name]}")`,
    maskSize: "contain",
    WebkitMaskSize: "contain",
    maskRepeat: "no-repeat",
    WebkitMaskRepeat: "no-repeat",
    maskPosition: "center",
    WebkitMaskPosition: "center",
  };
  return (
    <span
      aria-hidden="true"
      style={style}
      className={`inline-block shrink-0 bg-current ${className}`}
    />
  );
}
