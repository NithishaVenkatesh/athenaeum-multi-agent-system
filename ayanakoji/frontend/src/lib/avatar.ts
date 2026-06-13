/**
 * Deterministic learner avatars.
 *
 * DiceBear "notionists-neutral" generated locally (no network, CSP-safe) and
 * seeded by the persona's codename, so the same person always gets the same
 * face. Warm paper-tinted backgrounds keep avatars in the atelier palette.
 */

import { notionistsNeutral } from "@dicebear/collection";
import { createAvatar } from "@dicebear/core";

const PAPER_BACKGROUNDS = ["f1e9dc", "e9dccb", "f4eee3"];

/** A stable `data:image/svg+xml` URI for the given seed (e.g. a codename). */
export function avatarDataUri(seed: string): string {
  return createAvatar(notionistsNeutral, {
    seed,
    backgroundColor: PAPER_BACKGROUNDS,
    backgroundType: ["solid"],
    radius: 50,
  }).toDataUri();
}
