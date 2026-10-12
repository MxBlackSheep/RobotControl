/**
 * The app is a fixed frame: header, then `main` (the only scroll area), then the phone page bar.
 * The window never scrolls, so nothing can drag the header or the bar along with the content.
 */

/** Height from the top of `element` to the end of the scroll area, however far it is scrolled. */
export function heightBelow(element: Element): number {
  const main = element.closest('main');
  const top = element.getBoundingClientRect().top;
  if (!main) return (window.visualViewport?.height ?? window.innerHeight) - top;
  const offset = top - main.getBoundingClientRect().top + main.scrollTop;
  return main.clientHeight - offset - (parseFloat(getComputedStyle(main).paddingBottom) || 0);
}

/** Re-measure when the scroll area itself changes height (window, keyboard, banner, page bar). */
export function observeScrollArea(element: Element, observer: ResizeObserver) {
  const main = element.closest('main');
  if (main) observer.observe(main);
}
