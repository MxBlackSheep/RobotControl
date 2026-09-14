import React, { useRef } from 'react';
export default function SectionPanel({active, children}: {active: boolean; children: React.ReactNode}) {
  const visited = useRef(false);
  if (active) visited.current = true;
  return <div hidden={!active}>{visited.current ? children : null}</div>;
}
