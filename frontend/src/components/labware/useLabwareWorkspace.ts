import { useLayoutEffect, useRef, useState } from 'react';
import { heightBelow, observeScrollArea } from '../appShell';

/** Available space is independent of the diagrams or rows fitted inside it. */
export function useLabwareWorkspace(active: boolean, ready = true) {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useLayoutEffect(() => {
    const element = ref.current;
    if (!active || !ready || !element) return;
    let frame = 0;
    const measure = () => {
      if (!element.clientWidth || !element.getClientRects().length) return;
      // Position within the scroll area, so ordinary page scrolling cannot change the fit.
      const bounds = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      // clientWidth loses scrollbar width and can flip the compact breakpoint
      // back and forth when a short desktop first starts scrolling.
      const width = Math.floor(bounds.width - (parseFloat(style.borderLeftWidth) || 0) - (parseFloat(style.borderRightWidth) || 0));
      const height = Math.max(0, Math.floor(heightBelow(element)));
      setSize(previous => previous.width === width && previous.height === height ? previous : { width, height });
    };
    const schedule = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(measure); };
    const observer = new ResizeObserver(schedule);
    // Our height is never an input. Observe width changes and the preceding
    // headers/actions whose wrapping can move this anchor down the page.
    observer.observe(element);
    observeScrollArea(element, observer);
    for (let anchor: Element | null = element; anchor && anchor.tagName !== 'MAIN'; anchor = anchor.parentElement) {
      for (let sibling = anchor.previousElementSibling; sibling; sibling = sibling.previousElementSibling) observer.observe(sibling);
    }
    measure();
    window.addEventListener('resize', schedule);
    window.visualViewport?.addEventListener('resize', schedule);
    return () => {
      observer.disconnect(); cancelAnimationFrame(frame);
      window.removeEventListener('resize', schedule);
      window.visualViewport?.removeEventListener('resize', schedule);
    };
  }, [active, ready]);

  return { ref, ...size };
}
