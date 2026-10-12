import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Box, ButtonBase } from '@mui/material';
import { layout } from '../../theme';

export type DeckCard = { name: string; node: React.ReactNode };

/** The deck's side padding; it bleeds into the page padding so the next card peeks in. */
const bleed = layout.pagePhone;

/**
 * Phone Overview: the panels as a row of cards the browser scrolls and snaps natively. There is
 * no gesture code; the dots and the label only follow the scroll position. Every card stays
 * mounted, so each panel keeps polling exactly as it does in the grid.
 */
export default function OverviewDeck({ cards }: { cards: DeckCard[] }) {
  const scroller = useRef<HTMLDivElement>(null);
  const cardRefs = useRef<(HTMLDivElement | null)[]>([]);
  const [current, setCurrent] = useState(0);
  const total = cards.length;

  // Snap targets, clamped to the furthest scroll: the last card cannot reach the start edge.
  const targets = useCallback(() => {
    const el = scroller.current;
    if (!el) return [];
    const max = el.scrollWidth - el.clientWidth;
    return Array.from({ length: total }, (_, i) => Math.min(Math.max(0, (cardRefs.current[i]?.offsetLeft ?? 0) - bleed), max));
  }, [total]);

  const track = useCallback(() => {
    const el = scroller.current;
    if (!el) return;
    const positions = targets();
    let nearest = 0;
    positions.forEach((left, i) => { if (Math.abs(left - el.scrollLeft) < Math.abs(positions[nearest] - el.scrollLeft)) nearest = i; });
    setCurrent(nearest);
  }, [targets]);

  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    let frame = 0;
    const onScroll = () => {
      if (frame) return;
      frame = requestAnimationFrame(() => { frame = 0; track(); });
    };
    track();
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => { el.removeEventListener('scroll', onScroll); cancelAnimationFrame(frame); };
  }, [track]);

  // A card added in front (a new hold) would otherwise stay off-screen: the browser keeps the
  // card it had snapped to. The first card is the most urgent, so show it.
  const first = cards[0]?.name;
  const previousFirst = useRef(first);
  useEffect(() => {
    if (previousFirst.current !== first) scroller.current?.scrollTo({ left: 0, behavior: 'auto' });
    previousFirst.current = first;
  }, [first]);

  // The CSS scroll-behavior decides smooth or instant, so reduced motion is honoured here too.
  const show = (index: number) => scroller.current?.scrollTo({ left: targets()[index] ?? 0 });

  const shown = Math.min(current, total - 1);
  return <Box>
    <Box sx={{ mb: 1, ml: '-13px' }}>
      <Box sx={{ display: 'flex' }}>
        {cards.map((card, i) => <ButtonBase key={card.name} disableRipple aria-label={card.name} aria-current={i === shown ? 'true' : undefined} onClick={() => show(i)}
          sx={{ minWidth: 44, minHeight: 24, borderRadius: `${layout.radius}px` }}>
          <Box component="span" aria-hidden sx={{ display: 'block', height: 6, width: i === shown ? 18 : 6, borderRadius: 3,
            bgcolor: i === shown ? 'primary.main' : 'text.disabled', transition: 'width 150ms', '@media (prefers-reduced-motion: reduce)': { transition: 'none' } }} />
        </ButtonBase>)}
      </Box>
    </Box>
    <Box ref={scroller} role="region" aria-roledescription="carousel" aria-label="Overview cards" tabIndex={0}
      sx={{
        position: 'relative', display: 'flex', alignItems: 'flex-start', gap: `${layout.gutter}px`,
        mx: `-${bleed}px`, px: `${bleed}px`, scrollPaddingInline: `${bleed}px`,
        // 2px of block padding keeps focus rings inside the cards from being clipped by the scroller.
        py: '2px', my: '-2px',
        overflowX: 'auto', overflowY: 'hidden', scrollSnapType: 'x mandatory', overscrollBehaviorX: 'contain', touchAction: 'pan-x pan-y',
        scrollBehavior: 'smooth', '@media (prefers-reduced-motion: reduce)': { scrollBehavior: 'auto' },
        scrollbarWidth: 'none', '&::-webkit-scrollbar': { display: 'none' },
        // The scroller spans the screen edge to edge, so its focus ring is drawn inside.
        '&:focus-visible': { outlineOffset: '-2px' },
      }}>
      {cards.map((card, i) => <Box key={card.name} ref={(node: HTMLDivElement | null) => { cardRefs.current[i] = node; }}
        role="group" aria-roledescription="card" aria-label={`${card.name}, ${i + 1} of ${total}`}
        sx={{ flex: '0 0 calc(100% - 24px)', minWidth: 0, scrollSnapAlign: 'start' }}>
        {card.node}
      </Box>)}
    </Box>
  </Box>;
}
