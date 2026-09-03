import "@testing-library/jest-dom/vitest";

// jsdom has no layout engine, so scrollIntoView is unimplemented -- any
// component that calls it (research-thread's autoscroll) throws in tests
// otherwise. A no-op is the correct behaviour here: nothing in jsdom
// scrolls anyway.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
