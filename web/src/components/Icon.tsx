import add from "@material-symbols/svg-400/rounded/add.svg";
import audioFile from "@material-symbols/svg-400/rounded/audio_file.svg";
import close from "@material-symbols/svg-400/rounded/close.svg";
import dashboard from "@material-symbols/svg-400/rounded/dashboard.svg";
import graphicEq from "@material-symbols/svg-400/rounded/graphic_eq.svg";
import logout from "@material-symbols/svg-400/rounded/logout.svg";
import movie from "@material-symbols/svg-400/rounded/movie.svg";
import settings from "@material-symbols/svg-400/rounded/settings.svg";
import upload from "@material-symbols/svg-400/rounded/upload.svg";
import type { CSSProperties } from "react";

const ICONS = {
  add,
  audio_file: audioFile,
  close,
  dashboard,
  graphic_eq: graphicEq,
  logout,
  movie,
  settings,
  upload,
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
