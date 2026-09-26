import React, { ReactNode, useLayoutEffect, useRef, useState } from "react";
import { Box, Button } from "@mui/material";

interface InspectionWorkspaceProps {
  label: string;
  selector?: ReactNode;
  selectorLabel?: string;
  detailOpen?: boolean;
  onBack?: () => void;
  onDetailVisibilityChange?: (visible: boolean) => void;
  children: ReactNode;
}

/** A bounded reading area. The app header and page heading determine its height. */
export default function InspectionWorkspace({
  label,
  selector,
  selectorLabel = "Items",
  detailOpen = true,
  onBack,
  onDetailVisibilityChange,
  children,
}: InspectionWorkspaceProps) {
  const workspace = useRef<HTMLDivElement>(null);
  const detail = useRef<HTMLDivElement>(null);
  const catalogue = useRef<HTMLDivElement>(null);
  const previousOpen = useRef(detailOpen);
  const [height, setHeight] = useState<number>();
  const [narrow, setNarrow] = useState(false);
  const [selectorVisible, setSelectorVisible] = useState(true);
  const detailVisible = !selector || !narrow || detailOpen;

  useLayoutEffect(() => {
    onDetailVisibilityChange?.(detailVisible);
  }, [detailVisible, onDetailVisibilityChange]);

  useLayoutEffect(() => {
    const element = workspace.current;
    if (!element) return;
    const measure = () => {
      const bounds = element.getBoundingClientRect();
      if (!bounds.width) return; // A visited, hidden section keeps its previous size.
      const main = element.closest("main");
      const bottomSpace = main
        ? parseFloat(getComputedStyle(main).paddingBottom) || 0
        : 0;
      const viewportHeight =
        window.visualViewport?.height ?? window.innerHeight;
      setHeight(
        Math.max(
          320,
          Math.floor(
            viewportHeight - (bounds.top + window.scrollY) - bottomSpace,
          ),
        ),
      );
      setNarrow(bounds.width < 900);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    if (element.parentElement) observer.observe(element.parentElement);
    window.addEventListener("resize", measure);
    window.visualViewport?.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
      window.visualViewport?.removeEventListener("resize", measure);
    };
  }, []);

  useLayoutEffect(() => {
    if (narrow && detailOpen !== previousOpen.current) {
      if (detailOpen) detail.current?.focus({ preventScroll: true });
      else
        catalogue.current
          ?.querySelector<HTMLElement>('[aria-current="true"], .Mui-selected')
          ?.focus({ preventScroll: true });
    }
    previousOpen.current = detailOpen;
  }, [detailOpen, narrow]);

  return (
    <Box
      ref={workspace}
      aria-label={label}
      sx={{
        height: height ?? "70dvh",
        minHeight: 320,
        minWidth: 0,
        width: "100%",
        display: "flex",
        gap: 1.5,
        "& .MuiButton-root, & .MuiIconButton-root": {
          minHeight: 44,
          minWidth: 44,
        },
        "& .MuiInputBase-root": { minHeight: 44 },
        "& .MuiFormControlLabel-root": { minHeight: 44 },
      }}
    >
      {selector && (
        <Box
          ref={catalogue}
          component="aside"
          aria-label={selectorLabel}
          sx={{
            display: (narrow ? !detailOpen : selectorVisible) ? "flex" : "none",
            flexDirection: "column",
            width: narrow ? "100%" : 300,
            flexShrink: 0,
            minWidth: 0,
            minHeight: 0,
          }}
        >
          {selector}
        </Box>
      )}
      <Box
        ref={detail}
        tabIndex={-1}
        sx={{
          display: detailVisible ? "flex" : "none",
          flex: 1,
          flexDirection: "column",
          minWidth: 0,
          minHeight: 0,
          outline: "none",
        }}
      >
        {selector && (
          <Box sx={{ flexShrink: 0, pb: 0.5 }}>
            {narrow ? (
              <Button onClick={onBack}>
                Back to {selectorLabel.toLowerCase()}
              </Button>
            ) : (
              <Button
                onClick={() => setSelectorVisible((value) => !value)}
                aria-expanded={selectorVisible}
              >
                {selectorVisible ? "Hide" : "Show"}{" "}
                {selectorLabel.toLowerCase()}
              </Button>
            )}
          </Box>
        )}
        <Box
          sx={{
            display: "flex",
            flexDirection: "column",
            flex: 1,
            minWidth: 0,
            minHeight: 0,
          }}
        >
          {children}
        </Box>
      </Box>
    </Box>
  );
}
