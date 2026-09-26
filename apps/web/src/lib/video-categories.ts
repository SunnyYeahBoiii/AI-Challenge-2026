/** Video groups available in the single-select search filter. */
export const VIDEO_CATEGORIES = [
  { id: "news", label: "Bản tin", description: "L21, L22, M01–M10", prefixes: ["L21_V", "L22_V", "M"] },
  { id: "cycling", label: "Đua xe đạp", description: "L23, S01", prefixes: ["L23_V", "S01-"] },
  { id: "lion-dance", label: "Múa lân", description: "L24", prefixes: ["L24_V"] },
  { id: "education", label: "Dạy học", description: "L25", prefixes: ["L25_V"] },
  { id: "cooking", label: "Nấu ăn", description: "L26", prefixes: ["L26_V"] },
  { id: "vn-travel", label: "VN Đi là ghiền", description: "L27", prefixes: ["L27_V"] },
  { id: "mekong-stories", label: "Tản mạn Mekong", description: "L28", prefixes: ["L28_V"] },
  { id: "mekong-eyes", label: "Đôi mắt Mekong", description: "L29", prefixes: ["L29_V"] },
  { id: "youth", label: "Tuổi trẻ", description: "L30", prefixes: ["L30_V"] },
  { id: "traffic", label: "Camera giao thông", description: "N01–N100", prefixes: ["N"] },
] as const;

export type VideoCategoryId = (typeof VIDEO_CATEGORIES)[number]["id"];
export type VideoPrefix = (typeof VIDEO_CATEGORIES)[number]["prefixes"][number];

export function prefixesForVideoCategory(categoryId: VideoCategoryId | ""): VideoPrefix[] {
  return [...(VIDEO_CATEGORIES.find((category) => category.id === categoryId)?.prefixes ?? [])];
}
