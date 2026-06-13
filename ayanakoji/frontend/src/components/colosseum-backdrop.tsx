/**
 * Colosseum watermark grounding the app in the Athenaeum's old-Rome character.
 * Fixed full-viewport and non-interactive (kept off scroll containers per perf
 * guidance); the whole monument is shown, sized under the viewport and pinned to
 * the bottom edge so it sits on the floor of the page and fades up into the paper.
 *
 * The source art (public/colosseum.png) is light-on-black; inverting + multiply
 * drops the black field and leaves a soft dark relief on the warm paper. Swap
 * public/colosseum.png to restyle.
 */
export function ColosseumBackdrop() {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 -z-10 overflow-hidden"
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/colosseum.png"
        alt=""
        className="absolute bottom-0 left-1/2 h-[75vh] w-auto max-w-none -translate-x-1/2 opacity-[0.16] mix-blend-multiply filter-[invert(1)_saturate(0)] mask-[linear-gradient(to_top,black,transparent_82%)]"
      />
    </div>
  );
}
