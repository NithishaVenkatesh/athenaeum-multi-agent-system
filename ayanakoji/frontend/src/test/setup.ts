import "@testing-library/jest-dom/vitest";

// jsdom has no matchMedia; framer-motion's reduced-motion check needs it.
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}

// jsdom does not implement scrollIntoView; the chat view calls it to follow the
// stream. Make it a no-op so components that auto-scroll can render under test.
if (typeof Element !== "undefined" && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
