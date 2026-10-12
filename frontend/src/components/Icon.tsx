export type IconName = "camera" | "home" | "folder" | "menu" | "eye" | "eyeOff" | "user" | "info" | "logout";
const paths: Record<IconName, string> = {
  camera: "M4 7h4l2-3h4l2 3h4v13H4z M16 13a4 4 0 1 1-8 0 4 4 0 0 1 8 0",
  home: "M3 11l9-8 9 8 M5 10v11h5v-7h4v7h5V10",
  folder: "M3 6h7l2 3h9v11H3z",
  menu: "M4 6h16 M4 12h16 M4 18h16",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12 M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0",
  eyeOff: "M3 3l18 18 M9 5a12 12 0 0 1 3 0c6 0 10 7 10 7a22 22 0 0 1-4 5 M6 6a22 22 0 0 0-4 6s4 7 10 7a13 13 0 0 0 5-1",
  user: "M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M4 21v-2a8 8 0 0 1 16 0v2",
  info: "M12 11v6 M12 7v1 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  logout: "M10 3H4v18h6 M9 12h12 M17 8l4 4-4 4",
};
export function Icon({ name, size = 22 }: { name: IconName; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}
