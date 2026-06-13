/**
 * Faint Roman-arcade watermark grounding the whole app in the Athenaeum's
 * old-Rome character. Fixed and non-interactive (kept off scroll containers per
 * perf guidance), faded into the paper at the bottom of the viewport.
 *
 * Swap public/colosseum.svg for a different architectural asset to restyle.
 */
export function ColosseumBackdrop() {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-x-0 bottom-0 -z-10 flex justify-center overflow-hidden"
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/colosseum.svg"
        alt=""
        className="w-[min(1400px,150vw)] max-w-none opacity-[0.055] [mask-image:linear-gradient(to_top,black,transparent_88%)]"
      />
    </div>
  );
}
