import add from "@material-symbols/svg-400/rounded/add.svg";
import arrowBack from "@material-symbols/svg-400/rounded/arrow_back.svg";
import arrowForward from "@material-symbols/svg-400/rounded/arrow_forward.svg";
import audioFile from "@material-symbols/svg-400/rounded/audio_file.svg";
import check from "@material-symbols/svg-400/rounded/check.svg";
import close from "@material-symbols/svg-400/rounded/close.svg";
import contentCopy from "@material-symbols/svg-400/rounded/content_copy.svg";
import dashboard from "@material-symbols/svg-400/rounded/dashboard.svg";
import download from "@material-symbols/svg-400/rounded/download.svg";
import edit from "@material-symbols/svg-400/rounded/edit.svg";
import graphicEq from "@material-symbols/svg-400/rounded/graphic_eq.svg";
import keyboardArrowDown from "@material-symbols/svg-400/rounded/keyboard_arrow_down.svg";
import keyboardArrowUp from "@material-symbols/svg-400/rounded/keyboard_arrow_up.svg";
import logout from "@material-symbols/svg-400/rounded/logout.svg";
import menu from "@material-symbols/svg-400/rounded/menu.svg";
import menuOpen from "@material-symbols/svg-400/rounded/menu_open.svg";
import movie from "@material-symbols/svg-400/rounded/movie.svg";
import pause from "@material-symbols/svg-400/rounded/pause.svg";
import playArrow from "@material-symbols/svg-400/rounded/play_arrow.svg";
import restartAlt from "@material-symbols/svg-400/rounded/restart_alt.svg";
import search from "@material-symbols/svg-400/rounded/search.svg";
import settings from "@material-symbols/svg-400/rounded/settings.svg";
import tune from "@material-symbols/svg-400/rounded/tune.svg";
import upload from "@material-symbols/svg-400/rounded/upload.svg";
import visibility from "@material-symbols/svg-400/rounded/visibility.svg";
import visibilityOff from "@material-symbols/svg-400/rounded/visibility_off.svg";
import volumeOff from "@material-symbols/svg-400/rounded/volume_off.svg";
import volumeUp from "@material-symbols/svg-400/rounded/volume_up.svg";
import type { CSSProperties } from "react";

const ICONS = {
  add,
  arrow_back: arrowBack,
  arrow_forward: arrowForward,
  audio_file: audioFile,
  check,
  close,
  content_copy: contentCopy,
  dashboard,
  download,
  edit,
  graphic_eq: graphicEq,
  keyboard_arrow_down: keyboardArrowDown,
  keyboard_arrow_up: keyboardArrowUp,
  logout,
  menu,
  menu_open: menuOpen,
  movie,
  pause,
  play_arrow: playArrow,
  restart_alt: restartAlt,
  search,
  settings,
  tune,
  upload,
  visibility,
  visibility_off: visibilityOff,
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
