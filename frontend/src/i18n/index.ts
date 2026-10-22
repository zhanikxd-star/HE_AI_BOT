import { en } from "./en";
import { kk } from "./kk";
import { ru, type MessageKey } from "./ru";

export type Locale = "ru" | "kk" | "en";

const dictionaries = { ru, kk, en };

export function t(key: MessageKey, locale: Locale = "ru"): string {
  return dictionaries[locale][key] ?? ru[key];
}
